"""Credential-scoped live Media Understanding service.

Objective MediaAnalysis records remain globally reusable by content/provider/model, while
stateful provider instances (which contain API credentials) are isolated per Key Group.
"""

from echo_masque.live_media import LiveMediaContextService
from echo_masque.media_runtime import MediaAnalysis, MediaAsset, MediaUnderstandingService
from echo_masque.provider_credentials import ResolvedProviderCredential


class KeyGroupScopedLiveMediaContextService(LiveMediaContextService):
    """Never reuse a credential-bearing provider instance across Key Groups."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._key_group_services: dict[
            tuple[str, str, str, str], MediaUnderstandingService
        ] = {}

    async def _analyze(
        self,
        asset: MediaAsset,
        credential: ResolvedProviderCredential,
    ) -> tuple[MediaAnalysis, bool]:
        key = (
            credential.key_group_id,
            credential.provider.casefold(),
            credential.base_url.rstrip("/"),
            credential.model,
        )
        service = self._key_group_services.get(key)
        if service is None:
            provider = self.provider_factory(credential)
            service = MediaUnderstandingService(self.media_repository, provider)
            self._key_group_services[key] = service
        return await service.analyze(asset)
