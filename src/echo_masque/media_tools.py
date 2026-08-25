"""Media Tool extensions for the server-aware Runtime registry."""

from __future__ import annotations

import json
from typing import Any

from pydantic import SecretStr

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.generated_media_delivery import GeneratedMediaDeliveryService
from echo_masque.image_creation_runtime import ImageCreationRuntimeService, ImageGenerateToolInput
from echo_masque.image_generation import CANONICAL_ASPECT_RATIOS
from echo_masque.internal_context import INTERNAL_CONTEXT_TOOL_IDS, InternalContextService
from echo_masque.live_media import LiveMediaContextService, LiveMediaResult
from echo_masque.persistence import DeploymentRepository, DiscordIdentityRepository
from echo_masque.providers import ChatToolCall, ProviderError
from echo_masque.providers.trace import provider_trace_scope
from echo_masque.server_time_tools import ServerAwareToolRegistry
from echo_masque.tool_external import ExternalToolFailed, json_result
from echo_masque.tool_runtime import (
    ToolCatalogItem,
    ToolExecutionContext,
    ToolExecutionResult,
    _tool,
)

_MEDIA_INSPECT_TOOL_ID = "media.inspect"


class MediaToolRegistry(ServerAwareToolRegistry):
    """Add media creation plus one Runtime-owned shared-content inspection capability."""

    def __init__(
        self,
        *args: Any,
        image_creation_service: ImageCreationRuntimeService | None = None,
        generated_media_delivery: GeneratedMediaDeliveryService | None = None,
        internal_context_service: InternalContextService | None = None,
        **kwargs: Any,
    ) -> None:
        raw_bot_token = kwargs.get("discord_bot_token")
        super().__init__(*args, **kwargs)
        self.image_creation_service = image_creation_service
        self.internal_context_service = internal_context_service
        if generated_media_delivery is None and image_creation_service is not None:
            database = image_creation_service.artifact_repository.database
            generated_media_delivery = GeneratedMediaDeliveryService(
                image_creation_service.artifact_repository,
                DeploymentRepository(database),
                DiscordIdentityRepository(database),
                image_creation_service.credential_resolver.credential_vault,
                discord_bot_token=(
                    raw_bot_token if isinstance(raw_bot_token, SecretStr) else None
                ),
            )
        self.generated_media_delivery = generated_media_delivery
        self.live_media_service: LiveMediaContextService | None = None
        self._generated_by_turn: dict[tuple[str, str], tuple[str, ...]] = {}
        self._reply_reference_by_turn: dict[tuple[str, str], str] = {}
        self._shared_payload_by_turn: dict[
            tuple[str, str], DiscordInboundMessage
        ] = {}
        self._inspected_media_by_turn: dict[
            tuple[str, str], LiveMediaResult
        ] = {}

        inspect_tool = _tool(
            tool_id=_MEDIA_INSPECT_TOOL_ID,
            display_name="Inspect Shared Media",
            description=(
                "Privately open/watch/read the media or link in the current triggering Discord "
                "message. Runtime exposes this only for the current turn; it is not a manually "
                "assignable Deployment capability."
            ),
            category="media",
            operation="read",
            risk="low",
            side_effect=False,
            provider_name="media_inspect",
            provider_description=(
                "Inspect the shared media/link in the current triggering Discord message only "
                "when this Character genuinely wants or needs unseen content before choosing "
                "its final Discord action. Do not call merely because media exists. If the "
                "visible preview is enough, or the Character is not interested, skip this Tool "
                "and respond/ignore naturally. For the current shared media/link, prefer this "
                "Tool over generic web or file tools because it returns Runtime-grounded media "
                "observations."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
        self._by_id[inspect_tool.catalog.id] = inspect_tool
        self._by_provider_name[inspect_tool.catalog.provider_function_name] = inspect_tool

        internal_descriptions = {
            "memory.search": (
                "Search this Character's scoped durable memories relevant to a question."
            ),
            "conversation.search": (
                "Search compact past Episode projections in the current Discord location."
            ),
            "knowledge.search": (
                "Search Character-admitted Knowledge Fabric evidence in this current server only."
            ),
        }
        for tool_id in INTERNAL_CONTEXT_TOOL_IDS:
            provider_name = tool_id.replace(".", "_")
            internal_tool = _tool(
                tool_id=tool_id,
                display_name=tool_id,
                description=internal_descriptions[tool_id],
                category="internal_context",
                operation="read",
                risk="low",
                side_effect=False,
                provider_name=provider_name,
                provider_description=(
                    internal_descriptions[tool_id]
                    + " Runtime injects identity, permissions, and Discord scope; only provide "
                    "semantic query intent."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "maxLength": 800},
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 8,
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                available=internal_context_service is not None,
                availability_reason=(
                    ""
                    if internal_context_service is not None
                    else "Internal Context Runtime is unavailable."
                ),
            )
            self._by_id[internal_tool.catalog.id] = internal_tool
            self._by_provider_name[internal_tool.catalog.provider_function_name] = internal_tool

        image_available = (
            image_creation_service is not None and generated_media_delivery is not None
        )
        image_tool = _tool(
            tool_id="image.generate",
            display_name="Generate Image",
            description=(
                "Generate and deliver one image as a real Character side effect using the "
                "Character's assigned Image Generation Key Group. Conversation references are "
                "allowed only when that Character actually perceived the referenced image."
            ),
            category="image",
            operation="write",
            risk="medium",
            side_effect=True,
            provider_name="image_generate",
            provider_description=(
                "Create and share one image when doing so fits the Character and conversation. "
                "Describe the desired result in prompt. Runtime owns provider/model selection and "
                "delivers the image through this Character's Discord identity. Use "
                "reference_mode=current/reply/recent only for a previously perceived image."
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
                        "enum": list(CANONICAL_ASPECT_RATIOS),
                        "default": "1:1",
                        "description": (
                            "Canonical Character Relay image aspect ratio. Use auto only when "
                            "the provider should choose the ratio."
                        ),
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
                ""
                if image_available
                else "Image Generation or Discord media delivery Runtime is not configured."
            ),
        )
        self._by_id[image_tool.catalog.id] = image_tool
        self._by_provider_name[image_tool.catalog.provider_function_name] = image_tool

    def catalog(self) -> tuple[ToolCatalogItem, ...]:
        """Keep Runtime-owned media inspection out of manual Deployment Tool assignment."""

        hidden = {_MEDIA_INSPECT_TOOL_ID, *INTERNAL_CONTEXT_TOOL_IDS}
        return tuple(item for item in super().catalog() if item.id not in hidden)

    def internal_tool_ids(self) -> tuple[str, ...]:
        if self.internal_context_service is None:
            return ()
        return INTERNAL_CONTEXT_TOOL_IDS

    def set_live_media_service(self, service: LiveMediaContextService | None) -> None:
        self.live_media_service = service

    def set_turn_media_payload(
        self,
        *,
        deployment_id: str,
        message_id: str,
        payload: DiscordInboundMessage | None,
    ) -> None:
        key = (deployment_id, message_id)
        self._inspected_media_by_turn.pop(key, None)
        if payload is None:
            self._shared_payload_by_turn.pop(key, None)
        else:
            self._shared_payload_by_turn[key] = payload
        self._trim_turn_map(self._shared_payload_by_turn)
        self._trim_turn_map(self._inspected_media_by_turn)

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
        if tool_id == _MEDIA_INSPECT_TOOL_ID:
            return await self._inspect_shared_media(context)
        if tool_id in INTERNAL_CONTEXT_TOOL_IDS:
            if self.internal_context_service is None:
                raise ValueError("Internal Context Runtime is unavailable.")
            return self.internal_context_service.execute(tool_id, arguments, context)
        if tool_id != "image.generate":
            return await super()._execute_tool(tool_id, arguments, context)
        self._require_discord(context)
        if self.image_creation_service is None or self.generated_media_delivery is None:
            raise ValueError("Image Generation Runtime is unavailable.")
        payload = ImageGenerateToolInput.model_validate(arguments)
        reply_to_message_id = self._reply_reference_by_turn.get(
            (context.deployment_id, context.message_id),
            "",
        )
        try:
            with provider_trace_scope(
                owner_id=context.owner_id,
                deployment_id=context.deployment_id,
                character_card_id=context.character_card_id,
            ):
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
            raise ExternalToolFailed(
                f"Image generation provider failed ({exc.reason_code})."
            ) from exc

        message_ids: list[str] = []
        attachment_urls: list[str] = []
        try:
            for artifact_id in artifact_ids:
                delivered = await self.generated_media_delivery.deliver(
                    owner_id=context.owner_id,
                    deployment_id=context.deployment_id,
                    channel_id=context.channel_id,
                    thread_id=context.thread_id,
                    artifact_id=artifact_id,
                )
                message_ids.append(delivered.message_id)
                if delivered.attachment_url:
                    attachment_urls.append(delivered.attachment_url)
        except RuntimeError as exc:
            raise ExternalToolFailed(str(exc)) from exc

        return json_result(
            ok=True,
            artifact_ids=list(artifact_ids),
            discord_message_ids=message_ids,
            attachment_urls=attachment_urls,
            count=len(artifact_ids),
            delivered=True,
        )

    async def _inspect_shared_media(self, context: ToolExecutionContext) -> str:
        self._require_discord(context)
        key = (context.deployment_id, context.message_id)
        cached = self._inspected_media_by_turn.get(key)
        if cached is not None:
            return self._media_result_content(cached)

        service = self.live_media_service
        payload = self._shared_payload_by_turn.get(key)
        if service is None:
            result = LiveMediaResult(status="failed", reason="media_service_unavailable")
            self._inspected_media_by_turn[key] = result
            return self._media_result_content(result)
        if payload is None:
            result = LiveMediaResult(status="failed", reason="media_payload_unavailable")
            self._inspected_media_by_turn[key] = result
            return self._media_result_content(result)

        try:
            with provider_trace_scope(
                owner_id=context.owner_id,
                deployment_id=context.deployment_id,
                character_card_id=context.character_card_id,
                operation_id=context.operation_id,
                runtime_node="turn_tool_execution",
            ):
                result = await service.contexts_for_turn(
                    owner_id=context.owner_id,
                    character_card_id=context.character_card_id,
                    payload=payload,
                )
        except Exception as exc:
            raise ExternalToolFailed("Shared media inspection could not be completed.") from exc

        self._inspected_media_by_turn[key] = result
        self._trim_turn_map(self._inspected_media_by_turn)
        return self._media_result_content(result)

    @staticmethod
    def _media_result_content(result: LiveMediaResult) -> str:
        observations = [
            {
                "kind": item.kind,
                "label": item.label,
                "summary": item.summary[:8000],
                "visible_text": item.visible_text[:6000],
                "notable_details": list(item.notable_details[:12]),
            }
            for item in result.contexts[:2]
        ]
        perceived = bool(observations)
        return json_result(
            ok=perceived,
            perception="perceived" if perceived else "unavailable",
            reason=result.reason,
            cache_hits=result.cache_hits,
            observations=observations,
            guidance=(
                "Treat only these observations as grounded unseen-content facts. React from the "
                "Character persona; do not mention media_inspect, providers, cache, extraction, "
                "Vision, or Runtime internals. If perception is unavailable, do not invent details."
            ),
        )

    def media_inspection_result(
        self,
        context: ToolExecutionContext,
    ) -> LiveMediaResult | None:
        return self._inspected_media_by_turn.get(
            (context.deployment_id, context.message_id)
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
