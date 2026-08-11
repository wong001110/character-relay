"""Discord Connector Runtime extension for persona-driven shared content perception."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal

from echo_masque.api.connector_schemas import (
    DiscordAttachmentContent,
    DiscordConnectorReplyView,
    DiscordInboundMessage,
)
from echo_masque.connector_runtime import (
    DiscordConnectorRuntime,
    PreparedCharacterTurn,
    ResolvedCharacterOutput,
    ResolvedCharacterTurn,
)
from echo_masque.conversation_media import ConversationMediaReferenceService
from echo_masque.domain import TargetResponse
from echo_masque.live_media import LiveMediaContext, LiveMediaContextService, LiveMediaResult
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.media_attention import (
    CharacterMediaAttentionDecider,
    MediaAttentionDecider,
    MediaAttentionDecision,
    MediaResponseStance,
    has_shared_content,
    skipped_media_guidance,
    unavailable_media_guidance,
    watched_media_guidance,
)
from echo_masque.providers import ProviderError
from echo_masque.providers.trace import provider_trace_scope
from echo_masque.targets import PromptModelTarget, PromptModelToolTurn

_MEDIA_RESULT_TTL_SECONDS = 300.0
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")
MediaEpistemicState = Literal["skipped", "perceived", "unavailable"]


@dataclass(frozen=True, slots=True)
class MediaEpistemicSnapshot:
    """Runtime truth for one Character's relationship to shared content in one turn."""

    state: MediaEpistemicState
    attention_action: Literal["passive", "watch", "skip"]
    attention_reason: str
    response_stance: MediaResponseStance
    stance_reason: str
    context_count: int = 0
    cache_hits: int = 0
    media_result_reason: str = ""


def _is_visible_image_attachment(item: DiscordAttachmentContent) -> bool:
    content_type = item.content_type.casefold().strip()
    filename = item.filename.casefold().strip()
    return content_type.startswith("image/") or filename.endswith(_IMAGE_EXTENSIONS)


def _passive_image_guidance(contexts: tuple[LiveMediaContext, ...]) -> tuple[str, ...]:
    if not contexts:
        return ()
    lines = [
        "Character passive image perception:",
        (
            "Runtime truth: actual_media_perception=perceived. A visible image attachment in the "
            "group chat was passively perceived; you did not need to choose to open it first."
        ),
        (
            "Seeing the image does not obligate you to comment on it. React, ignore it, joke, "
            "criticize, or focus elsewhere according to your persona, interests, mood, and the "
            "conversation."
        ),
        (
            "Use only the objective observations below as visual facts. Do not mention Vision, "
            "media providers, cache, or analysis internals."
        ),
    ]
    for index, item in enumerate(contexts, start=1):
        lines.extend(item.prompt_lines(index))
    return tuple(lines)


def _passive_image_unavailable_guidance(payload: DiscordInboundMessage) -> tuple[str, ...]:
    labels = [item.filename for item in payload.attachments if _is_visible_image_attachment(item)]
    preview = ", ".join(value for value in labels if value)[:800]
    lines = [
        "Character passive image perception:",
        (
            "Runtime truth: actual_media_perception=unavailable. A visible image attachment was "
            "present in the chat, but Runtime did not obtain reliable visual observations for it."
        ),
        (
            "Do not invent unseen image details. You may still react to the fact that an image was "
            "posted or stay silent according to your persona, without exposing technical errors."
        ),
    ]
    if preview:
        lines.append(f"Visible attachment label(s): {preview}")
    return tuple(lines)


