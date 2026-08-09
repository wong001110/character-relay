import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from echo_masque.providers import (
    ChatMessage,
    ChatToolDefinition,
    ChatToolFunction,
    OpenAICompatibleProvider,
)
from echo_masque.providers.errors import ProviderProtocolError
from echo_masque.providers.trace import configure_provider_trace_sink


def _completion(content: str, *, completion_tokens: int = 5) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "message": {"content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": completion_tokens,
            },
        },
    )


def _run(provider: OpenAICompatibleProvider) -> Any:
    return asyncio.run(
        provider.complete(
            messages=(ChatMessage(role="user", content="Hello"),),
            model="deepseek-v4-flash",
            temperature=0.4,
        )
    )


def _run_tools(provider: OpenAICompatibleProvider) -> Any:
    return asyncio.run(
        provider.complete_with_tools(
            messages=(ChatMessage(role="user", content="What is 8 * 0.27?"),),
            model="deepseek-v4-flash",
            temperature=0.4,
            tools=(
                ChatToolDefinition(
                    function=ChatToolFunction(
                        name="utility_calculator",
                        description="Calculate arithmetic.",
                        parameters={
                            "type": "object",
                            "properties": {"expression": {"type": "string"}},
                            "required": ["expression"],
                        },
                    )
                ),
            ),
        )
    )


def test_deepseek_request_explicitly_disables_thinking() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["temperature"] == 0.4
        return _completion("Visible answer")

    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com",
        api_key=SecretStr("secret"),
        transport=httpx.MockTransport(handler),
    )

    completion = _run(provider)
    assert completion.text == "Visible answer"


def test_non_deepseek_provider_does_not_receive_thinking_extension() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "thinking" not in payload
        return _completion("Generic provider answer")

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key=SecretStr("secret"),
        transport=httpx.MockTransport(handler),
    )

    completion = _run(provider)
    assert completion.text == "Generic provider answer"


def test_native_tool_call_allows_null_content_and_preserves_call() -> None:
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tool_choice"] == "auto"
        assert payload["tools"][0]["function"]["name"] == "utility_calculator"
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "utility_calculator",
                                        "arguments": '{"expression":"8 * 0.27"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 24, "completion_tokens": 12},
            },
        )

    try:
        provider = OpenAICompatibleProvider(
            base_url="https://api.deepseek.com",
            api_key=SecretStr("secret"),
            transport=httpx.MockTransport(handler),
        )
        completion = _run_tools(provider)
    finally:
        configure_provider_trace_sink(None)

    assert completion.text == ""
    assert completion.finish_reason == "tool_calls"
    assert completion.tool_calls[0].function.name == "utility_calculator"
    request_event = next(item for item in events if item["event"] == "provider.request")
    response_event = next(item for item in events if item["event"] == "provider.response")
    assert request_event["available_tool_names"] == ["utility_calculator"]
    assert response_event["tool_call_names"] == ["utility_calculator"]


def test_empty_content_is_retried_before_returning_success(monkeypatch: Any) -> None:
    monkeypatch.setenv("ECHO_MASQUE_PROVIDER_TRACE_MODE", "summary")
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        assert payload["thinking"] == {"type": "disabled"}
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "model": "deepseek-v4-flash",
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": "Internal reasoning only",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 49},
                },
            )
        return _completion("Recovered visible answer", completion_tokens=8)

    try:
        provider = OpenAICompatibleProvider(
            base_url="https://api.deepseek.com",
            api_key=SecretStr("secret"),
            max_retries=1,
            transport=httpx.MockTransport(handler),
        )
        completion = _run(provider)
    finally:
        configure_provider_trace_sink(None)

    assert calls == 2
    assert completion.text == "Recovered visible answer"
    retry = next(item for item in events if item["event"] == "provider.retry")
    assert retry["reason"] == "empty_content"
    response = next(item for item in events if item["event"] == "provider.response")
    assert response["response_text"] == "Recovered visible answer"
    assert response["response_chars"] == len("Recovered visible answer")


def test_repeated_empty_content_raises_protocol_error() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {
                            "content": "   ",
                            "reasoning_content": "Reasoning without final answer",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 49},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com/v1",
        api_key=SecretStr("secret"),
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(
        ProviderProtocolError,
        match="empty chat-completion content",
    ):
        _run(provider)
    assert calls == 2
