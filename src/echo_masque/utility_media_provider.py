"""Media-capability routing that preserves the existing SHA/cache/inspect pipeline."""

from __future__ import annotations

import base64
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import SecretStr

from echo_masque.admin_runtime import UtilityProviderMember
from echo_masque.media_runtime import MediaAnalysis, MediaAsset, MediaUnderstandingProvider
from echo_masque.network_safety import PublicUrlGuard
from echo_masque.provider_capabilities import ModelCapability, ProviderModelCapabilityRegistry
from echo_masque.provider_io import provider_dialect
from echo_masque.providers.errors import ProviderError, ProviderProtocolError
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider
from echo_masque.utility_gateway_router import UtilityGatewayRouter
from echo_masque.utility_media_pool_observer import UtilityMediaPoolObserver

_MAX_INLINE_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_REDIRECTS = 4


class _DataUriMultimodalProvider(OpenAICompatibleMultimodalProvider):
    """Adapt public image URLs to bounded inline Data URIs before provider submission."""

    def __init__(
        self,
        *,
        provider_id: str,
        api_key: SecretStr,
        model: str,
        base_url: str,
        timeout_seconds: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
        media_transport: httpx.AsyncBaseTransport | None = None,
        url_guard: PublicUrlGuard | None = None,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        self._media_transport = media_transport
        self._url_guard = url_guard or PublicUrlGuard()

    @staticmethod
    def _mime_hint(uri: str, declared: str = "") -> str:
        normalized = declared.split(";", 1)[0].strip().casefold()
        if normalized.startswith("image/"):
            return normalized
        path = urlparse(uri).path.casefold()
        for suffix, mime in (
            (".png", "image/png"),
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".webp", "image/webp"),
            (".gif", "image/gif"),
            (".avif", "image/avif"),
        ):
            if path.endswith(suffix):
                return mime
        return ""

    async def _data_uri(self, uri: str, *, declared_mime: str = "") -> str:
        if uri.casefold().startswith("data:"):
            return uri
        current = await self._url_guard.validate(uri)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            transport=self._media_transport,
            follow_redirects=False,
            headers={"User-Agent": "CharacterRelay/0.3 MediaTransport"},
        ) as client:
            for redirect_index in range(_MAX_REDIRECTS + 1):
                try:
                    async with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect_index >= _MAX_REDIRECTS:
                                raise ProviderProtocolError(
                                    "Media input conversion exceeded the redirect limit."
                                )
                            location = response.headers.get("location", "").strip()
                            if not location:
                                raise ProviderProtocolError(
                                    "Media input redirect omitted a destination."
                                )
                            current = await self._url_guard.validate(urljoin(current, location))
                            continue
                        if response.is_error:
                            raise ProviderProtocolError(
                                f"Media input fetch returned HTTP {response.status_code}."
                            )
                        length = response.headers.get("content-length", "").strip()
                        if length:
                            try:
                                declared_length = int(length)
                            except ValueError:
                                declared_length = 0
                            if declared_length > _MAX_INLINE_IMAGE_BYTES:
                                raise ProviderProtocolError(
                                    "Image is too large for provider Data URI transport."
                                )
                        chunks: list[bytes] = []
                        total = 0
                        async for chunk in response.aiter_bytes():
                            total += len(chunk)
                            if total > _MAX_INLINE_IMAGE_BYTES:
                                raise ProviderProtocolError(
                                    "Image is too large for provider Data URI transport."
                                )
                            chunks.append(chunk)
                        mime = self._mime_hint(
                            current,
                            response.headers.get("content-type", "") or declared_mime,
                        )
                        if not mime:
                            raise ProviderProtocolError(
                                "Image transport could not determine a supported image MIME type."
                            )
                        encoded = base64.b64encode(b"".join(chunks)).decode("ascii")
                        return f"data:{mime};base64,{encoded}"
                except httpx.HTTPError as exc:
                    raise ProviderProtocolError(
                        "Media input fetch failed before provider submission."
                    ) from exc
        raise ProviderProtocolError("Media input could not be converted to a Data URI.")

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis:
        updates: dict[str, object] = {}
        if asset.media_type == "image":
            updates["source_uri"] = await self._data_uri(
                asset.source_uri,
                declared_mime=asset.mime_type,
            )
        elif asset.keyframe_uris:
            converted = [await self._data_uri(uri) for uri in asset.keyframe_uris]
            updates["keyframe_uris"] = tuple(converted)
        adapted = asset.model_copy(update=updates) if updates else asset
        return await super().analyze(adapted)