class MediaAwareDiscordConnectorRuntime(DiscordConnectorRuntime):
    """Passively perceive visible images while keeping links/videos persona-controlled."""

    def __init__(
        self,
        *args: Any,
        live_media_service: LiveMediaContextService | None = None,
        media_attention_decider: MediaAttentionDecider | None = None,
        conversation_media_service: ConversationMediaReferenceService | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.live_media_service: LiveMediaContextService | None
        if isinstance(live_media_service, LiveMediaContextService):
            self.live_media_service = EnhancedLiveMediaContextService.from_service(
                live_media_service,
                browser_runtime=self.tool_registry.browser,
            )
        else:
            self.live_media_service = live_media_service
        self.media_attention_decider = media_attention_decider or CharacterMediaAttentionDecider()
        self.conversation_media_service = conversation_media_service
        self._media_turn_results: dict[
            tuple[str, str, str], tuple[float, LiveMediaResult]
        ] = {}
        self._media_attention_results: dict[
            tuple[str, str], tuple[float, MediaAttentionDecision]
        ] = {}
        self._media_epistemic_states: dict[
            tuple[str, str], tuple[float, MediaEpistemicSnapshot]
        ] = {}

    def prepare_character_turn(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> PreparedCharacterTurn:
        prepared = super().prepare_character_turn(resolved)
        setter = getattr(self.tool_registry, "set_turn_reply_reference", None)
        if callable(setter):
            setter(
                deployment_id=resolved.deployment.id,
                message_id=resolved.payload.message_id,
                reply_to_message_id=resolved.payload.reply_to_message_id,
            )
        return prepared

    async def invoke_character_model(
        self,
        prepared: PreparedCharacterTurn,
    ) -> TargetResponse:
        await self._ensure_media_context(prepared)
        try:
            return await super().invoke_character_model(prepared)
        except ProviderError as exc:
            self._isolate_provider_failure(prepared, exc)
            return self._provider_failure_response(exc)

    async def start_character_tool_turn(
        self,
        prepared: PreparedCharacterTurn,
    ) -> PromptModelToolTurn | None:
        await self._ensure_media_context(prepared)
        return await super().start_character_tool_turn(prepared)

    async def advance_character_tool_model(
        self,
        prepared: PreparedCharacterTurn,
        turn: PromptModelToolTurn,
    ) -> TargetResponse | None:
        try:
            return await super().advance_character_tool_model(prepared, turn)
        except ProviderError as exc:
            self._isolate_provider_failure(prepared, exc)
            return self._provider_failure_response(exc)

    async def resolve_character_output(
        self,
        prepared: PreparedCharacterTurn,
        response: TargetResponse,
    ) -> ResolvedCharacterOutput:
        output = await super().resolve_character_output(prepared, response)
        provider_failure = response.trace.get("provider_failure")
        if isinstance(provider_failure, str) and provider_failure:
            output.smart_reason = f"provider_turn_failed:{provider_failure}"
        elif output.smart_reason == "smart_output_retry_failed":
            deployment = prepared.resolved.deployment
            self.deployment_repository.update_deployment(
                deployment.id,
                deployment.owner_id,
                status="active",
                last_error="smart_output_retry_failed",
            )
        return output

    def authorize_character_output(
        self,
        prepared: PreparedCharacterTurn,
        output: ResolvedCharacterOutput,
    ) -> DiscordConnectorReplyView:
        view = super().authorize_character_output(prepared, output)
        getter = getattr(self.tool_registry, "generated_artifact_ids", None)
        if not callable(getter):
            return view
        artifact_ids = getter(prepared.tool_context)
        if not artifact_ids:
            return view
        return view.model_copy(update={"generated_artifact_ids": list(artifact_ids)[:4]})

    def _isolate_provider_failure(
        self,
        prepared: PreparedCharacterTurn,
        exc: ProviderError,
    ) -> None:
        if exc.deployment_fatal:
            return
        deployment = prepared.resolved.deployment
        detail = str(exc).replace("\x00", "").strip()
        last_error = exc.reason_code if not detail else f"{exc.reason_code}: {detail}"
        self.deployment_repository.update_deployment(
            deployment.id,
            deployment.owner_id,
            status="active",
            last_error=last_error[:2000],
        )

    @staticmethod
    def _provider_failure_response(exc: ProviderError) -> TargetResponse:
        return TargetResponse(
            text='[[CR_OUTPUT {"action":"ignore"}]]',
            latency_ms=0,
            trace={
                "provider_failure": exc.reason_code,
                "provider_failure_transient": exc.transient,
            },
        )

    @staticmethod
    def _split_passive_images(
        payload: DiscordInboundMessage,
    ) -> tuple[DiscordInboundMessage | None, DiscordInboundMessage]:
        image_attachments = [
            item for item in payload.attachments if _is_visible_image_attachment(item)
        ]
        if not image_attachments:
            return None, payload
        other_attachments = [
            item for item in payload.attachments if not _is_visible_image_attachment(item)
        ]
        passive_payload = payload.model_copy(
            update={"text": "", "embeds": [], "attachments": image_attachments}
        )
        active_payload = payload.model_copy(update={"attachments": other_attachments})
        return passive_payload, active_payload

    async def _media_result_for_payload(
        self,
        prepared: PreparedCharacterTurn,
        *,
        payload: DiscordInboundMessage,
        scope: str,
        now: float,
    ) -> LiveMediaResult:
        service = self.live_media_service
        if service is None:
            return LiveMediaResult(status="failed", reason="media_service_unavailable")
        resolved = prepared.resolved
        deployment = resolved.deployment
        key = (deployment.id, resolved.payload.message_id, scope)
        cached = self._media_turn_results.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        with provider_trace_scope(
            owner_id=deployment.owner_id,
            deployment_id=deployment.id,
            character_card_id=resolved.card.id,
        ):
            result = await service.contexts_for_turn(
                owner_id=deployment.owner_id,
                character_card_id=resolved.card.id,
                payload=payload,
            )
        self._media_turn_results[key] = (now + _MEDIA_RESULT_TTL_SECONDS, result)
        self._cleanup_cache(self._media_turn_results, now)
        return result

    async def _ensure_media_context(self, prepared: PreparedCharacterTurn) -> None:
        resolved = prepared.resolved
        deployment = resolved.deployment
        payload = resolved.payload

        memory_service = self.conversation_media_service
        if memory_service is not None:
            memories = memory_service.resolve_for_turn(
                deployment_id=deployment.id,
                character_card_id=resolved.card.id,
                payload=payload,
            )
            self._inject_guidance(prepared, memory_service.guidance(memories))

        if not has_shared_content(payload):
            return

        key = (deployment.id, payload.message_id)
        now = monotonic()
        passive_payload, active_payload = self._split_passive_images(payload)
        passive_contexts: tuple[LiveMediaContext, ...] = ()
        passive_cache_hits = 0
        passive_reason = ""

        if passive_payload is not None:
            passive_result = await self._media_result_for_payload(
                prepared,
                payload=passive_payload,
                scope="passive-images",
                now=now,
            )
            passive_contexts = tuple(
                item for item in passive_result.contexts if item.kind == "image"
            )
            passive_cache_hits = passive_result.cache_hits
            passive_reason = passive_result.reason
            if passive_contexts:
                if memory_service is not None:
                    memory_service.remember_perceived(
                        owner_id=deployment.owner_id,
                        deployment_id=deployment.id,
                        character_card_id=resolved.card.id,
                        payload=passive_payload,
                        contexts=passive_contexts,
                    )
                self._inject_guidance(prepared, _passive_image_guidance(passive_contexts))
            else:
                self._inject_guidance(
                    prepared,
                    _passive_image_unavailable_guidance(passive_payload),
                )

        if not has_shared_content(active_payload):
            state: MediaEpistemicState = "perceived" if passive_contexts else "unavailable"
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state=state,
                    attention_action="passive",
                    attention_reason="visible_image_attachment",
                    response_stance="truthful",
                    stance_reason="Visible images are passively perceived before persona reaction.",
                    context_count=len(passive_contexts),
                    cache_hits=passive_cache_hits,
                    media_result_reason=passive_reason,
                ),
            )
            return

        attention = await self._attention_for_turn(
            prepared,
            payload=active_payload,
            key=key,
            now=now,
        )
        if attention.action == "skip":
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="perceived" if passive_contexts else "skipped",
                    attention_action="skip",
                    attention_reason=attention.reason,
                    response_stance=attention.response_stance,
                    stance_reason=attention.stance_reason,
                    context_count=len(passive_contexts),
                    cache_hits=passive_cache_hits,
                    media_result_reason=(
                        "passive_image_perceived_active_skipped"
                        if passive_contexts
                        else "active_content_skipped"
                    ),
                ),
            )
            self._inject_guidance(prepared, skipped_media_guidance(active_payload, attention))
            return

        if self.live_media_service is None:
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="perceived" if passive_contexts else "unavailable",
                    attention_action="watch",
                    attention_reason=attention.reason,
                    response_stance=attention.response_stance,
                    stance_reason=attention.stance_reason,
                    context_count=len(passive_contexts),
                    cache_hits=passive_cache_hits,
                    media_result_reason="media_service_unavailable",
                ),
            )
            self._inject_guidance(prepared, unavailable_media_guidance(active_payload, attention))
            return

        result = await self._media_result_for_payload(
            prepared,
            payload=active_payload,
            scope="active-content",
            now=now,
        )
        active_contexts = result.contexts
        all_contexts = tuple([*passive_contexts, *active_contexts])
        total_cache_hits = passive_cache_hits + result.cache_hits

        if not active_contexts:
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="perceived" if passive_contexts else "unavailable",
                    attention_action="watch",
                    attention_reason=attention.reason,
                    response_stance=attention.response_stance,
                    stance_reason=attention.stance_reason,
                    context_count=len(passive_contexts),
                    cache_hits=total_cache_hits,
                    media_result_reason=result.reason,
                ),
            )
            self._inject_guidance(prepared, unavailable_media_guidance(active_payload, attention))
            return

        self._record_epistemic(
            key,
            now,
            MediaEpistemicSnapshot(
                state="perceived",
                attention_action="watch",
                attention_reason=attention.reason,
                response_stance=attention.response_stance,
                stance_reason=attention.stance_reason,
                context_count=len(all_contexts),
                cache_hits=total_cache_hits,
                media_result_reason=result.reason,
            ),
        )
        if memory_service is not None:
            memory_service.remember_perceived(
                owner_id=deployment.owner_id,
                deployment_id=deployment.id,
                character_card_id=resolved.card.id,
                payload=active_payload,
                contexts=active_contexts,
            )
        guidance = (
            *watched_media_guidance(active_contexts, attention),
            (
                "Evidence boundary: do not infer scenes, speech, demonstrations, or conclusions "
                "that are absent from the observations below. A video title/description or web "
                "page preview alone is not evidence that you watched the full video."
            ),
        )
        self._inject_guidance(prepared, guidance)

    async def _attention_for_turn(
        self,
        prepared: PreparedCharacterTurn,
        *,
        payload: DiscordInboundMessage,
        key: tuple[str, str],
        now: float,
    ) -> MediaAttentionDecision:
        cached = self._media_attention_results.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        target = prepared.resolved.target
        if not isinstance(target, PromptModelTarget):
            decision = MediaAttentionDecision(
                action="watch",
                reason="non_prompt_target",
                response_stance="truthful",
                stance_reason="Deterministic target follows resolved content directly.",
            )
        else:
            deployment = prepared.resolved.deployment
            with provider_trace_scope(
                owner_id=deployment.owner_id,
                deployment_id=deployment.id,
                character_card_id=prepared.resolved.card.id,
            ):
                decision = await self.media_attention_decider.decide(
                    target=target,
                    payload=payload,
                )

        self._media_attention_results[key] = (
            now + _MEDIA_RESULT_TTL_SECONDS,
            decision,
        )
        self._cleanup_cache(self._media_attention_results, now)
        return decision

    def epistemic_trace_metadata(
        self,
        prepared: PreparedCharacterTurn,
    ) -> tuple[tuple[str, str], ...]:
        resolved = prepared.resolved
        key = (resolved.deployment.id, resolved.payload.message_id)
        cached = self._media_epistemic_states.get(key)
        if cached is None or cached[0] <= monotonic():
            return ()
        snapshot = cached[1]
        return (
            ("actual_perception", snapshot.state),
            ("attention_action", snapshot.attention_action),
            ("attention_reason", snapshot.attention_reason[:300]),
            ("response_stance", snapshot.response_stance),
            ("stance_reason", snapshot.stance_reason[:300]),
            ("stance_grounding", self._stance_grounding(snapshot.state, snapshot.response_stance)),
            ("media_context_count", str(snapshot.context_count)),
            ("media_cache_hits", str(snapshot.cache_hits)),
            ("media_result_reason", snapshot.media_result_reason[:300]),
        )

    def _record_epistemic(
        self,
        key: tuple[str, str],
        now: float,
        snapshot: MediaEpistemicSnapshot,
    ) -> None:
        self._media_epistemic_states[key] = (
            now + _MEDIA_RESULT_TTL_SECONDS,
            snapshot,
        )
        self._cleanup_cache(self._media_epistemic_states, now)

    @staticmethod
    def _stance_grounding(state: MediaEpistemicState, stance: MediaResponseStance) -> str:
        if stance == "neutral":
            return "no_explicit_media_stance"
        if stance == "truthful":
            return (
                "grounded_in_perception"
                if state == "perceived"
                else "honest_about_limited_perception"
            )
        if stance in {"bluff", "lie", "tease"}:
            return (
                "intentional_social_distortion_with_perception"
                if state == "perceived"
                else "intentional_without_perception"
            )
        if stance == "evasive":
            return "evasive"
        if stance in {"guess", "uncertain"}:
            return (
                "speculative_with_perception"
                if state == "perceived"
                else "speculative_without_perception"
            )
        return "unclassified"

    @staticmethod
    def _inject_guidance(
        prepared: PreparedCharacterTurn,
        guidance: tuple[str, ...],
    ) -> None:
        if not guidance:
            return
        markers = (
            "Character passive image perception:",
            "Character media attention:",
            "Character media perception for this turn:",
            "Character media perception:",
            "Remembered media perception from this conversation:",
        )
        first_line = guidance[0]
        if first_line in prepared.prompt:
            return
        if first_line not in markers and any(marker in prepared.prompt for marker in markers):
            return
        block = "\n".join(guidance)
        final_line = "Return Smart Output now."
        if prepared.prompt.endswith(final_line):
            prepared.prompt = (
                prepared.prompt[: -len(final_line)].rstrip()
                + "\n"
                + block
                + "\n"
                + final_line
            )
        else:
            prepared.prompt = prepared.prompt.rstrip() + "\n" + block

    @staticmethod
    def _cleanup_cache(cache: dict[Any, Any], now: float) -> None:
        if len(cache) <= 1000:
            return
        stale = [key for key, value in cache.items() if value[0] <= now]
        for key in stale:
            cache.pop(key, None)


__all__ = [
    "MediaAwareDiscordConnectorRuntime",
    "MediaEpistemicSnapshot",
    "MediaEpistemicState",
]
