"""Discord Connector Runtime extension that injects shared objective media context."""

from __future__ import annotations

from time import monotonic
from typing import Any

from echo_masque.connector_runtime import DiscordConnectorRuntime, PreparedCharacterTurn
from echo_masque.domain import TargetResponse
from echo_masque.live_media import LiveMediaContextService, LiveMediaResult, media_prompt_guidance
from echo_masque.targets import PromptModelToolTurn

_MEDIA_RESULT_TTL_SECONDS = 300.0


class MediaAwareDiscordConnectorRuntime(DiscordConnectorRuntime):
    """Add lazy Media Understanding without changing Character model/provider behavior."""

    def __init__(
        self,
        *args: Any,
        live_media_service: LiveMediaContextService | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.live_media_service = live_media_service
        self._media_turn_results: dict[tuple[str, str], tuple[float, LiveMediaResult]] = {}

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
        key = (deployment.id, payload.message_id)
        now = monotonic()
        cached = self._media_turn_results.get(key)
        if cached is not None and cached[0] > now:
            result = cached[1]
        else:
            result = await service.contexts_for_turn(
                owner_id=deployment.owner_id,
                character_card_id=resolved.card.id,
                payload=payload,
            )
            self._media_turn_results[key] = (
                now + _MEDIA_RESULT_TTL_SECONDS,
                result,
            )
            if len(self._media_turn_results) > 1000:
                self._media_turn_results = {
                    item_key: value
                    for item_key, value in self._media_turn_results.items()
                    if value[0] > now
                }

        if not result.contexts:
            return
        guidance = media_prompt_guidance(result.contexts)
        if not guidance:
            return
        marker = "Shared objective content context for this turn:"
        if marker in prepared.prompt:
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
