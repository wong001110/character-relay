from __future__ import annotations

import asyncio
import json

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from echo_masque.media_runtime import MediaAsset
from echo_masque.provider_capabilities import ProviderModelCapabilityRegistry
from echo_masque.provider_io import complete_structured, provider_dialect
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.utility_media_provider import _GeminiMultimodalProvider


class ExampleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: str
    confidence: float = Field(ge=0.0, le=1.0)


class _AllowAllGuard:
    async def validate(self, url: str) -> str:
        return url


def test_structured_completion_prefers_json_schema_and_embeds_exact_contract() -> None:
    ProviderModelCapabilityRegistry.reset_for_test()
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        observed.update(payload)
        response_format = payload["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        assert "choice" in json.dumps(response_format["json_schema"]["schema"])
        system_prompt = payload["messages"][0]["content"]
        assert "schema_version=example-v1" in system_prompt
        assert "Do not invent aliases or extra keys" in system_prompt
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "message": {"content": '{"choice":"a","confidence":0.9}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key=SecretStr("secret"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    completion = asyncio.run(
        complete_structured(
            provider,
            provider_id="groq",
            base_url="https://provider.example/v1",
            model="test-model",
            schema=ExampleDecision,
            schema_name="example_decision",
            schema_version="example-v1",
            system_prompt="Choose one supplied option.",
            user_prompt="a or b",
            temperature=0.0,
            max_output_tokens=96,
        )
    )

    assert completion.text.startswith("{")
    assert observed["max_tokens"] == 96
    assert (
        ProviderModelCapabilityRegistry.status(
            provider="groq",
            model="test-model",
            base_url="https://provider.example/v1",
            capability="json_schema",
        )
        == "supported"
    )


def test_structured_completion_falls_back_and_remembers_schema_rejection() -> None:
    ProviderModelCapabilityRegistry.reset_for_test()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        mode = payload.get("response_format", {}).get("type", "prompt_only")
        calls.append(mode)
        if mode == "json_schema":
            return httpx.Response(
                400,
                json={"error": {"message": "json_schema response_format is not supported"}},
            )
        assert mode == "json_object"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"choice":"b","confidence":0.8}'},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key=SecretStr("secret"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    first = asyncio.run(
        complete_structured(
            provider,
            provider_id="cloudflare",
            base_url="https://provider.example/v1",
            model="test-model",
            schema=ExampleDecision,
            schema_name="example_decision",
            schema_version="example-v1",
            system_prompt="Choose.",
            user_prompt="b",
            temperature=0.0,
        )
    )
    assert first.text.startswith("{")
    assert calls == ["json_schema", "json_object"]
    assert (
        ProviderModelCapabilityRegistry.status(
            provider="cloudflare",
            model="test-model",
            base_url="https://provider.example/v1",
            capability="json_schema",
        )
        == "unsupported"
    )

    calls.clear()
    second = asyncio.run(
        complete_structured(
            provider,
            provider_id="cloudflare",
            base_url="https://provider.example/v1",
            model="test-model",
            schema=ExampleDecision,
            schema_name="example_decision",
            schema_version="example-v1",
            system_prompt="Choose.",
            user_prompt="b",
            temperature=0.0,
        )
    )
    assert second.text.startswith("{")
    assert calls == ["json_object"]


def test_provider_dialects_cover_cloudflare_and_gemini_media_transport() -> None:
    assert provider_dialect("cloudflare").structured_output_modes[0] == "json_schema"
    assert provider_dialect("gemini").structured_output_modes[0] == "json_schema"
    assert provider_dialect("gemini").image_input_transport == "data_uri"
    assert provider_dialect("deepseek").structured_output_modes[0] == "json_object"


def test_gemini_media_adapter_converts_remote_image_to_data_uri() -> None:
    ProviderModelCapabilityRegistry.reset_for_test()
    seen_provider_payload: dict[str, object] = {}

    def media_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://cdn.example/image.png"
        return httpx.Response(
            200,
            content=b"fake-png-bytes",
            headers={"content-type": "image/png"},
        )

    def provider_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen_provider_payload.update(payload)
        user_content = payload["messages"][1]["content"]
        image_url = user_content[1]["image_url"]["url"]
        assert image_url.startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "model": "gemini-test",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "A small test image.",
                                    "visible_text": "",
                                    "people": [],
                                    "objects": ["test image"],
                                    "notable_details": [],
                                    "topics": ["test"],
                                    "tone": "neutral",
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    provider = _GeminiMultimodalProvider(
        provider_id="utility:gemini-test",
        api_key=SecretStr("secret"),
        model="gemini-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        transport=httpx.MockTransport(provider_handler),
        media_transport=httpx.MockTransport(media_handler),
        url_guard=_AllowAllGuard(),  # type: ignore[arg-type]
    )
    analysis = asyncio.run(
        provider.analyze(
            MediaAsset(
                media_key="sha256:test",
                media_type="image",
                mime_type="image/png",
                source_uri="https://cdn.example/image.png",
            )
        )
    )

    assert analysis.summary == "A small test image."
    assert seen_provider_payload["response_format"]["type"] == "json_schema"
