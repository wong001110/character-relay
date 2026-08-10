import asyncio
import json

import httpx
from pydantic import SecretStr

from echo_masque.media_runtime import MediaAsset
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider


def test_multimodal_provider_sends_image_url_and_parses_objective_context() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "An orange cat is sitting on a laptop.",
                                    "visible_text": "Build failed",
                                    "people": [],
                                    "objects": ["cat", "laptop"],
                                    "notable_details": ["One paw is on the keyboard."],
                                    "topics": ["coding", "cats"],
                                    "tone": "humorous",
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleMultimodalProvider(
        provider_id="openrouter",
        api_key=SecretStr("or-key"),
        model="xiaomi/mimo-v2.5",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.analyze(
            MediaAsset(
                media_key="sha256:abc",
                media_type="image",
                source_uri="https://cdn.example.test/cat.png",
            )
        )
    )

    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["authorization"] == "Bearer or-key"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "xiaomi/mimo-v2.5"
    messages = body["messages"]
    assert isinstance(messages, list)
    content = messages[0]["content"]
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://cdn.example.test/cat.png"},
    }
    assert result.summary == "An orange cat is sitting on a laptop."
    assert result.visible_text == "Build failed"
    assert result.objects == ("cat", "laptop")


def test_multimodal_provider_uses_video_url_for_video_asset() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "```json\n"
                            + json.dumps(
                                {
                                    "summary": "A short UI demo video.",
                                    "visible_text": "Settings",
                                    "people": [],
                                    "objects": ["phone"],
                                    "notable_details": [],
                                    "topics": ["mobile UI"],
                                    "tone": "informational",
                                }
                            )
                            + "\n```"
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleMultimodalProvider(
        provider_id="openrouter",
        api_key=SecretStr("or-key"),
        model="xiaomi/mimo-v2.5",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.analyze(
            MediaAsset(
                media_key="youtube:abc123",
                media_type="video",
                source_uri="https://www.youtube.com/watch?v=abc123",
            )
        )
    )

    body = captured["body"]
    assert isinstance(body, dict)
    messages = body["messages"]
    assert isinstance(messages, list)
    content = messages[0]["content"]
    assert content[1] == {
        "type": "video_url",
        "video_url": {"url": "https://www.youtube.com/watch?v=abc123"},
    }
    assert result.summary == "A short UI demo video."
