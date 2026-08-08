import asyncio
import json

from echo_masque.providers import (
    ChatMessage,
    ChatToolCall,
    ChatToolDefinition,
    ChatToolFunctionCall,
    ProviderCompletion,
)
from echo_masque.targets import PromptModelConfig, PromptModelTarget
from echo_masque.tool_runtime import ToolExecutionContext, default_tool_registry


class FakeToolProvider:
    def __init__(self) -> None:
        self.tool_rounds = 0
        self.final_without_tools = 0
        self.seen_tool_result = ""

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        del messages, temperature
        self.final_without_tools += 1
        return ProviderCompletion(
            text="Forced final answer",
            model=model,
            latency_ms=2,
            finish_reason="stop",
        )

    async def complete_with_tools(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
    ) -> ProviderCompletion:
        del temperature
        self.tool_rounds += 1
        assert [item.function.name for item in tools] == ["utility_calculator"]
        if self.tool_rounds == 1:
            return ProviderCompletion(
                text="",
                model=model,
                latency_ms=3,
                finish_reason="tool_calls",
                tool_calls=(
                    ChatToolCall(
                        id="call-calc",
                        function=ChatToolFunctionCall(
                            name="utility_calculator",
                            arguments=json.dumps({"expression": "8 * 0.27"}),
                        ),
                    ),
                ),
            )

        tool_message = next(item for item in reversed(messages) if item.role == "tool")
        self.seen_tool_result = tool_message.content
        payload = json.loads(tool_message.content)
        assert payload["result"] == 2.16
        return ProviderCompletion(
            text="The exact result is 2.16.",
            model=model,
            latency_ms=4,
            finish_reason="stop",
        )


def test_prompt_model_executes_tool_and_returns_final_response() -> None:
    provider = FakeToolProvider()
    target = PromptModelTarget(
        config=PromptModelConfig(
            name="Tool Character",
            provider="deepseek",
            model="deepseek-v4-flash",
            system_prompt="Stay concise.",
            base_url="https://api.deepseek.com",
            temperature=0.2,
        ),
        provider=provider,
    )

    response = asyncio.run(
        target.send_with_tools(
            "What is 8 * 0.27?",
            tool_registry=default_tool_registry(),
            enabled_tool_ids=("utility.calculator",),
            tool_context=ToolExecutionContext(
                owner_id="owner-1",
                deployment_id="deployment-1",
                character_card_id="character-1",
                platform="discord",
            ),
            max_tool_rounds=2,
        )
    )

    assert response.text == "The exact result is 2.16."
    assert response.latency_ms == 7
    assert provider.tool_rounds == 2
    assert provider.final_without_tools == 0
    assert provider.seen_tool_result
    traces = response.trace["tool_calls"]
    assert isinstance(traces, list)
    assert traces[0]["tool_id"] == "utility.calculator"
    assert traces[0]["status"] == "completed"


def test_prompt_model_forces_final_response_after_tool_round_limit() -> None:
    class AlwaysCallsToolProvider(FakeToolProvider):
        async def complete_with_tools(
            self,
            *,
            messages: tuple[ChatMessage, ...],
            model: str,
            temperature: float,
            tools: tuple[ChatToolDefinition, ...],
        ) -> ProviderCompletion:
            del messages, temperature, tools
            self.tool_rounds += 1
            return ProviderCompletion(
                text="",
                model=model,
                latency_ms=1,
                finish_reason="tool_calls",
                tool_calls=(
                    ChatToolCall(
                        id=f"call-{self.tool_rounds}",
                        function=ChatToolFunctionCall(
                            name="utility_calculator",
                            arguments='{"expression":"1 + 1"}',
                        ),
                    ),
                ),
            )

    provider = AlwaysCallsToolProvider()
    target = PromptModelTarget(
        config=PromptModelConfig(
            name="Bounded Character",
            provider="deepseek",
            model="deepseek-v4-flash",
            system_prompt="Stay concise.",
            base_url="https://api.deepseek.com",
        ),
        provider=provider,
    )

    response = asyncio.run(
        target.send_with_tools(
            "Keep using tools forever.",
            tool_registry=default_tool_registry(),
            enabled_tool_ids=("utility.calculator",),
            tool_context=ToolExecutionContext(
                owner_id="owner-1",
                deployment_id="deployment-1",
                character_card_id="character-1",
                platform="discord",
            ),
            max_tool_rounds=2,
        )
    )

    assert provider.tool_rounds == 2
    assert provider.final_without_tools == 1
    assert response.text == "Forced final answer"
