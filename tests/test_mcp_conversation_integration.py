"""Exercise actual model -> registry -> progress -> connected-tool orchestration offline."""

import asyncio
import json
from typing import cast

import pytest

from echo_masque.mcp_gateway import McpGateway
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall, ProviderCompletion
from echo_masque.targets import PromptModelConfig, PromptModelTarget
from echo_masque.tool_external import ExternalToolFailed
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry
from echo_masque.turn_progress import bind_turn_progress, publish_turn_progress


def context() -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner",
        deployment_id="deployment",
        character_card_id="character",
        platform="discord",
        connection_id="connection",
        guild_id="guild",
        channel_id="channel",
        message_id="message",
        trigger_text="幫我畫一張圖",
        operation_id="operation",
        step_id="step",
    )


def call(name: str, arguments: dict[str, object]) -> ChatToolCall:
    return ChatToolCall(
        id=name, function=ChatToolFunctionCall(name=name, arguments=json.dumps(arguments))
    )


class Gateway:
    available = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.invocations = 0

    async def discover(self, arguments: dict[str, object], scope: ToolExecutionContext) -> str:
        assert scope.owner_id == "owner"
        assert arguments == {"query": "image generation"}
        await publish_turn_progress(scope.progress_message)
        self.started.set()
        await self.release.wait()
        return json.dumps(
            {"tools": [{"server_id": "art", "tool_name": "draw", "schema_fingerprint": "a" * 64}]}
        )

    async def invoke(self, arguments: dict[str, object], scope: ToolExecutionContext) -> str:
        assert "progress_message" not in arguments
        assert scope.deployment_id == "deployment"
        await publish_turn_progress(scope.progress_message)
        self.invocations += 1
        if self.fail:
            raise ExternalToolFailed("mcp_call_outcome_unknown")
        return json.dumps({"ok": True, "delivered": True, "artifact_ids": ["image"]})


class Provider:
    def __init__(self, *, retry: bool = False) -> None:
        self.round = 0
        self.retry = retry
        self.visible: list[list[str]] = []

    async def complete_with_tools(self, *, messages, model, temperature, tools):
        del messages, temperature
        self.round += 1
        self.visible.append([tool.function.name for tool in tools])
        if self.round == 1:
            tool = call(
                "mcp_discover",
                {"query": "image generation", "progress_message": "我找一下能用的工具。"},
            )
        elif self.round == 2 or self.retry:
            tool = call(
                "mcp_invoke",
                {
                    "server_id": "art",
                    "tool_name": "draw",
                    "schema_fingerprint": "a" * 64,
                    "arguments": {"prompt": "a cat"},
                    "progress_message": "找到了, 我來畫一下。",
                },
            )
        else:
            return ProviderCompletion(
                text="畫好了, 給你!", model=model, latency_ms=1, finish_reason="stop"
            )
        return ProviderCompletion(
            text="", model=model, latency_ms=1, finish_reason="tool_calls", tool_calls=(tool,)
        )

    async def complete(self, *, messages, model, temperature):
        del messages, temperature
        return ProviderCompletion(
            text="還沒辦法確認結果, 我不會重複執行。",
            model=model,
            latency_ms=1,
            finish_reason="stop",
        )


def target(provider: Provider) -> PromptModelTarget:
    return PromptModelTarget(
        config=PromptModelConfig(
            name="Character",
            model="fake",
            system_prompt="自然地聊天。",
            base_url="https://provider.example/v1",
        ),
        provider=provider,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("retry", [False, True])
def test_discovery_survives_pruning_progress_precedes_work_and_unknown_write_is_not_retried(
    monkeypatch, retry
):
    monkeypatch.setattr("echo_masque.targets.prompt_model.select_tool_ids_for_turn", lambda *_: ())

    async def run():
        gateway = Gateway(fail=retry)
        registry = ToolRegistry(mcp_gateway=cast(McpGateway, gateway))
        provider = Provider(retry=retry)
        messages: list[str] = []

        async def progress(text: str) -> bool:
            messages.append(text)
            return True

        with bind_turn_progress(progress):
            task = asyncio.create_task(
                target(provider).send_with_tools(
                    "幫我畫一張圖",
                    tool_registry=registry,
                    enabled_tool_ids=("mcp.discover", "mcp.invoke"),
                    tool_context=context(),
                )
            )
            await asyncio.wait_for(gateway.started.wait(), timeout=2)
            assert not task.done()
            assert messages == ["我找一下能用的工具。"]
            assert provider.visible[0] == ["mcp_discover"]
            gateway.release.set()
            result = await task
        assert gateway.invocations == 1
        assert messages == ["我找一下能用的工具。", "找到了, 我來畫一下。"]
        assert "mcp_invoke" in provider.visible[1]
        if retry:
            assert result.trace["tool_calls"][-1]["error"] == "side_effect_limit_reached"
        else:
            assert result.text == "畫好了, 給你!"

    asyncio.run(run())


def test_unassigned_tool_cannot_publish_progress_or_call_remote():
    async def run():
        gateway = Gateway()
        registry = ToolRegistry(mcp_gateway=cast(McpGateway, gateway))
        messages: list[str] = []

        async def progress(text: str) -> bool:
            messages.append(text)
            return True

        with bind_turn_progress(progress):
            result = await registry.execute(
                call(
                    "mcp_discover",
                    {
                        "query": "image generation",
                        "progress_message": "我找一下。",
                    },
                ),
                enabled_tool_ids=(),
                context=context(),
            )
        assert result.trace.error == "tool_not_assigned_to_deployment"
        assert not messages and not gateway.started.is_set()

    asyncio.run(run())


def test_progress_is_required_only_for_async_turn_and_not_forwarded_or_replayed():
    class Store:
        def __init__(self):
            self.hashes: list[str] = []
            self.result = None

        def claim_side_effect(self, **kwargs):
            self.hashes.append(kwargs["arguments_hash"])
            return (
                ("granted", "key", "", {})
                if self.result is None
                else (
                    "replay",
                    "key",
                    self.result[0],
                    self.result[1],
                )
            )

        def complete_side_effect(self, **kwargs):
            self.result = (kwargs["content"], kwargs["trace"])

        def release_side_effect_claim(self, **kwargs):
            raise AssertionError("Successful call must not release its claim")

    async def run():
        gateway = Gateway()
        store = Store()
        registry = ToolRegistry(mcp_gateway=cast(McpGateway, gateway), side_effect_store=store)
        schema = registry.provider_tools(("mcp.invoke",))[0]
        assert "progress_message" not in schema.function.parameters["properties"]
        messages: list[str] = []

        async def progress(text: str) -> bool:
            messages.append(text)
            return True

        arguments = {
            "server_id": "art",
            "tool_name": "draw",
            "schema_fingerprint": "a" * 64,
            "arguments": {"prompt": "a cat"},
        }
        with bind_turn_progress(progress):
            missing = await registry.execute(
                call("mcp_invoke", arguments), enabled_tool_ids=("mcp.invoke",), context=context()
            )
            assert missing.trace.status == "rejected" and gateway.invocations == 0
            for text in ["我來畫一下。", "再說一次進度。"]:
                result = await registry.execute(
                    call("mcp_invoke", {**arguments, "progress_message": text}),
                    enabled_tool_ids=("mcp.invoke",),
                    context=context(),
                )
                assert result.trace.status == "completed"
        assert gateway.invocations == 1
        assert messages == ["我來畫一下。"]
        assert len(store.hashes) == 2 and store.hashes[0] == store.hashes[1]

    asyncio.run(run())
