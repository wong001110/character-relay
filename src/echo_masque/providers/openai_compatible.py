"""Minimal OpenAI-compatible chat provider."""

import asyncio
from time import perf_counter

import httpx
from pydantic import SecretStr

from echo_masque.providers.base import ChatMessage, ProviderCompletion
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderProtocolError,
    ProviderTimeoutError,
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._transport = transport

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleProvider("
            f"base_url={self._base_url!r}, api_key=SecretStr('**********'), "
            f"timeout_seconds={self._timeout!r}, max_retries={self._max_retries!r})"
        )

    @property
    def endpoint(self) -> str:
        suffix = "/chat/completions" if self._base_url.endswith("/v1") else "/v1/chat/completions"
        return f"{self._base_url}{suffix}"

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [item.model_dump() for item in messages],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        last_timeout: Exception | None = None
        started = perf_counter()

        async with httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            for attempt in range(self._max_retries + 1):
                try:
                    response = await client.post(self.endpoint, json=payload, headers=headers)
                except httpx.TimeoutException as exc:
                    last_timeout = exc
                    if attempt >= self._max_retries:
                        raise ProviderTimeoutError("Model provider timed out.") from exc
                    await asyncio.sleep(0)
                    continue

                if response.status_code in {401, 403}:
                    raise ProviderAuthenticationError("Model provider rejected the credential.")
                if response.status_code >= 500 and attempt < self._max_retries:
                    await asyncio.sleep(0)
                    continue
                if response.is_error:
                    raise ProviderProtocolError(
                        f"Model provider returned HTTP {response.status_code}."
                    )

                try:
                    body = response.json()
                    choice = body["choices"][0]
                    text = choice["message"]["content"]
                    usage = body.get("usage", {})
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise ProviderProtocolError(
                        "Model provider returned an invalid chat-completion payload."
                    ) from exc

                return ProviderCompletion(
                    text=str(text),
                    model=str(body.get("model", model)),
                    latency_ms=round((perf_counter() - started) * 1000),
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    finish_reason=choice.get("finish_reason"),
                )

        raise ProviderTimeoutError("Model provider timed out.") from last_timeout
