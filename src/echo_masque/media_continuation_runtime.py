"""Runtime adapter for same-topic skipped media continuation."""

from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
from echo_masque.media_continuation import SkippedMediaContinuationService
from echo_masque.semantic_turn_runtime import SemanticTurnSignalStore


class MediaContinuationRuntime(MediaAwareDiscordConnectorRuntime):
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        memory = self.conversation_media_service
        self.skipped_media = (
            SkippedMediaContinuationService(memory.repository) if memory is not None else None
        )
        self._recalled_media = {}

    def prepare_character_turn(self, resolved):  # type: ignore[no-untyped-def, override]
        prepared = super().prepare_character_turn(resolved)
        key = (resolved.deployment.id, resolved.payload.message_id)
        self._recalled_media.pop(key, None)
        if self._active_shared_payload(resolved.payload) is not None:
            return prepared
        signals = SemanticTurnSignalStore.get(*key)
        if self.skipped_media is None or signals is None or not signals.topic_id:
            return prepared
        reference = self.skipped_media.resolve_for_turn(
            deployment_id=resolved.deployment.id,
            character_card_id=resolved.card.id,
            payload=resolved.payload,
            topic_id=signals.topic_id,
        )
        if reference is None:
            return prepared
        self._recalled_media[key] = reference
        setter = getattr(self.tool_registry, "set_turn_media_payload", None)
        if callable(setter):
            setter(
                deployment_id=resolved.deployment.id,
                message_id=resolved.payload.message_id,
                payload=self.skipped_media.payload_for_reference(resolved.payload, reference),
            )
        return prepared

    def _media_inspection_enabled(self, prepared):  # type: ignore[no-untyped-def, override]
        key = (prepared.resolved.deployment.id, prepared.resolved.payload.message_id)
        if key in self._recalled_media:
            return (
                self.live_media_service is not None
                and self.tool_registry.tool_id_for_provider_name("media_inspect") == "media.inspect"
            )
        return super()._media_inspection_enabled(prepared)


__all__ = ["MediaContinuationRuntime"]
