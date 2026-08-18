import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from echo_masque.media_runtime import MediaAsset
from echo_masque.provider_capabilities import ProviderModelCapabilityRegistry
from echo_masque.provider_failure_classifier import classify_provider_response
from echo_masque.providers import ChatMessage, ChatToolDefinition, ChatToolFunction
from echo_masque.providers.errors import (
    ProviderBillingRequiredError,
    ProviderCapabilityUnsupportedError,
    ProviderQuotaExhaustedError,
)
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider


def _run(provider: OpenAICompatibleProvider) -> Any:
    return asyncio.run(
        provider.complete(
            messages=(ChatMessage(role="user", content="test"),),
            model="free-model",
            temperature=0.0,
        )
    )


def test_failure_classifier_recognizes_billing_required_without_429() -> None:
    failure = classify_provider_response(
        status_code=402,
        body=json.dumps(
            {
                "error": {
                    "type": "billing_error",
                    "message": "Free credits are exhausted. Add a payment method to continue.",
                }
            }
        ),
    )
    assert failure is not None
    assert failure.kind == "billing_required"
    assert failure.retryable is False


def test_openai_provider_recognizes_200_error_envelope_as_free_quota_exhausted() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": {
                    "code": "free_tier_limit",
                    "message": "Your free quota is exhausted for today.",
                }
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key=SecretStr("secret"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderQuotaExhaustedError) as raised:
        _run(provider)
    assert raised.value.free_tier is True
    assert any(item.remaining == 0 for item in raised.value.quota_observations)


def test_openai_provider_does_not_misclassify_payment_required_403_as_auth() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": {"message": "Please enable billing or add a payment method."}},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key=SecretStr("secret"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderBillingRequiredError):
        _run(provider)


def test_tool_capability_error_is_semantically_classified() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "This model does not support tool calling."}},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key=SecretStr("secret"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderCapabilityUnsupportedError) as raised:
        asyncio.run(
            provider.complete_with_tools(
                messages=(ChatMessage(role="user", content="calculate"),),
                model="free-model",
                temperature=0.0,
                tools=(
                    ChatToolDefinition(
                        function=ChatToolFunction(
                            name="calculator",
                            parameters={"type": "object", "properties": {}},
                        )
                    ),
                ),
            )
        )
    assert raised.value.capability == "native_tool_calling"


def test_media_structured_output_extracts_prose_and_safely_normalizes_shape() -> None:
    ProviderModelCapabilityRegistry.reset_for_test()
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload["messages"][0]["role"] == "system"
        assert payload["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={
                "model": "vision-free",
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Analysis follows: "
                                '{"summary":"A screenshot of a chat interface.",'
                                '"visibleText":"hello","people":[{"description":"one person"}],'
                                '"objects":"phone","notableDetails":null,'
                                '"topics":["chat"],"tone":"casual"}'
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
        )

    provider = OpenAICompatibleMultimodalProvider(
        provider_id="utility:test-vision",
        api_key=SecretStr("secret"),
        model="vision-free",
        base_url="https://provider.example/v1",
        transport=httpx.MockTransport(handler),
    )
    analysis = asyncio.run(
        provider.analyze(
            MediaAsset(
                media_key="sha256:test",
                media_type="image",
                source_uri="https://example.com/test.png",
            )
        )
    )
    assert analysis.summary == "A screenshot of a chat interface."
    assert analysis.visible_text == "hello"
    assert analysis.people == ("one person",)
    assert analysis.objects == ("phone",)
    assert analysis.notable_details == ()
    assert len(calls) == 1


def test_media_json_schema_capability_falls_back_once_and_is_remembered() -> None:
    ProviderModelCapabilityRegistry.reset_for_test()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        response_format = payload.get("response_format")
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            return httpx.Response(
                400,
                json={"error": {"message": "json_schema response_format is not supported."}},
            )
        assert response_format == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "model": "vision-free",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "A blue icon.",
                                    "visible_text": "",
                                    "people": [],
                                    "objects": ["icon"],
                                    "notable_details": [],
                                    "topics": ["UI"],
                                    "tone": "neutral",
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    provider = OpenAICompatibleMultimodalProvider(
        provider_id="utility:test-vision",
        api_key=SecretStr("secret"),
        model="vision-free",
        base_url="https://provider.example/v1",
        transport=httpx.MockTransport(handler),
    )
    asset = MediaAsset(
        media_key="sha256:test2",
        media_type="image",
        source_uri="https://example.com/test2.png",
    )
    first = asyncio.run(provider.analyze(asset))
    assert first.summary == "A blue icon."
    assert calls == 2
    assert (
        ProviderModelCapabilityRegistry.status(
            provider="utility:test-vision",
            model="vision-free",
            base_url="https://provider.example/v1",
            capability="json_schema",
        )
        == "unsupported"
    )

    calls = 0
    second = asyncio.run(provider.analyze(asset))
    assert second.summary == "A blue icon."
    assert calls == 1