class _GeminiMultimodalProvider(_DataUriMultimodalProvider):
    @property
    def endpoint(self) -> str:
        return f"{self._base_url.rstrip('/')}/chat/completions"


class UtilityMediaUnderstandingProvider(MediaUnderstandingProvider):
    """Try only media-compatible free members and feed outcomes back to Utility telemetry."""

    def __init__(
        self,
        gateway: UtilityGatewayRouter,
        *,
        fallback: MediaUnderstandingProvider | None = None,
    ) -> None:
        self.gateway = gateway
        self.fallback = fallback
        self.observer = UtilityMediaPoolObserver(gateway.database)

    @property
    def provider_id(self) -> str:
        return "utility-gateway"

    @property
    def model(self) -> str:
        return "media-pool-v2"

    @staticmethod
    def _base_url(provider: str, configured: str) -> str:
        if provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        return configured

    @staticmethod
    def _required(asset: MediaAsset, provider: str) -> tuple[ModelCapability, ...]:
        dialect = provider_dialect(provider)
        if asset.media_type == "image":
            values: list[ModelCapability] = ["image_input"]
            if (
                asset.source_uri.casefold().startswith("data:")
                or dialect.image_input_transport == "data_uri"
            ):
                values.extend(("data_uri_image", "inline_image_data"))
            else:
                values.append("remote_image_url")
            return tuple(values)
        if asset.keyframe_uris:
            values = ["image_input"]
            if len(asset.keyframe_uris) > 1:
                values.append("multi_image_input")
            if (
                any(uri.casefold().startswith("data:") for uri in asset.keyframe_uris)
                or dialect.image_input_transport == "data_uri"
            ):
                values.extend(("data_uri_image", "inline_image_data"))
            else:
                values.append("remote_image_url")
            return tuple(values)
        values = ["video_url", "remote_video_url"]
        host = (urlparse(asset.source_uri).hostname or "").casefold()
        if host in {"youtube.com", "www.youtube.com", "youtu.be"}:
            values.append("youtube_video_url")
        return tuple(values)

    def _providers(
        self,
        asset: MediaAsset,
    ) -> list[tuple[UtilityProviderMember, OpenAICompatibleMultimodalProvider]]:
        config = self.gateway.runtime.config().utility_gateway
        snapshots = {item.member_id: item for item in self.gateway.snapshot().members}
        members = [
            member
            for member in config.members
            if member.enabled and "media_understanding" in member.capabilities
        ]
        members.sort(key=lambda member: member.priority)
        providers: list[tuple[UtilityProviderMember, OpenAICompatibleMultimodalProvider]] = []
        for member in members:
            state = snapshots.get(member.id)
            if state is not None and state.status in {
                "unavailable",
                "cooling_down",
                "exhausted",
            }:
                continue
            credential = self.gateway.credential(member.id)
            if credential is None:
                continue
            base_url = self._base_url(member.provider, member.base_url)
            registry_provider = f"utility:{member.id}"
            required = self._required(asset, member.provider)
            if any(
                not ProviderModelCapabilityRegistry.allows(
                    provider=registry_provider,
                    model=member.model,
                    base_url=base_url,
                    capability=capability,
                )
                for capability in required
            ):
                continue
            if member.provider == "gemini":
                provider_type: type[OpenAICompatibleMultimodalProvider] = _GeminiMultimodalProvider
            elif provider_dialect(member.provider).image_input_transport == "data_uri":
                provider_type = _DataUriMultimodalProvider
            else:
                provider_type = OpenAICompatibleMultimodalProvider
            providers.append(
                (
                    member,
                    provider_type(
                        provider_id=registry_provider,
                        api_key=credential,
                        model=member.model,
                        base_url=base_url,
                        timeout_seconds=120.0,
                    ),
                )
            )
        return providers

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis:
        if self.gateway.runtime.config().utility_gateway.enabled:
            for member, provider in self._providers(asset):
                started = self.observer.started()
                try:
                    analysis = await provider.analyze(asset)
                except ProviderError as exc:
                    self.observer.failure(member, exc, started=started)
                    continue
                except ValueError:
                    continue
                base_url = self._base_url(member.provider, member.base_url)
                registry_provider = f"utility:{member.id}"
                for capability in self._required(asset, member.provider):
                    ProviderModelCapabilityRegistry.observe(
                        provider=registry_provider,
                        model=member.model,
                        base_url=base_url,
                        capability=capability,
                        supported=True,
                    )
                self.observer.success(member, started=started)
                return analysis
        if self.fallback is not None:
            return await self.fallback.analyze(asset)
        raise RuntimeError("No Media Understanding provider is currently available.")


__all__ = ["UtilityMediaUnderstandingProvider"]
