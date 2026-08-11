"""Discord Connector Runtime extension for persona-driven shared content perception."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal

from echo_masque.connector_runtime import (
    DiscordConnectorRuntime,
    PreparedCharacterTurn,
    ResolvedCharacterOutput,
)
from echo_masque.domain import TargetResponse
from echo_masque.live_media import LiveMediaContextService, LiveMediaResult
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
MediaEpistemicState = Literal["skipped", "perceived", "unavailable"]


@dataclass(frozen=True, slots=True)
class MediaEpistemicSnapshot:
    """Runtime truth for one Character's relationship to shared content in one turn."""

    state: MediaEpistemicState
    attention_action: Literal["watch", "skip"]
    attention_reason: str
    response_stance: MediaResponseStance
    stance_reason: str
    context_count: int = 0
    cache_hits: int = 0
    media_result_reason: str = ""


class MediaAwareDiscordConnectorRuntime(DiscordConnectorRuntime):
    """Let a Character choose whether to inspect content before Media Understanding runs."""

    def __init__(
        self,
        *args: Any,
        live_media_service: LiveMediaContextService | None = None,
        media_attention_decider: MediaAttentionDecider | None = None,
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
            # Preserve test doubles and alternate injectable service implementations.
            self.live_media_service = live_media_service
        self.media_attention_decider = media_attention_decider or CharacterMediaAttentionDecider()
        self._media_turn_results: dict[tuple[str, str], tuple[float, LiveMediaResult]] = {}
        self._media_attention_results: dict[
            tuple[str, str], tuple[float, MediaAttentionDecision]
        ] = {}
        self._media_epistemic_states: dict[
            tuple[str, str], tuple[float, MediaEpistemicSnapshot]
        ] = {}

    async def invoke_character_model(
        self,
        prepared: PreparedCharacterTurn,
    ) -> TargetResponse:
        await self._ensure_media_context(prepared)
        try:
            return await super().invoke_character_model(prepared)
        except ProviderError as exc:
            # The base Runtime historically marked every model exception as a deployment
            # error. A timeout/rate-limit/provider outage is only a failed turn. Convert it
            # into a valid silent Smart Output so the Discord connector does not retry the
            # whole non-idempotent generation request.
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
            # Preserve the reason in the connector response while keeping the Discord-facing
            # action silent. This is operational state, not Character dialogue.
            output.smart_reason = f"provider_turn_failed:{provider_failure}"
        elif output.smart_reason == "smart_output_retry_failed":
            # A failed formatting-repair provider call is also turn-scoped. The original
            # answer was already produced, so it must not disable the deployment.
            deployment = prepared.resolved.deployment
            self.deployment_repository.update_deployment(
                deployment.id,
                deployment.owner_id,
                status="active",
                last_error="smart_output_retry_failed",
            )
        return output

    def _isolate_provider_failure(
        self,
        prepared: PreparedCharacterTurn,
        exc: ProviderError,
    ) -> None:
        if exc.deployment_fatal:
            # Credential rejection is persistent until configuration changes. Keep the
            # base Runtime's deployment error state, but still return a controlled silent
            # turn instead of surfacing an HTTP 502 to Discord.
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

    async def _ensure_media_context(self, prepared: PreparedCharacterTurn) -> None:
        resolved = prepared.resolved
        deployment = resolved.deployment
        payload = resolved.payload
        if not has_shared_content(payload):
            return

        key = (deployment.id, payload.message_id)
        now = monotonic()
        attention = await self._attention_for_turn(prepared, key=key, now=now)
        if attention.action == "skip":
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="skipped",
                    attention_action="skip",
                    attention_reason=attention.reason,
                    response_stance=attention.response_stance,
                    stance_reason=attention.stance_reason,
                ),
            )
            self._inject_guidance(prepared, skipped_media_guidance(payload, attention))
            return

        service = self.live_media_service
        if service is None:
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="unavailable",
                    attention_action="watch",
                    attention_reason=attention.reason,
                    response_stance=attention.response_stance,
                    stance_reason=attention.stance_reason,
                    media_result_reason="media_service_unavailable",
                ),
            )
            self._inject_guidance(prepared, unavailable_media_guidance(payload, attention))
            return

        cached = self._media_turn_results.get(key)
        if cached is not None and cached[0] > now:
            result = cached[1]
        else:
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
            self._media_turn_results[key] = (
                now + _MEDIA_RESULT_TTL_SECONDS,
                result,
            )
            self._cleanup_cache(self._media_turn_results, now)

        if not result.contexts:
            self._record_epistemic(
                key,
                now,
                MediaEpistemicSnapshot(
                    state="unavailable",
                    attention_action="watch",
                    attention_reason=attention.reason,
                    response_stance=attention.response_stance,
                    stance_reason=attention.stance_reason,
                    context_count=0,
                    cache_hits=result.cache_hits,
                    media_result_reason=result.reason,
                ),
            )
            self._inject_guidance(prepared, unavailable_media_guidance(payload, attention))
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
                context_count=len(result.contexts),
                cache_hits=result.cache_hits,
                media_result_reason=result.reason,
            ),
        )
        guidance = (
            *watched_media_guidance(result.contexts, attention),
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
        key: tuple[str, str],
        now: float,
    ) -> MediaAttentionDecision:
        cached = self._media_attention_results.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        target = prepared.resolved.target
        if not isinstance(target, PromptModelTarget):
            # Deterministic/test targets have no persona model capable of an attention decision.
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
                    payload=prepared.resolved.payload,
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
        """Return bounded Superadmin Runtime Trace metadata for the current media turn."""

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
            "Character media attention:",
            "Character media perception for this turn:",
            "Character media perception:",
        )
        if any(marker in prepared.prompt for marker in markers):
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
    def _cleanup_cache(cache: dict[tuple[str, str], Any], now: float) -> None:
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
