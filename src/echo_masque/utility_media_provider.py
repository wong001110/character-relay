"""Media-capability routing that preserves the existing SHA/cache/inspect pipeline."""

from __future__ import annotations

from echo_masque.media_runtime import (
    MediaAnalysis,
    MediaAsset,
    MediaUnderstandingProvider,
)
from echo_masque.providers.errors import ProviderError
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider
from echo_masque.utility_gateway_router import UtilityGatewayRouter


class _GeminiMultimodalProvider(OpenAICompatibleMultimodalProvider):
    @property
    def endpoint(self) -> str:
        return f"{self._base_url.rstrip('/')}/chat/completions"


class UtilityMediaUnderstandingProvider(MediaUnderstandingProvider):
    """Try configured free media members before the existing Deployment media provider."""

    def __init__(
        self,
        gateway: UtilityGatewayRouter,
        *,
        fallback: MediaUnderstandingProvider | None = None,
    ) -> None:
        self.gateway = gateway
        self.fallback = fallback

    @property
    def provider_id(self) -> str:
        return "utility-gateway"

    @property
    def model(self) -> str:
        return "media-pool-v1"

    @staticmethod
    def _base_url(provider: str, configured: str) -> str:
        if provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        return configured

    def _providers(self) -> list[OpenAICompatibleMultimodalProvider]:
        config = self.gateway.runtime.config().utility_gateway
        snapshots = {item.member_id: item for item in self.gateway.snapshot().members}
        members = [
            member
            for member in config.members
            if member.enabled and "media_understanding" in member.capabilities
        ]
        members.sort(key=lambda member: member.priority)
        providers: list[OpenAICompatibleMultimodalProvider] = []
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
            provider_type = (
                _GeminiMultimodalProvider
                if member.provider == "gemini"
                else OpenAICompatibleMultimodalProvider
            )
            providers.append(
                provider_type(
                    provider_id=f"utility:{member.id}",
                    api_key=credential,
                    model=member.model,
                    base_url=self._base_url(member.provider, member.base_url),
                    timeout_seconds=120.0,
                )
            )
        return providers

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis:
        if self.gateway.runtime.config().utility_gateway.enabled:
            for provider in self._providers():
                try:
                    return await provider.analyze(asset)
                except (ProviderError, ValueError):
                    continue
        if self.fallback is not None:
            return await self.fallback.analyze(asset)
        raise RuntimeError("No Media Understanding provider is currently available.")


__all__ = ["UtilityMediaUnderstandingProvider"]
