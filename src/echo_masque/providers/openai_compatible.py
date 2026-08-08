"""Minimal OpenAI-compatible chat provider."""

import asyncio
from time import perf_counter
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from echo_masque.providers.base import (
    ChatMessage,
    ChatToolCall,
    ChatToolDefinition,
    ProviderCompletion,
)
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderProtocolError,
    ProviderTimeoutError,
)
from echo_masque.providers.trace import ProviderTrace


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

    @property
    def _uses_deepseek_api(self) -> bool:
        hostname = (urlparse(self._base_url).hostname or "").casefold()
        return hostname == "api.deepseek.com"

    @staticmethod
    def _message_payload(message: ChatMessage) -> dict[str, object]:
        value: dict[str, object] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_call_id is not None:
            value["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            value["tool_calls"] = [item.model_dump() for item in message.tool_calls]
        return value

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        return await self._complete(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=(),
        )

    async def complete_with_tools(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
    ) -> ProviderCompletion:
        return await self._complete(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=tools,
        )

    async def _complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
    ) -> ProviderCompletion:
        payload: dict[str, object] = {
            "model": model,
            "temperature": temperature,
            "messages": [self._message_payload(item) for item in messages],
        }
        if tools:
            payload["tools"] = [item.model_dump() for item in tools]
            payload["tool_choice"] = "auto"
        if self._uses_deepseek_api:
            # DeepSeek currently defaults chat completions to thinking mode. Character
            # Relay expects a direct user-visible answer from this low-latency adapter,
            # so explicitly request non-thinking mode instead of consuming hidden CoT.
            payload["thinking"] = {"type": "disabled"}

        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        last_timeout: Exception | None = None
        started = perf_counter()
        trace = ProviderTrace.start(
            endpoint=self.endpoint,
            model=model,
            temperature=temperature,
            messages=messages,
        )

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
                        trace.error(reason="timeout")
                        raise ProviderTimeoutError("Model provider timed out.") from exc
                    trace.retry(attempt=attempt + 1, reason="timeout")
                    await asyncio.sleep(0)
                    continue

                if response.status_code in {401, 403}:
                    trace.error(
                        reason="authentication_rejected",
                        status_code=response.status_code,
                    )
                    raise ProviderAuthenticationError("Model provider rejected the credential.")
                if response.status_code >= 500 and attempt < self._max_retries:
                    trace.retry(
                        attempt=attempt + 1,
                        reason="server_error",
                        status_code=response.status_code,
                    )
                    await asyncio.sleep(0)
                    continue
                if response.is_error:
                    trace.error(
                        reason="http_error",
                        status_code=response.status_code,
                        response_body=response.text,
                    )
                    raise ProviderProtocolError(
                        f"Model provider returned HTTP {response.status_code}."
                    )

                try:
                    body = response.json()
                    choice = body["choices"][0]
                    message = choice["message"]
                    raw_content = message.get("content")
                    if raw_content is None:
                        text = ""
                    elif isinstance(raw_content, str):
                        text = raw_content
                    else:
                        raise TypeError("Chat-completion content must be a string or null.")
                    raw_tool_calls = message.get("tool_calls", [])
                    if raw_tool_calls is None:
                        raw_tool_calls = []
                    if not isinstance(raw_tool_calls, list):
                        raise TypeError("Chat-completion tool_calls must be a list.")
                    tool_calls = tuple(ChatToolCall.model_validate(item) for item in raw_tool_calls)
                    usage = body.get("usage", {})
                    if not isinstance(usage, dict):
                        raise TypeError("Chat-completion usage must be an object.")
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    trace.error(
                        reason="invalid_response_payload",
                        status_code=response.status_code,
                        response_body=response.text,
                    )
                    raise ProviderProtocolError(
                        "Model provider returned an invalid chat-completion payload."
                    ) from exc

                response_model = str(body.get("model", model))
                input_tokens = usage.get("prompt_tokens")
                output_tokens = usage.get("completion_tokens")
                finish_reason = choice.get("finish_reason")

                if not text.strip() and not tool_calls:
                    if attempt < self._max_retries:
                        trace.retry(
                            attempt=attempt + 1,
                            reason="empty_content",
                            status_code=response.status_code,
                        )
                        await asyncio.sleep(0)
                        continue
                    trace.error(
                        reason="empty_content",
                        status_code=response.status_code,
                    )
                    raise ProviderProtocolError(
                        "Model provider returned empty chat-completion content."
                    )

                trace_text = text
                if not trace_text and tool_calls:
                    names = ", ".join(item.function.name for item in tool_calls)
                    trace_text = f"[tool calls: {names}]"
                trace.response(
                    status_code=response.status_code,
                    response_model=response_model,
                    text=trace_text,
                    input_tokens=input_tokens if isinstance(input_tokens, int) else None,
                    output_tokens=output_tokens if isinstance(output_tokens, int) else None,
                    finish_reason=(str(finish_reason) if finish_reason is not None else None),
                )
                return ProviderCompletion(
                    text=text,
                    model=response_model,
                    latency_ms=round((perf_counter() - started) * 1000),
                    input_tokens=input_tokens if isinstance(input_tokens, int) else None,
                    output_tokens=output_tokens if isinstance(output_tokens, int) else None,
                    finish_reason=(str(finish_reason) if finish_reason is not None else None),
                    tool_calls=tool_calls,
                )

        trace.error(reason="timeout")
        raise ProviderTimeoutError("Model provider timed out.") from last_timeout
