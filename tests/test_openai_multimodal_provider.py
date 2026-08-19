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
    assert messages[0]["role"] == "system"
    assert "objective media-understanding parser" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    content = messages[1]["content"]
    assert isinstance(content, list)
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
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    content = messages[1]["content"]
    assert isinstance(content, list)
    assert content[1] == {
        "type": "video_url",
        "video_url": {"url": "https://www.youtube.com/watch?v=abc123"},
    }
    assert result.summary == "A short UI demo video."


def test_multimodal_provider_uses_local_keyframes_instead_of_platform_video_url() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Sampled frames show a cooking demonstration.",
                                    "visible_text": "Step 2",
                                    "people": ["one presenter"],
                                    "objects": ["pan"],
                                    "notable_details": ["The pan appears in later samples."],
                                    "topics": ["cooking"],
                                    "tone": "instructional",
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
    frames = (
        "data:image/jpeg;base64,QUFB",
        "data:image/jpeg;base64,QkJC",
    )
    result = asyncio.run(
        provider.analyze(
            MediaAsset(
                media_key="url:bilibili:platform-keyframes-v1",
                media_type="video",
                source_uri="https://www.bilibili.com/video/BV1test",
                keyframe_uris=frames,
                keyframe_timestamps_seconds=(5.0, 15.0),
            )
        )
    )

    body = captured["body"]
    assert isinstance(body, dict)
    messages = body["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    content = messages[1]["content"]
    assert isinstance(content, list)
    assert "chronological sampled keyframes" in content[0]["text"]
    assert content[1:] == [
        {"type": "image_url", "image_url": {"url": frames[0]}},
        {"type": "image_url", "image_url": {"url": frames[1]}},
    ]
    assert not any(item.get("type") == "video_url" for item in content)
    assert result.summary == "Sampled frames show a cooking demonstration."
