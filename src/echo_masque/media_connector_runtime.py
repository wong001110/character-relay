"""Discord Connector Runtime extension for persona-driven shared content perception."""

from __future__ import annotations

from time import monotonic
from typing import Any

from echo_masque.connector_runtime import DiscordConnectorRuntime, PreparedCharacterTurn
from echo_masque.domain import TargetResponse
from echo_masque.live_media import LiveMediaContextService, LiveMediaResult
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.media_attention import (
    CharacterMediaAttentionDecider,
    MediaAttentionDecider,
    MediaAttentionDecision,
    has_shared_content,
    skipped_media_guidance,
    unavailable_media_guidance,
    watched_media_guidance,
)
from echo_masque.providers.trace import provider_trace_scope
from echo_masque.targets import PromptModelTarget, PromptModelToolTurn

_MEDIA_RESULT_TTL_SECONDS = 300.0


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

    async def invoke_character_model(
        self,
        prepared: PreparedCharacterTurn,
    ) -> TargetResponse:
        await self._ensure_media_context(prepared)
        return await super().invoke_character_model(prepared)

    async def start_character_tool_turn(
        self,
        prepared: PreparedCharacterTurn,
    ) -> PromptModelToolTurn | None:
        await self._ensure_media_context(prepared)
        return await super().start_character_tool_turn(prepared)

    async def _ensure_media_context(self, prepared: PreparedCharacterTurn) -> None:
        service = self.live_media_service
        if service is None:
            return
        resolved = prepared.resolved
        deployment = resolved.deployment
        payload = resolved.payload
        if not has_shared_content(payload):
            return

        key = (deployment.id, payload.message_id)
        now = monotonic()
        attention = await self._attention_for_turn(prepared, key=key, now=now)
        if attention.action == "skip":
            self._inject_guidance(prepared, skipped_media_guidance(payload))
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
            self._inject_guidance(prepared, unavailable_media_guidance(payload))
            return
        self._inject_guidance(prepared, watched_media_guidance(result.contexts))

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
            decision = MediaAttentionDecision(action="watch", reason="non_prompt_target")
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
