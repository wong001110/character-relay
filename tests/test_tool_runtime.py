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


def test_registry_only_exposes_manually_enabled_tools() -> None:
    registry = default_tool_registry()
    schemas = registry.provider_tools(("utility.calculator",))

    assert [item.function.name for item in schemas] == ["utility_calculator"]
    assert {item.id for item in registry.catalog()} == {
        "utility.calculator",
        "utility.current_time",
    }


def test_calculator_executes_safe_arithmetic() -> None:
    result = default_tool_registry().execute(
        call("utility_calculator", {"expression": "(8 * 0.27) + 2"}),
        enabled_tool_ids=("utility.calculator",),
        context=context(),
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["ok"] is True
    assert payload["result"] == 4.16


def test_calculator_rejects_code_and_function_calls() -> None:
    result = default_tool_registry().execute(
        call("utility_calculator", {"expression": "__import__('os').system('whoami')"}),
        enabled_tool_ids=("utility.calculator",),
        context=context(),
    )

    assert result.trace.status == "rejected"
    assert json.loads(result.content)["ok"] is False


def test_current_time_returns_requested_timezone() -> None:
    result = default_tool_registry().execute(
        call("utility_current_time", {"timezone": "Asia/Kuala_Lumpur"}),
        enabled_tool_ids=("utility.current_time",),
        context=context(),
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["timezone"] == "Asia/Kuala_Lumpur"
    assert payload["utc_offset"] == "+08:00"


def test_runtime_rejects_tool_not_assigned_to_deployment() -> None:
    result = default_tool_registry().execute(
        call("utility_current_time", {"timezone": "UTC"}),
        enabled_tool_ids=("utility.calculator",),
        context=context(),
    )

    assert result.trace.status == "rejected"
    assert result.trace.error == "tool_not_assigned_to_deployment"
