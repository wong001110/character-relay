"""Discord Connector Runtime extension for shared-content perception.

Visible image attachments remain passively perceived. Links, videos, and other non-visible
shared content are now inspected through a Runtime-owned Tool only when the Character model
requests it during the normal Character turn. This avoids a separate Media Attention LLM pass.
"""

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
from echo_masque.live_media import (
    LiveMediaContext,
    LiveMediaContextService,
    LiveMediaResult,
    media_prompt_guidance,
)
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.media_attention import MediaResponseStance, has_shared_content
from echo_masque.media_dependency import resolve_media_dependency
from echo_masque.providers import ProviderError
from echo_masque.providers.trace import provider_trace_scope
from echo_masque.targets import PromptModelTarget, PromptModelToolTurn

_MEDIA_RESULT_TTL_SECONDS = 300.0
_MEDIA_INSPECT_TOOL_ID = "media.inspect"
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")
MediaEpistemicState = Literal["skipped", "perceived", "unavailable"]


@dataclass(frozen=True, slots=True)
class MediaEpistemicSnapshot:
    """Runtime truth for one Character's relationship to shared content in one turn."""

    state: MediaEpistemicState
    attention_action: Literal["passive", "required", "watch", "skip"]
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


def _active_media_choice_guidance() -> tuple[str, ...]:
    return (
        "Character media inspection choice:",
        (
            "A shared link/video/other non-visible item is present. You are not required to open "
            "it. If your persona is genuinely interested or you need unseen details before "
            "choosing your final Discord action, call media_inspect."
        ),
        (
            "If you do not call media_inspect, treat unseen details as unknown and decide from the "
            "Discord-visible preview and conversation only. Choose any currently allowed visible "
            "social action without pretending you inspected the content."
        ),
        (
            "For the current shared media/link, use media_inspect rather than generic web/file "
            "tools when you need the actual content."
        ),
    )


