import asyncio
import json

from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.tool_runtime import (
    ToolExecutionContext,
    default_tool_registry,
)


def call(name: str, arguments: dict[str, object]) -> ChatToolCall:
    return ChatToolCall(
        id="call-1",
        function=ChatToolFunctionCall(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


def context() -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="character-1",
        platform="discord",
    )


def execute(name: str, arguments: dict[str, object], enabled: tuple[str, ...]):
    return asyncio.run(
        default_tool_registry().execute(
            call(name, arguments),
            enabled_tool_ids=enabled,
            context=context(),
        )
    )


def test_registry_only_exposes_manually_enabled_and_available_tools() -> None:
    registry = default_tool_registry()
    schemas = registry.provider_tools(("utility.calculator", "web.search"))

    assert [item.function.name for item in schemas] == ["utility_calculator"]
    assert {item.id for item in registry.catalog()} == {
        "utility.calculator",
        "utility.current_time",
        "web.search",
        "web.fetch_page",
        "discord.search_messages",
        "discord.create_poll",
        "image.search",
    }
    availability = {item.id: item.available for item in registry.catalog()}
    assert availability["utility.calculator"] is True
    assert availability["utility.current_time"] is True
    assert availability["web.fetch_page"] is True
    assert availability["web.search"] is False
    assert availability["image.search"] is False
    assert availability["discord.search_messages"] is False
    assert availability["discord.create_poll"] is False


def test_calculator_executes_safe_arithmetic() -> None:
    result = execute(
        "utility_calculator",
        {"expression": "(8 * 0.27) + 2"},
        ("utility.calculator",),
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["ok"] is True
    assert payload["result"] == 4.16


def test_calculator_rejects_code_and_function_calls() -> None:
    result = execute(
        "utility_calculator",
        {"expression": "__import__('os').system('whoami')"},
        ("utility.calculator",),
    )

    assert result.trace.status == "rejected"
    assert json.loads(result.content)["ok"] is False


def test_current_time_returns_requested_timezone() -> None:
    result = execute(
        "utility_current_time",
        {"timezone": "Asia/Kuala_Lumpur"},
        ("utility.current_time",),
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["timezone"] == "Asia/Kuala_Lumpur"
    assert payload["utc_offset"] == "+08:00"


def test_runtime_rejects_tool_not_assigned_to_deployment() -> None:
    result = execute(
        "utility_current_time",
        {"timezone": "UTC"},
        ("utility.calculator",),
    )

    assert result.trace.status == "rejected"
    assert result.trace.error == "tool_not_assigned_to_deployment"
