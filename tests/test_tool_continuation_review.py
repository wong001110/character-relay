"""Runtime-level regression coverage for the R04/R05 continuation path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.character_prompts import CharacterPromptProfile
from echo_masque.config import Settings
from echo_masque.connector_runtime import (
    ConnectorRuntimeError,
    DiscordConnectorRuntime,
    PreparedCharacterTurn,
)
from echo_masque.credentials import CredentialStore
from echo_masque.pending_actions_v3 import PendingActionService
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.database import Database
from echo_masque.providers import (
    ChatToolCall,
    ChatToolDefinition,
    ChatToolFunction,
    ChatToolFunctionCall,
    ProviderCompletion,
)
from echo_masque.smart_output import SmartOutputContext
from echo_masque.targets import PromptModelConfig, PromptModelTarget
from echo_masque.tool_runtime import (
    ToolCatalogItem,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolExecutionTrace,
)


class ImageRegistry:
    def __init__(self, *, available: bool) -> None:
        self.available = available
        self.schema = ChatToolDefinition(
            function=ChatToolFunction(
                name="image_generate",
                description="Generate one image.",
                parameters={"type": "object"},
            )
        )

    def catalog(self) -> tuple[ToolCatalogItem, ...]:
        return (
            ToolCatalogItem(
                id="image.generate",
                display_name="Generate image",
                description="Create an image.",
                category="image",
                operation="write",
                risk="medium",
                side_effect=True,
                provider_function_name="image_generate",
                available=self.available,
                availability_reason=(
                    "Image provider is not configured." if not self.available else ""
                ),
            ),
        )

    def provider_tools(self, ids: tuple[str, ...]) -> tuple[ChatToolDefinition, ...]:
        return (self.schema,) if self.available and "image.generate" in ids else ()

    def is_side_effect_call(self, call: ChatToolCall) -> bool:
        return call.function.name == "image_generate"

    async def execute(self, call: ChatToolCall, **_: object) -> ToolExecutionResult:
        assert call.function.name == "image_generate"
        return ToolExecutionResult(
            content='{"ok":true,"artifact_id":"artifact-1"}',
            trace=ToolExecutionTrace(tool_id="image.generate", status="completed"),
        )


class ContinuationProvider:
    def __init__(self) -> None:
        self.rounds = 0
        self.visible_tool_names: list[str] = []

    async def complete(self, **_: object) -> ProviderCompletion:
        raise AssertionError("Continuation should retain the available assigned tool.")

    async def complete_with_tools(
        self,
        *,
        tools: tuple[ChatToolDefinition, ...],
        model: str,
        **_: object,
    ) -> ProviderCompletion:
        self.rounds += 1
        self.visible_tool_names = [item.function.name for item in tools]
        if self.rounds == 1:
            return ProviderCompletion(
                text="",
                model=model,
                latency_ms=1,
                finish_reason="tool_calls",
                tool_calls=(
                    ChatToolCall(
                        id="retry-image",
                        function=ChatToolFunctionCall(
                            name="image_generate",
                            arguments=json.dumps({"prompt": "a lighthouse at dusk"}),
                        ),
                    ),
                ),
            )
        return ProviderCompletion(
            text='[[CR_OUTPUT {"action":"message","content":[{"text":"Done"}]}]]',
            model=model,
            latency_ms=1,
            finish_reason="stop",
        )


def _payload(
    *, message_id: str, author_id: str, text: str, reply_to: str = ""
) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id=message_id,
        guild_id="guild-1",
        channel_id="channel-1",
        author_id=author_id,
        author_display_name="Member",
        text=text,
        mentioned_bot=True,
        reply_to_message_id=reply_to,
    )


def _prepared(
    payload: DiscordInboundMessage,
    target: PromptModelTarget,
    *,
    conversation_thread_id: str = "",
) -> PreparedCharacterTurn:
    deployment = SimpleNamespace(id="deployment-1", owner_id="owner-1", platform="discord")
    card = SimpleNamespace(id="card-1", display_name="Ann", subtitle="Companion")
    resolved = SimpleNamespace(
        payload=payload,
        deployment=deployment,
        card=card,
        target=target,
        target_record=SimpleNamespace(target_kind="prompt_model"),
    )
    return PreparedCharacterTurn(
        resolved=cast(Any, resolved),
        turn_context=None,
        context_bundle=(
            SimpleNamespace(
                thread=SimpleNamespace(id=conversation_thread_id),
                segment=None,
            )
            if conversation_thread_id
            else None
        ),
        context_error="",
        smart_context=SmartOutputContext.from_payload(payload, character_name="Ann"),
        prompt="Reply as Ann. Return Smart Output now.",
        prompt_manifest={},
        enabled_tools=("image.generate",),
        tool_context=ToolExecutionContext(
            owner_id="owner-1",
            deployment_id="deployment-1",
            character_card_id="card-1",
            platform="discord",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="channel-1",
            message_id=payload.message_id,
            trigger_text=payload.text,
            initiator_user_id=payload.author_id,
        ),
    )


def _target(provider: object) -> PromptModelTarget:
    return PromptModelTarget(
        config=PromptModelConfig(
            name="Ann target",
            model="test-model",
            system_prompt="Be Ann.",
            base_url="https://provider.invalid",
        ),
        provider=cast(Any, provider),
    )


def _service() -> PendingActionService:
    database = Database("sqlite://")
    database.initialize()
    return PendingActionService(ConversationRuntimeRepository(database))


def test_app_runtime_retries_unique_pending_tool_without_current_tool_keyword(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'continuation.db'}",
            browser_tools_enabled=False,
            semantic_participation_enabled=False,
            legacy_local_user_enabled=False,
        )
    )
    runtime = app.state.discord_connector_runtime
    service = app.state.pending_action_service
    assert runtime.pending_action_service is service
    registry = ImageRegistry(available=False)
    runtime.tool_registry = cast(Any, registry)

    original = _prepared(
        _payload(
            message_id="source-request",
            author_id="member-1",
            text="Generate an image of a lighthouse at dusk.",
        ),
        _target(ContinuationProvider()),
        conversation_thread_id="thread-1",
    )
    runtime._prepare_pending_action(original)
    actions = service.repository.active_pending_actions(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        requested_by_user_id="member-1",
        target_character_card_id="card-1",
        deployment_id="deployment-1",
    )
    assert len(actions) == 1
    assert actions[0].state == "blocked_unavailable"

    # A different member cannot take over the same reply-anchored action.
    registry.available = True
    other_member = _prepared(
        _payload(
            message_id="other-retry",
            author_id="member-2",
            text="go ahead",
        ),
        _target(ContinuationProvider()),
        conversation_thread_id="thread-1",
    )
    runtime._prepare_pending_action(other_member)
    assert other_member.pending_action is None

    provider = ContinuationProvider()
    retry = _prepared(
        _payload(
            message_id="retry-request",
            author_id="member-1",
            text="go ahead",
        ),
        _target(provider),
        conversation_thread_id="thread-1",
    )
    runtime._prepare_pending_action(retry)
    assert retry.pending_action is not None
    assert retry.pending_action.tool_id == "image.generate"
    assert runtime._forced_tool_ids(retry) == ("image.generate",)

    # The conditional claim turns the action non-resumable before the first
    # provider call. A concurrent retry therefore receives no ordinary schema
    # even though semantic tool selection is disabled and normally falls back
    # to every assigned tool.
    competing_provider = ContinuationProvider()
    competing_retry = _prepared(
        _payload(
            message_id="competing-retry",
            author_id="member-1",
            text="go ahead",
        ),
        _target(competing_provider),
        conversation_thread_id="thread-1",
    )
    runtime._prepare_pending_action(competing_retry)
    assert competing_retry.pending_action is None
    assert competing_retry.suppressed_side_effect_tool_ids == ("image.generate",)
    assert runtime._enabled_tools_for_turn(competing_retry) == ()
    assert asyncio.run(runtime.start_character_tool_turn(competing_retry)) is None
    assert competing_provider.visible_tool_names == []

    turn = asyncio.run(runtime.start_character_tool_turn(retry))
    assert turn is not None
    assert asyncio.run(runtime.advance_character_tool_model(retry, turn)) is None
    assert asyncio.run(runtime.execute_character_tools(retry, turn)) == 1
    response = asyncio.run(runtime.advance_character_tool_model(retry, turn))
    assert response is not None
    asyncio.run(runtime.resolve_character_output(retry, response))

    assert provider.visible_tool_names == ["image_generate"]
    action = service.repository.pending_action(owner_id="owner-1", action_id=actions[0].id)
    assert action is not None
    assert action.state == "completed"


def test_app_runtime_cancellation_suppresses_an_explicit_tool_request_this_turn(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'cancel-continuation.db'}",
            browser_tools_enabled=False,
            semantic_participation_enabled=False,
            legacy_local_user_enabled=False,
        )
    )
    runtime = app.state.discord_connector_runtime
    service = app.state.pending_action_service
    registry = ImageRegistry(available=False)
    runtime.tool_registry = cast(Any, registry)

    source = _prepared(
        _payload(
            message_id="cancel-source",
            author_id="member-1",
            text="Generate an image of a lighthouse at dusk.",
        ),
        _target(ContinuationProvider()),
        conversation_thread_id="thread-1",
    )
    runtime._prepare_pending_action(source)
    actions = service.repository.active_pending_actions(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        requested_by_user_id="member-1",
        target_character_card_id="card-1",
        deployment_id="deployment-1",
    )
    assert len(actions) == 1

    registry.available = True
    provider = ContinuationProvider()
    cancelled = _prepared(
        _payload(
            message_id="cancel-request",
            author_id="member-1",
            text="Cancel that; generate an image anyway.",
            reply_to="cancel-source",
        ),
        _target(provider),
        conversation_thread_id="thread-1",
    )
    runtime._prepare_pending_action(cancelled)

    assert cancelled.pending_action is not None
    assert cancelled.pending_action.source == "cancelled"
    assert cancelled.suppressed_side_effect_tool_ids == ("image.generate",)
    assert runtime._enabled_tools_for_turn(cancelled) == ()
    assert asyncio.run(runtime.start_character_tool_turn(cancelled)) is None
    assert provider.visible_tool_names == []
    action = service.repository.pending_action(owner_id="owner-1", action_id=actions[0].id)
    assert action is not None
    assert action.state == "cancelled"


def test_connector_requires_stored_credential_even_when_target_names_an_environment_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALLER_CONTROLLED_PROVIDER_KEY", "must-not-be-read")
    invoked = False

    def provider_factory(*_: object) -> object:
        nonlocal invoked
        invoked = True
        return object()

    runtime = DiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, object()),
        CredentialStore(),
        provider_factory=provider_factory,
    )
    config = PromptModelConfig(
        name="Caller controlled target",
        model="test-model",
        system_prompt="Be safe.",
        base_url="https://provider.invalid",
        api_key_env="CALLER_CONTROLLED_PROVIDER_KEY",
    )

    with pytest.raises(ConnectorRuntimeError, match="needs a provider credential"):
        runtime._target(
            target_kind="prompt_model",
            target_name="Caller controlled target",
            config_json=config.model_dump_json(),
            owner_id="owner-1",
            character_card_id="card-1",
            character_profile=CharacterPromptProfile(display_name="Ann"),
        )
    assert not invoked
