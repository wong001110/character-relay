"""Runtime adapter for same-topic skipped media continuation."""

from time import monotonic

from echo_masque.media_connector_runtime import (
    MediaAwareDiscordConnectorRuntime,
    MediaEpistemicSnapshot,
)
from echo_masque.media_continuation import SkippedMediaContinuationService
from echo_masque.semantic_turn_runtime import SemanticTurnSignalStore

_MEDIA_INSPECT_TOOL_ID = "media.inspect"


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
                and self.tool_registry.tool_id_for_provider_name("media_inspect")
                == _MEDIA_INSPECT_TOOL_ID
            )
        return super()._media_inspection_enabled(prepared)

    async def _ensure_media_context(self, prepared):  # type: ignore[no-untyped-def, override]
        await super()._ensure_media_context(prepared)
        key = (prepared.resolved.deployment.id, prepared.resolved.payload.message_id)
        reference = self._recalled_media.get(key)
        if reference is None:
            return
        self._inject_guidance(
            prepared,
            (
                "Character recalled media inspection choice:",
                (
                    "This message semantically continues the same topic and appears to ask you "
                    "to reconsider media you previously chose not to inspect."
                ),
                f"Earlier visible label: {reference.label or reference.kind}",
                (
                    "Runtime restored only the earlier reference. Its contents remain unknown "
                    "unless you call media_inspect now."
                ),
            ),
        )
        self._record_epistemic(
            key,
            monotonic(),
            MediaEpistemicSnapshot(
                state="skipped",
                attention_action="skip",
                attention_reason="same_topic_skipped_media_recalled",
                response_stance="neutral",
                stance_reason="Source restored; content remains unseen until media_inspect.",
                media_result_reason="recalled_skipped_media_reference",
            ),
        )

    def _registered_payload(self, key):  # type: ignore[no-untyped-def]
        values = getattr(self.tool_registry, "_shared_payload_by_turn", {})
        return values.get(key) if isinstance(values, dict) else None

    def _apply_media_inspection_result(self, prepared, result):  # type: ignore[no-untyped-def, override]
        key = (prepared.resolved.deployment.id, prepared.resolved.payload.message_id)
        reference = self._recalled_media.get(key)
        if reference is None:
            return super()._apply_media_inspection_result(prepared, result)
        inspection_payload = self._registered_payload(key)
        contexts = tuple(result.contexts)
        if (
            contexts
            and inspection_payload is not None
            and self.conversation_media_service is not None
        ):
            self.conversation_media_service.remember_perceived(
                owner_id=prepared.resolved.deployment.owner_id,
                deployment_id=prepared.resolved.deployment.id,
                character_card_id=prepared.resolved.card.id,
                payload=inspection_payload,
                contexts=contexts,
            )
            if self.skipped_media is not None:
                self.skipped_media.forget(reference)
            self._recalled_media.pop(key, None)
        self._record_epistemic(
            key,
            monotonic(),
            MediaEpistemicSnapshot(
                state="perceived" if contexts else "unavailable",
                attention_action="watch",
                attention_reason="recalled_media_inspection_requested",
                response_stance="neutral",
                stance_reason="Final behavior follows the grounded media Tool result.",
                context_count=len(contexts),
                cache_hits=result.cache_hits,
                media_result_reason=result.reason,
            ),
        )

    def _finalize_media_epistemic(self, prepared, output):  # type: ignore[no-untyped-def, override]
        key = (prepared.resolved.deployment.id, prepared.resolved.payload.message_id)
        current = self._active_shared_payload(prepared.resolved.payload)
        reference = self._recalled_media.get(key)
        if current is not None:
            super()._finalize_media_epistemic(prepared, output)
            if self.skipped_media is None:
                return
            if any(item.tool_id == _MEDIA_INSPECT_TOOL_ID for item in output.tool_traces):
                return
            signals = SemanticTurnSignalStore.get(*key)
            if signals is not None and signals.topic_id:
                self.skipped_media.remember_skipped(
                    owner_id=prepared.resolved.deployment.owner_id,
                    deployment_id=prepared.resolved.deployment.id,
                    character_card_id=prepared.resolved.card.id,
                    payload=current,
                    topic_id=signals.topic_id,
                )
            return
        if reference is None:
            return
        if any(item.tool_id == _MEDIA_INSPECT_TOOL_ID for item in output.tool_traces):
            return
        self._record_epistemic(
            key,
            monotonic(),
            MediaEpistemicSnapshot(
                state="skipped",
                attention_action="skip",
                attention_reason="recalled_media_not_inspected",
                response_stance="neutral",
                stance_reason="The recalled source remains unseen.",
                media_result_reason="recalled_skipped_media_not_inspected",
            ),
        )

    def epistemic_trace_metadata(self, prepared):  # type: ignore[no-untyped-def, override]
        metadata = list(super().epistemic_trace_metadata(prepared))
        key = (prepared.resolved.deployment.id, prepared.resolved.payload.message_id)
        reference = self._recalled_media.get(key)
        source = "recalled" if reference is not None else "current"
        source_message_id = (
            reference.message_id if reference is not None else prepared.resolved.payload.message_id
        )
        if metadata or self._media_inspection_enabled(prepared):
            metadata.extend(
                (
                    ("inspection_source", source),
                    ("source_message_id", source_message_id[:200]),
                    ("media_inspect_offered", str(self._media_inspection_enabled(prepared)).lower()),
                )
            )
        return tuple(metadata)


__all__ = ["MediaContinuationRuntime"]
