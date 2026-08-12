import asyncio
import json

import httpx
from pydantic import SecretStr

from echo_masque.providers.base import ChatMessage, ChatToolDefinition, ChatToolFunction
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.providers.trace import configure_provider_trace_sink


def test_provider_trace_reports_hidden_tool_schema_chars() -> None:
    events: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert len(body["tools"]) == 1
        return httpx.Response(
            200,
            json={
                "model": "demo-model",
                "choices": [
                    {
                        "message": {"content": "done", "tool_calls": []},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 123, "completion_tokens": 4},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.test/v1",
        api_key=SecretStr("test-key"),
        transport=httpx.MockTransport(handler),
    )
    tool = ChatToolDefinition(
        function=ChatToolFunction(
            name="weather_get",
            description="Get the current weather and forecast.",
            parameters={
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
                "additionalProperties": False,
            },
        )
    )
    configure_provider_trace_sink(events.append)
    try:
        asyncio.run(
            provider.complete_with_tools(
                messages=(ChatMessage(role="user", content="weather tomorrow"),),
                model="demo-model",
                temperature=0.2,
                tools=(tool,),
            )
        )
    finally:
        configure_provider_trace_sink(None)

    request = events[0]
    assert request["event"] == "provider.request"
    assert request["tool_schema_count"] == 1
    assert isinstance(request["tool_schema_chars"], int)
    assert request["tool_schema_chars"] > 100
    assert request["message_chars"] == len("weather tomorrow")
