import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from echo_masque.providers.base import ChatMessage
from echo_masque.providers.errors import ProviderRateLimitError
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider


def test_success_exposes_request_and_token_quota_headers() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "x-ratelimit-remaining-requests": "42",
                "x-ratelimit-limit-requests": "100",
                "x-ratelimit-reset-requests": "5s",
                "x-ratelimit-remaining-tokens": "9000",
                "x-ratelimit-limit-tokens": "10000",
                "x-ratelimit-reset-tokens": "2s",
            },
            json={
                "model": "test",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("key"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.complete(
            messages=(ChatMessage(role="user", content="hello"),),
            model="test",
            temperature=0,
        )
    )
    values = {item.kind: item for item in result.quota_observations}
    assert values["requests"].remaining == 42
    assert values["requests"].limit == 100
    assert values["tokens"].remaining == 9000
    assert values["tokens"].limit == 10000
    assert values["requests"].reset_at is not None


def test_429_preserves_retry_after_without_inventing_remaining() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "30"},
            json={"error": "rate"},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("key"),
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    before = datetime.now(UTC)
    with pytest.raises(ProviderRateLimitError) as raised:
        asyncio.run(
            provider.complete(
                messages=(ChatMessage(role="user", content="hello"),),
                model="test",
                temperature=0,
            )
        )
    observation = raised.value.quota_observations[0]
    assert observation.kind == "retry_after"
    assert observation.remaining is None
    assert observation.reset_at is not None
    assert observation.reset_at >= before