class MediaAwareDiscordConnectorRuntime(DiscordConnectorRuntime):
    """Passively perceive visible images and inspect links/videos only through Tool Calling."""

    def __init__(
        self,
        *args: Any,
        live_media_service: LiveMediaContextService | None = None,
        media_attention_decider: Any | None = None,
        conversation_media_service: ConversationMediaReferenceService | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        # Kept as a compatibility-only constructor argument for older tests/callers. The
        # dedicated Media Attention model pass is intentionally no longer used.
        del media_attention_decider
        self.live_media_service: LiveMediaContextService | None
        if isinstance(live_media_service, LiveMediaContextService):
            self.live_media_service = EnhancedLiveMediaContextService.from_service(
                live_media_service,
                browser_runtime=self.tool_registry.browser,
            )
        else:
            self.live_media_service = live_media_service
        self.conversation_media_service = conversation_media_service
        self._media_turn_results: dict[tuple[str, str, str], tuple[float, LiveMediaResult]] = {}
        self._media_epistemic_states: dict[
            tuple[str, str], tuple[float, MediaEpistemicSnapshot]
        ] = {}

        setter = getattr(self.tool_registry, "set_live_media_service", None)
        if callable(setter):
            setter(self.live_media_service)

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

        media_setter = getattr(self.tool_registry, "set_turn_media_payload", None)
        if callable(media_setter):
            active_payload = self._active_shared_payload(resolved.payload)
            media_setter(
                deployment_id=resolved.deployment.id,
                message_id=resolved.payload.message_id,
                payload=active_payload,
            )
        return prepared

    async def invoke_character_model(
        self,
        prepared: PreparedCharacterTurn,
    ) -> TargetResponse:
        await self._ensure_media_context(prepared)
        target = prepared.resolved.target
        try:
            if isinstance(target, PromptModelTarget) and self._media_inspection_enabled(prepared):
                enabled = self._enabled_tools_with_media(prepared)
                return await target.send_with_tools(
                    prepared.prompt,
                    tool_registry=self.tool_registry,
                    enabled_tool_ids=enabled,
                    tool_context=prepared.tool_context,
                    max_tool_rounds=2,
                    forced_tool_ids=(_MEDIA_INSPECT_TOOL_ID,),
                )
            return await super().invoke_character_model(prepared)
        except ProviderError as exc:
            # The base path already records Provider errors; the direct media-tool path does not.
            if isinstance(target, PromptModelTarget) and self._media_inspection_enabled(prepared):
                self.deployment_repository.record_deployment_error(
                    prepared.resolved.deployment.id,
                    str(exc),
                )
            self._isolate_provider_failure(prepared, exc)
            return self._provider_failure_response(exc)
        except Exception as exc:
            if isinstance(target, PromptModelTarget) and self._media_inspection_enabled(prepared):
                self.deployment_repository.record_deployment_error(
                    prepared.resolved.deployment.id,
                    str(exc),
                )
            raise

    async def start_character_tool_turn(
        self,
        prepared: PreparedCharacterTurn,
    ) -> PromptModelToolTurn | None:
        await self._ensure_media_context(prepared)
        target = prepared.resolved.target
        if not isinstance(target, PromptModelTarget) or not self._media_inspection_enabled(
            prepared
        ):
            return await super().start_character_tool_turn(prepared)

        try:
            return await target.start_tool_turn(
                prepared.prompt,
                tool_registry=self.tool_registry,
                enabled_tool_ids=self._enabled_tools_with_media(prepared),
                tool_context=prepared.tool_context,
                max_tool_rounds=2,
                forced_tool_ids=(_MEDIA_INSPECT_TOOL_ID,),
            )
        except Exception as exc:
            self.deployment_repository.record_deployment_error(
                prepared.resolved.deployment.id,
                str(exc),
            )
            raise

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

    async def execute_character_tools(
        self,
        prepared: PreparedCharacterTurn,
        turn: PromptModelToolTurn,
    ) -> int:
        before = len(turn.traces)
        executed = await super().execute_character_tools(prepared, turn)
        media_traces = [
            item for item in turn.traces[before:] if item.tool_id == _MEDIA_INSPECT_TOOL_ID
        ]
        if media_traces:
            getter = getattr(self.tool_registry, "media_inspection_result", None)
            result = getter(prepared.tool_context) if callable(getter) else None
            if isinstance(result, LiveMediaResult):
                self._apply_media_inspection_result(prepared, result)
            elif any(item.status != "completed" for item in media_traces):
                self._record_failed_media_tool(prepared)
        return executed

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
        self._finalize_media_epistemic(prepared, output)
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

    @classmethod
    def _active_shared_payload(
        cls,
        payload: DiscordInboundMessage,
    ) -> DiscordInboundMessage | None:
        _, active_payload = cls._split_passive_images(payload)
        return active_payload if has_shared_content(active_payload) else None

    def _media_inspection_enabled(self, prepared: PreparedCharacterTurn) -> bool:
        if self.live_media_service is None:
            return False
        active = self._active_shared_payload(prepared.resolved.payload)
        if active is None:
            return False
        dependency = resolve_media_dependency(
            text=prepared.resolved.payload.text,
            has_media=True,
        )
        if dependency.dependency != "optional":
            return False
        return (
            self.tool_registry.tool_id_for_provider_name("media_inspect") == _MEDIA_INSPECT_TOOL_ID
        )

    @staticmethod
    def _enabled_tools_with_media(prepared: PreparedCharacterTurn) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*prepared.enabled_tools, _MEDIA_INSPECT_TOOL_ID)))

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
        key = (deployment.id, payload.message_id, scope)
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

    async def _burst_passive_image_contexts(
        self,
        prepared: PreparedCharacterTurn,
        *,
        payload: DiscordInboundMessage,
        now: float,
    ) -> tuple[tuple[LiveMediaContext, ...], int]:
        """Perceive visible image messages collected immediately before the current text.

        Each source is resolved with its original Discord message ID so Conversation Media and
        Graph provenance remain attached to the actual image message instead of the burst tail.
        """

        memory_service = self.conversation_media_service
        contexts: list[LiveMediaContext] = []
        cache_hits = 0
        seen: set[str] = set()
        for raw_message_id in payload.burst_media_message_ids[:2]:
            source_message_id = raw_message_id.strip()
            if (
                not source_message_id
                or source_message_id == payload.message_id
                or source_message_id in seen
            ):
                continue
            seen.add(source_message_id)
            source_payload = payload.model_copy(
                update={
                    "message_id": source_message_id,
                    "text": "",
                    "attachments": [],
                    "embeds": [],
                    "burst_media_message_ids": [],
                }
            )
            result = await self._media_result_for_payload(
                prepared,
                payload=source_payload,
                scope=f"burst-passive-image:{source_message_id}",
                now=now,
            )
            source_contexts = tuple(item for item in result.contexts if item.kind == "image")
            if not source_contexts:
                continue
            cache_hits += result.cache_hits
            if memory_service is not None:
                memory_service.remember_perceived(
                    owner_id=prepared.resolved.deployment.owner_id,
                    deployment_id=prepared.resolved.deployment.id,
                    character_card_id=prepared.resolved.card.id,
                    payload=source_payload,
                    contexts=source_contexts,
                )
            contexts.extend(source_contexts)
            if len(contexts) >= 5:
                break
        return tuple(contexts[:5]), cache_hits

    async def _ensure_media_context(self, prepared: PreparedCharacterTurn) -> None:
        """Inject memory/passive images only; active links/videos are Tool-driven."""

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

        key = (deployment.id, payload.message_id)
        now = monotonic()
        burst_contexts, burst_cache_hits = await self._burst_passive_image_contexts(
            prepared,
            payload=payload,
            now=now,
        )
        if not has_shared_content(payload) and not burst_contexts:
            return

        passive_payload, active_payload = self._split_passive_images(payload)
        passive_contexts: tuple[LiveMediaContext, ...] = burst_contexts
        passive_cache_hits = burst_cache_hits
        passive_reason = "conversation_burst_visible_image_attachment" if burst_contexts else ""

        if passive_payload is not None:
            passive_result = await self._media_result_for_payload(
                prepared,
                payload=passive_payload,
                scope="passive-images",
                now=now,
            )
            current_contexts = tuple(
                item for item in passive_result.contexts if item.kind == "image"
            )
            passive_contexts = tuple((*passive_contexts, *current_contexts)[:5])
            passive_cache_hits += passive_result.cache_hits
            passive_reason = passive_result.reason or passive_reason
            if current_contexts and memory_service is not None:
                memory_service.remember_perceived(
                    owner_id=deployment.owner_id,
                    deployment_id=deployment.id,
                    character_card_id=resolved.card.id,
                    payload=passive_payload,
                    contexts=current_contexts,
                )
            if not current_contexts and not burst_contexts:
                self._inject_guidance(
                    prepared,
                    _passive_image_unavailable_guidance(passive_payload),
                )

        if passive_contexts:
            self._inject_guidance(prepared, _passive_image_guidance(passive_contexts))

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

        dependency = resolve_media_dependency(text=payload.text, has_media=True)
        if dependency.dependency == "required":
            required_result = await self._media_result_for_payload(
                prepared,
                payload=active_payload,
                scope="required-active-media",
                now=now,
            )
            required_contexts = tuple(required_result.contexts)
            if required_contexts:
                self._inject_guidance(prepared, media_prompt_guidance(required_contexts))
                if memory_service is not None:
                    memory_service.remember_perceived(
                        owner_id=deployment.owner_id,
                        deployment_id=deployment.id,
                        character_card_id=resolved.card.id,
                        payload=active_payload,
                        contexts=required_contexts,
                    )
            else:
                self._inject_guidance(
                    prepared,
                    (
                        "Required media perception:",
                        (
                            "Runtime could not obtain reliable content for media that the user "
                            "asked you to inspect."
                        ),
                        (
                            "Do not invent unseen details. Respond honestly from the visible "
                            "conversation only."
                        ),
                    ),
                )
            total_count = len(passive_contexts) + len(required_contexts)
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="perceived" if total_count else "unavailable",
                    attention_action="required",
                    attention_reason=dependency.reason,
                    response_stance="truthful" if total_count else "neutral",
                    stance_reason=(
                        "Runtime resolved epistemically required media before Character generation."
                    ),
                    context_count=total_count,
                    cache_hits=passive_cache_hits + required_result.cache_hits,
                    media_result_reason=required_result.reason,
                ),
            )
            return

        if dependency.dependency == "optional":
            # Optional inspection remains Character-driven. Planner-only descriptors are never
            # injected here, so Runtime knowledge does not become Character perception.
            self._inject_guidance(prepared, _active_media_choice_guidance())

        if passive_payload is not None:
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="perceived" if passive_contexts else "unavailable",
                    attention_action="passive",
                    attention_reason="visible_image_attachment",
                    response_stance="truthful" if passive_contexts else "neutral",
                    stance_reason=(
                        "Visible image perception is already grounded; other shared content has "
                        "not been inspected yet."
                    ),
                    context_count=len(passive_contexts),
                    cache_hits=passive_cache_hits,
                    media_result_reason=passive_reason,
                ),
            )

    def _apply_media_inspection_result(
        self,
        prepared: PreparedCharacterTurn,
        result: LiveMediaResult,
    ) -> None:
        resolved = prepared.resolved
        deployment = resolved.deployment
        key = (deployment.id, resolved.payload.message_id)
        now = monotonic()
        previous = self._current_epistemic(key)
        base_count = previous.context_count if previous is not None else 0
        base_cache_hits = previous.cache_hits if previous is not None else 0
        active_payload = self._active_shared_payload(resolved.payload)
        active_contexts = tuple(result.contexts)

        if active_contexts and active_payload is not None:
            memory_service = self.conversation_media_service
            if memory_service is not None:
                memory_service.remember_perceived(
                    owner_id=deployment.owner_id,
                    deployment_id=deployment.id,
                    character_card_id=resolved.card.id,
                    payload=active_payload,
                    contexts=active_contexts,
                )

        perceived = bool(active_contexts)
        self._record_epistemic(
            key,
            now,
            MediaEpistemicSnapshot(
                state=("perceived" if perceived or base_count > 0 else "unavailable"),
                attention_action="watch",
                attention_reason="Character requested media inspection before final output.",
                response_stance="neutral",
                stance_reason=(
                    "No separate Media Attention model pass; final social behavior is decided by "
                    "the Character model after the Tool result."
                ),
                context_count=base_count + len(active_contexts),
                cache_hits=base_cache_hits + result.cache_hits,
                media_result_reason=result.reason,
            ),
        )

    def _record_failed_media_tool(self, prepared: PreparedCharacterTurn) -> None:
        resolved = prepared.resolved
        key = (resolved.deployment.id, resolved.payload.message_id)
        previous = self._current_epistemic(key)
        self._record_epistemic(
            key,
            monotonic(),
            MediaEpistemicSnapshot(
                state=("perceived" if previous and previous.context_count > 0 else "unavailable"),
                attention_action="watch",
                attention_reason="Character requested media inspection before final output.",
                response_stance="neutral",
                stance_reason="Media inspection Tool did not complete successfully.",
                context_count=previous.context_count if previous else 0,
                cache_hits=previous.cache_hits if previous else 0,
                media_result_reason="media_inspect_tool_failed",
            ),
        )

    def _finalize_media_epistemic(
        self,
        prepared: PreparedCharacterTurn,
        output: ResolvedCharacterOutput,
    ) -> None:
        if self._active_shared_payload(prepared.resolved.payload) is None:
            return
        key = (
            prepared.resolved.deployment.id,
            prepared.resolved.payload.message_id,
        )
        traces = output.tool_traces
        if any(item.tool_id == _MEDIA_INSPECT_TOOL_ID for item in traces):
            if self._current_epistemic(key) is None:
                self._record_failed_media_tool(prepared)
            return

        previous = self._current_epistemic(key)
        if previous is not None and previous.attention_action == "required":
            return
        passive_count = previous.context_count if previous is not None else 0
        passive_cache_hits = previous.cache_hits if previous is not None else 0
        self._record_epistemic(
            key,
            monotonic(),
            MediaEpistemicSnapshot(
                state="perceived" if passive_count > 0 else "skipped",
                attention_action="skip",
                attention_reason=(
                    "Character completed the turn without requesting media inspection."
                ),
                response_stance="neutral",
                stance_reason=(
                    "No separate Media Attention model pass; the Character chose its final action "
                    "without opening the unseen content."
                ),
                context_count=passive_count,
                cache_hits=passive_cache_hits,
                media_result_reason=(
                    "passive_image_perceived_active_skipped"
                    if passive_count > 0
                    else "active_content_not_inspected"
                ),
            ),
        )

    def _current_epistemic(
        self,
        key: tuple[str, str],
    ) -> MediaEpistemicSnapshot | None:
        cached = self._media_epistemic_states.get(key)
        if cached is None or cached[0] <= monotonic():
            return None
        return cached[1]

    def epistemic_trace_metadata(
        self,
        prepared: PreparedCharacterTurn,
    ) -> tuple[tuple[str, str], ...]:
        resolved = prepared.resolved
        key = (resolved.deployment.id, resolved.payload.message_id)
        snapshot = self._current_epistemic(key)
        if snapshot is None:
            return ()
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
            "Character media inspection choice:",
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
                prepared.prompt[: -len(final_line)].rstrip() + "\n" + block + "\n" + final_line
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
