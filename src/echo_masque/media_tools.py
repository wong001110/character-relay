"""Media creation Tool extensions for the server-aware Runtime registry."""

from __future__ import annotations

import json
from typing import Any

from echo_masque.image_creation_runtime import ImageCreationRuntimeService, ImageGenerateToolInput
from echo_masque.providers import ChatToolCall, ProviderError
from echo_masque.server_time_tools import ServerAwareToolRegistry
from echo_masque.tool_external import ExternalToolFailed, json_result
from echo_masque.tool_runtime import (
    ToolExecutionContext,
    ToolExecutionResult,
    _tool,
)


class MediaToolRegistry(ServerAwareToolRegistry):
    """Add explicitly assignable media-creation capabilities without provider coupling."""

    def __init__(
        self,
        *args: Any,
        image_creation_service: ImageCreationRuntimeService | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.image_creation_service = image_creation_service
        self._generated_by_turn: dict[tuple[str, str], tuple[str, ...]] = {}
        self._reply_reference_by_turn: dict[tuple[str, str], str] = {}
        image_available = image_creation_service is not None
        image_tool = _tool(
            tool_id="image.generate",
            display_name="Generate Image",
            description=(
                "Generate one image as a real Character side effect using the Character's assigned "
                "Image Generation Key Group. Conversation references are allowed only when that "
                "Character actually perceived the referenced image."
            ),
            category="image",
            operation="write",
            risk="medium",
            side_effect=True,
            provider_name="image_generate",
            provider_description=(
                "Create and share one image when doing so fits the Character and conversation. "
                "Describe the desired result in prompt. Runtime owns provider/model selection. "
                "Use reference_mode=current/reply/recent only for a previously perceived image."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "maxLength": 4000,
                        "description": "Content and visual direction for the image to create.",
                    },
                    "aspect_ratio": {
                        "type": "string",
                        "maxLength": 20,
                        "default": "1:1",
                    },
                    "resolution": {
                        "type": "string",
                        "maxLength": 30,
                        "default": "",
                    },
                    "reference_mode": {
                        "type": "string",
                        "enum": ["none", "current", "reply", "recent"],
                        "default": "none",
                        "description": (
                            "Optional image reference source from this Character's own perceived "
                            "conversation media."
                        ),
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            available=image_available,
            availability_reason=(
                "" if image_available else "Image Generation Runtime is not configured."
            ),
        )
        self._by_id[image_tool.catalog.id] = image_tool
        self._by_provider_name[image_tool.catalog.provider_function_name] = image_tool

    async def execute(
        self,
        call: ChatToolCall,
        *,
        enabled_tool_ids: tuple[str, ...],
        context: ToolExecutionContext,
        allow_side_effect: bool = True,
    ) -> ToolExecutionResult:
        result = await super().execute(
            call,
            enabled_tool_ids=enabled_tool_ids,
            context=context,
            allow_side_effect=allow_side_effect,
        )
        if result.trace.tool_id == "image.generate" and result.trace.status == "completed":
            try:
                payload = json.loads(result.content)
            except (json.JSONDecodeError, TypeError):
                payload = {}
            raw = payload.get("artifact_ids") if isinstance(payload, dict) else None
            if isinstance(raw, list):
                ids = tuple(str(item) for item in raw if isinstance(item, str) and item)
                if ids:
                    self._generated_by_turn[(context.deployment_id, context.message_id)] = ids[:4]
                    self._trim_turn_map(self._generated_by_turn)
        return result

    async def _execute_tool(
        self,
        tool_id: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        if tool_id != "image.generate":
            return await super()._execute_tool(tool_id, arguments, context)
        self._require_discord(context)
        if self.image_creation_service is None:
            raise ValueError("Image Generation Runtime is unavailable.")
        payload = ImageGenerateToolInput.model_validate(arguments)
        reply_to_message_id = self._reply_reference_by_turn.get(
            (context.deployment_id, context.message_id),
            "",
        )
        try:
            artifact_ids = await self.image_creation_service.generate(
                owner_id=context.owner_id,
                deployment_id=context.deployment_id,
                character_card_id=context.character_card_id,
                guild_id=context.guild_id,
                channel_id=context.channel_id,
                thread_id=context.thread_id,
                message_id=context.message_id,
                reply_to_message_id=reply_to_message_id,
                payload=payload,
            )
        except ProviderError as exc:
            # Image generation is a Tool side effect. A provider outage/timeout must fail the
            # Tool call, not disable the Character deployment or abort the whole turn.
            raise ExternalToolFailed(
                f"Image generation provider failed ({exc.reason_code})."
            ) from exc
        return json_result(
            ok=True,
            artifact_ids=list(artifact_ids),
            count=len(artifact_ids),
            delivery="Character Relay will attach the generated image after this turn.",
        )

    def set_turn_reply_reference(
        self,
        *,
        deployment_id: str,
        message_id: str,
        reply_to_message_id: str,
    ) -> None:
        key = (deployment_id, message_id)
        if reply_to_message_id:
            self._reply_reference_by_turn[key] = reply_to_message_id
        else:
            self._reply_reference_by_turn.pop(key, None)
        self._trim_turn_map(self._reply_reference_by_turn)

    def generated_artifact_ids(self, context: ToolExecutionContext) -> tuple[str, ...]:
        return self._generated_by_turn.get((context.deployment_id, context.message_id), ())

    @staticmethod
    def _trim_turn_map(values: dict[tuple[str, str], Any]) -> None:
        if len(values) <= 2000:
            return
        for stale in list(values)[:500]:
            values.pop(stale, None)


__all__ = ["MediaToolRegistry"]
