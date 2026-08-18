"""Media-capability routing that preserves the existing SHA/cache/inspect pipeline."""

from __future__ import annotations

from echo_masque.admin_runtime import UtilityProviderMember
from echo_masque.media_runtime import MediaAnalysis, MediaAsset, MediaUnderstandingProvider
from echo_masque.provider_capabilities import ModelCapability, ProviderModelCapabilityRegistry
from echo_masque.providers.errors import ProviderError
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider
from echo_masque.utility_gateway_router import UtilityGatewayRouter
from echo_masque.utility_media_pool_observer import UtilityMediaPoolObserver


class _GeminiMultimodalProvider(OpenAICompatibleMultimodalProvider):
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
    def _required(asset: MediaAsset) -> tuple[ModelCapability, ...]:
        if asset.media_type == "image":
            values: list[ModelCapability] = ["image_input"]
            if asset.source_uri.casefold().startswith("data:"):
                values.append("data_uri_image")
            return tuple(values)
        if asset.keyframe_uris:
            values = ["image_input"]
            if len(asset.keyframe_uris) > 1:
                values.append("multi_image_input")
            if any(uri.casefold().startswith("data:") for uri in asset.keyframe_uris):
                values.append("data_uri_image")
            return tuple(values)
        return ("video_url",)

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
        required = self._required(asset)
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
            provider_type = (
                _GeminiMultimodalProvider
                if member.provider == "gemini"
                else OpenAICompatibleMultimodalProvider
            )
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
                self.observer.success(member, started=started)
                return analysis
        if self.fallback is not None:
            return await self.fallback.analyze(asset)
        raise RuntimeError("No Media Understanding provider is currently available.")


__all__ = ["UtilityMediaUnderstandingProvider"]
