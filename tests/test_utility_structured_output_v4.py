from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from echo_masque.providers import ChatMessage
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.utility_structured_output import exact_json_contract


class ExampleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: str
    confidence: float = Field(ge=0.0, le=1.0)


def test_exact_json_contract_contains_version_schema_and_no_extra_key_rule() -> None:
    contract = exact_json_contract(
        ExampleDecision,
        schema_version="example-v1",
        additional_rules=("choice must be one supplied value.",),
    )

    assert "schema_version=example-v1" in contract
    assert "JSON Schema:" in contract
    assert '"confidence"' in contract
    assert '"choice"' in contract
    assert "Do not invent aliases or extra keys" in contract
    assert "no markdown" in contract


async def test_openai_compatible_provider_forwards_output_bound_and_json_mode() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"choice":"a","confidence":0.9}'
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 7},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.test/v1",
        api_key=SecretStr("secret"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    completion = await provider.complete(
        messages=(ChatMessage(role="user", content="return json"),),
        model="test-model",
        temperature=0.0,
        max_output_tokens=96,
        response_format={"type": "json_object"},
    )

    assert completion.text.startswith("{")
    assert observed["max_tokens"] == 96
    assert observed["response_format"] == {"type": "json_object"}


async def test_openai_compatible_provider_omits_structured_fields_for_normal_character_calls() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "normal reply"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example.test/v1",
        api_key=SecretStr("secret"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    await provider.complete(
        messages=(ChatMessage(role="user", content="hello"),),
        model="test-model",
        temperature=0.4,
    )

    assert "max_tokens" not in observed
    assert "response_format" not in observed
