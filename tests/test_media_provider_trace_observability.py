import asyncio
import json

import httpx
from pydantic import SecretStr

from echo_masque.media_runtime import MediaAsset
from echo_masque.provider_trace_classification import (
    provider_trace_category,
    provider_trace_media_input,
)
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider
from echo_masque.providers.trace import (
    configure_provider_trace_sink,
    provider_trace_scope,
)


def test_image_understanding_emits_scoped_media_provider_trace() -> None:
    events: list[dict[str, object]] = []

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "xiaomi/mimo-v2.5",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "A tabby kitten is lying on a white bed.",
                                    "visible_text": "",
                                    "people": [],
                                    "objects": ["kitten", "bed"],
                                    "notable_details": ["The kitten has blue-gray eyes."],
                                    "topics": ["cat"],
                                    "tone": "calm",
                                }
                            )
                        },
                    }
                ],
                "usage": {"prompt_tokens": 123, "completion_tokens": 45},
            },
        )

    provider = OpenAICompatibleMultimodalProvider(
        provider_id="openrouter",
        api_key=SecretStr("secret-key"),
        model="xiaomi/mimo-v2.5",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    configure_provider_trace_sink(events.append)
    try:
        async def run() -> None:
            with provider_trace_scope(
                owner_id="owner-1",
                deployment_id="deployment-1",
                character_card_id="character-1",
            ):
                await provider.analyze(
                    MediaAsset(
                        media_key="sha256:abc123",
                        media_type="image",
                        mime_type="image/png",
                        filename="cat.png",
                        source_uri=(
                            "https://cdn.example.test/cat.png"
                            "?token=must-not-appear&expires=123"
                        ),
                        size_bytes=2048,
                    )
                )

        asyncio.run(run())
    finally:
        configure_provider_trace_sink(None)

    assert [event["event"] for event in events] == [
        "provider.request",
        "provider.response",
    ]
    request = events[0]
    assert request["owner_id"] == "owner-1"
    assert request["deployment_id"] == "deployment-1"
    assert request["character_card_id"] == "character-1"
    request_json = json.dumps(request)
    assert provider_trace_category(request_json, "") == "media_understanding"
    media = provider_trace_media_input(request_json)
    assert media == {
        "operation": "media_understanding",
        "media_type": "image",
        "media_key": "sha256:abc123",
        "filename": "cat.png",
        "mime_type": "image/png",
        "size_bytes": 2048,
        "input_part_type": "image_url",
        "source_host": "cdn.example.test",
        "source_uri": "https://cdn.example.test/cat.png",
    }
    assert "must-not-appear" not in request_json

    response = events[1]
    assert response["status_code"] == 200
    assert response["response_model"] == "xiaomi/mimo-v2.5"
    assert response["input_tokens"] == 123
    assert response["output_tokens"] == 45
    assert "tabby kitten" in str(response.get("response_text", ""))


def test_media_trace_redacts_data_uri_body() -> None:
    assert OpenAICompatibleMultimodalProvider._trace_source_uri(
        "data:image/png;base64,AAAA"
    ) == "data:<redacted>"
