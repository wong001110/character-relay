import asyncio
import json

import httpx
from pydantic import SecretStr

from echo_masque.providers import (
    ChatMessage,
    MockChatProvider,
    OpenAICompatibleProvider,
    ProviderAuthenticationError,
    ProviderTimeoutError,
)
from echo_masque.targets import PromptModelConfig, PromptModelTarget


def config() -> PromptModelConfig:
    return PromptModelConfig(
        name="Ann via model",
        model="demo-model",
        system_prompt="You are Ann.",
        base_url="https://models.example/v1",
    )


def test_prompt_target_keeps_history_and_resets() -> None:
    async def run() -> None:
        provider = MockChatProvider()
        target = PromptModelTarget(config=config(), provider=provider)
        first = await target.send("Hello")
        assert first.text == "Echo: Hello"
        assert [message.role for message in target.history] == ["system", "user", "assistant"]
        await target.reset()
        assert len(target.history) == 1
        assert target.history[0].content == "You are Ann."

    asyncio.run(run())


def test_openai_compatible_request_and_usage() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "served-model",
                "choices": [
                    {"message": {"content": "I am Ann."}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    async def run() -> None:
        provider = OpenAICompatibleProvider(
            base_url="https://models.example/v1",
            api_key=SecretStr("top-secret"),
            transport=httpx.MockTransport(handler),
        )
        result = await provider.complete(
            messages=(ChatMessage(role="user", content="Who are you?"),),
            model="demo-model",
            temperature=0.2,
        )
        assert result.text == "I am Ann."
        assert result.input_tokens == 12
        assert result.output_tokens == 4
        assert captured["authorization"] == "Bearer top-secret"
        assert "top-secret" not in repr(provider)

    asyncio.run(run())


def test_authentication_error_does_not_echo_secret() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    async def run() -> None:
        provider = OpenAICompatibleProvider(
            base_url="https://models.example",
            api_key=SecretStr("top-secret"),
            transport=httpx.MockTransport(handler),
        )
        try:
            await provider.complete(
                messages=(ChatMessage(role="user", content="test"),),
                model="demo",
                temperature=0.0,
            )
        except ProviderAuthenticationError as exc:
            assert "top-secret" not in str(exc)
        else:
            raise AssertionError("authentication error expected")

    asyncio.run(run())


def test_full_read_timeout_is_terminal_and_raises_explicit_error() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("slow", request=request)

    async def run() -> None:
        provider = OpenAICompatibleProvider(
            base_url="https://models.example",
            api_key=SecretStr("secret"),
            max_retries=1,
            transport=httpx.MockTransport(handler),
        )
        try:
            await provider.complete(
                messages=(ChatMessage(role="user", content="test"),),
                model="demo",
                temperature=0.0,
            )
        except ProviderTimeoutError:
            pass
        else:
            raise AssertionError("timeout error expected")

    asyncio.run(run())
    assert attempts == 1
