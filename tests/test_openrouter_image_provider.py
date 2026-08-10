import asyncio
import json

import httpx
from pydantic import SecretStr

from echo_masque.image_generation import ImageGenerationRequest, ImageReference
from echo_masque.providers.openrouter_image import OpenRouterImageGenerationProvider


def test_openrouter_image_provider_normalizes_request_and_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": "aGVsbG8=",
                        "media_type": "image/png",
                    }
                ]
            },
        )

    provider = OpenRouterImageGenerationProvider(
        api_key=SecretStr("or-key"),
        model="black-forest-labs/flux.2-klein-4b",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.generate(
            ImageGenerationRequest(
                prompt="anime character drinking coffee",
                aspect_ratio="1:1",
                resolution="1K",
                references=(ImageReference(uri="https://example.com/mia.png"),),
            )
        )
    )

    assert captured["url"] == "https://openrouter.ai/api/v1/images"
    assert captured["authorization"] == "Bearer or-key"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "black-forest-labs/flux.2-klein-4b"
    assert body["aspect_ratio"] == "1:1"
    assert body["resolution"] == "1K"
    assert body["input_references"] == [
        {
            "type": "image_url",
            "image_url": {"url": "https://example.com/mia.png"},
        }
    ]
    assert result.provider == "openrouter"
    assert result.images[0].b64_json == "aGVsbG8="
