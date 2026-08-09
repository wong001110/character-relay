import asyncio
import json
import logging
from typing import Any

import httpx
from pydantic import SecretStr

from echo_masque.providers import ChatMessage, OpenAICompatibleProvider
from echo_masque.providers.trace import (
    configure_provider_trace_sink,
    provider_trace_scope,
)


def test_provider_trace_uses_private_sink_without_process_logs(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    monkeypatch.setenv("ECHO_MASQUE_PROVIDER_TRACE_MODE", "summary")
    monkeypatch.setenv("ECHO_MASQUE_PROVIDER_TRACE_MAX_CHARS", "1000")
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer deepseek-secret-key"
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {"content": "Ning response from DeepSeek."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 21, "completion_tokens": 7},
            },
        )

    try:
        provider = OpenAICompatibleProvider(
            base_url="https://api.deepseek.com",
            api_key=SecretStr("deepseek-secret-key"),
            transport=httpx.MockTransport(handler),
        )
        with provider_trace_scope(
            owner_id="owner-1",
            deployment_id="deployment-1",
            character_card_id="character-1",
        ):
            completion = asyncio.run(
                provider.complete(
                    messages=(
                        ChatMessage(role="system", content="PRIVATE SYSTEM PROMPT"),
                        ChatMessage(role="user", content="Ning, are you there?"),
                    ),
                    model="deepseek-v4-flash",
                    temperature=0.4,
                )
            )
    finally:
        configure_provider_trace_sink(None)

    assert completion.text == "Ning response from DeepSeek."
    request_event = next(item for item in events if item["event"] == "provider.request")
    response_event = next(item for item in events if item["event"] == "provider.response")
    assert request_event["endpoint"] == "https://api.deepseek.com/v1/chat/completions"
    assert request_event["latest_message"] == {
        "role": "user",
        "content": "Ning, are you there?",
    }
    assert request_event["owner_id"] == "owner-1"
    assert request_event["deployment_id"] == "deployment-1"
    assert request_event["character_card_id"] == "character-1"
    assert response_event["owner_id"] == "owner-1"
    assert "PRIVATE SYSTEM PROMPT" not in json.dumps(request_event)
    assert response_event["response_text"] == "Ning response from DeepSeek."
    serialized = json.dumps(events)
    assert "deepseek-secret-key" not in serialized
    assert response_event["input_tokens"] == 21
    assert response_event["output_tokens"] == 7
    assert not any("provider.request" in record.message for record in caplog.records)
    assert not any("provider.response" in record.message for record in caplog.records)


def test_provider_trace_content_mode_includes_bounded_messages(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("ECHO_MASQUE_PROVIDER_TRACE_MODE", "content")
    monkeypatch.setenv("ECHO_MASQUE_PROVIDER_TRACE_MAX_CHARS", "256")
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)

    try:
        provider = OpenAICompatibleProvider(
            base_url="https://api.deepseek.com/v1",
            api_key=SecretStr("secret"),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"content": "ok"}, "finish_reason": "stop"}
                        ],
                        "usage": {},
                    },
                )
            ),
        )
        asyncio.run(
            provider.complete(
                messages=(ChatMessage(role="system", content="x" * 400),),
                model="deepseek-chat",
                temperature=0.2,
            )
        )
    finally:
        configure_provider_trace_sink(None)

    request_event = next(item for item in events if item["event"] == "provider.request")
    messages = request_event["messages"]
    assert isinstance(messages, list)
    assert len(str(messages[0]["content"])) < 400
    assert "chars omitted" in str(messages[0]["content"])
