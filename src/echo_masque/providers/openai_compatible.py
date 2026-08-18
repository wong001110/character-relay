"""Minimal OpenAI-compatible chat provider."""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from time import perf_counter
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from echo_masque.provider_capabilities import ModelCapability
from echo_masque.provider_failure_classifier import (
    NormalizedProviderFailure,
    classify_provider_response,
)
from echo_masque.providers.base import (
    ChatMessage,
    ChatToolCall,
    ChatToolDefinition,
    ProviderCompletion,
    ProviderQuotaObservation,
)
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderBillingRequiredError,
    ProviderCapabilityUnsupportedError,
    ProviderError,
    ProviderInsufficientBalanceError,
    ProviderModelNotFoundError,
    ProviderModelUnavailableError,
    ProviderProtocolError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from echo_masque.providers.trace import ProviderTrace

_DURATION_PART = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h)", re.I)


def _float_header(headers: httpx.Headers, name: str) -> float | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _reset_time(raw: str | None, *, now: datetime, retry_after: bool = False) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    if retry_after:
        try:
            return now + timedelta(seconds=max(0.0, float(value)))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    parts = list(_DURATION_PART.finditer(value))
    if parts and "".join(item.group(0) for item in parts).casefold() == value.casefold():
        seconds = 0.0
        for item in parts:
            amount = float(item.group("value"))
            unit = item.group("unit").casefold()
            seconds += (
                amount / 1000 if unit == "ms" else amount * {"s": 1, "m": 60, "h": 3600}[unit]
            )
        return now + timedelta(seconds=max(0.0, seconds))
    try:
        numeric = float(value)
    except ValueError:
        return None
    if numeric > 1_000_000_000:
        return datetime.fromtimestamp(numeric, tz=UTC)
    return now + timedelta(seconds=max(0.0, numeric))


def _quota_observations(headers: httpx.Headers) -> tuple[ProviderQuotaObservation, ...]:
    now = datetime.now(UTC)
    observations: list[ProviderQuotaObservation] = []
    dimensions = (
        (
            "requests",
            "requests",
            "x-ratelimit-remaining-requests",
            "x-ratelimit-limit-requests",
            "x-ratelimit-reset-requests",
        ),
        (
            "tokens",
            "tokens",
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-limit-tokens",
            "x-ratelimit-reset-tokens",
        ),
        ("requests", "requests", "ratelimit-remaining", "ratelimit-limit", "ratelimit-reset"),
    )
    seen: set[tuple[str, str]] = set()
    for kind, unit, remaining_header, limit_header, reset_header in dimensions:
        remaining = _float_header(headers, remaining_header)
        limit_value = _float_header(headers, limit_header)
        reset_at = _reset_time(headers.get(reset_header), now=now)
        if remaining is None and limit_value is None and reset_at is None:
            continue
        key = (kind, reset_header)
        if key in seen:
            continue
        seen.add(key)
        observations.append(
            ProviderQuotaObservation(
                kind=kind,
                remaining=remaining,
                limit=limit_value,
                unit=unit,
                reset_at=reset_at,
                source="response_header",
            )
        )
    retry_reset = _reset_time(headers.get("retry-after"), now=now, retry_after=True)
    if retry_reset is not None:
        observations.append(
            ProviderQuotaObservation(
                kind="retry_after",
                unit="seconds",
                reset_at=retry_reset,
                source="retry_after_header",
            )
        )
    return tuple(observations)


def _requested_capabilities(
    *,
    tools: tuple[ChatToolDefinition, ...],
    response_format: dict[str, object] | None,
) -> tuple[ModelCapability, ...]:
    values: list[ModelCapability] = []
    if tools:
        values.append("native_tool_calling")
    if response_format is not None:
        format_type = str(response_format.get("type") or "").casefold()
        if format_type == "json_schema":
            values.append("json_schema")
        elif format_type == "json_object":
            values.append("json_object")
    return tuple(values)


def _failure_error(
    failure: NormalizedProviderFailure,
    *,
    quota_observations: tuple[ProviderQuotaObservation, ...],
) -> ProviderError:
    detail = failure.detail or failure.kind
    if failure.kind == "rate_limited":
        return ProviderRateLimitError(detail, quota_observations=quota_observations)
    if failure.kind in {"quota_exhausted", "free_tier_exhausted"}:
        observations = quota_observations
        if not any(item.remaining == 0 for item in observations):
            observations = (
                *observations,
                ProviderQuotaObservation(
                    kind="free_tier" if failure.kind == "free_tier_exhausted" else "quota",
                    remaining=0,
                    unit="requests",
                    source="response_body",
                ),
            )
        return ProviderQuotaExhaustedError(
            detail,
            quota_observations=observations,
            free_tier=failure.kind == "free_tier_exhausted",
        )
    if failure.kind == "billing_required":
        return ProviderBillingRequiredError(detail)
    if failure.kind == "insufficient_balance":
        return ProviderInsufficientBalanceError(detail)
    if failure.kind == "authentication_invalid":
        return ProviderAuthenticationError(detail)
    if failure.kind == "capability_unsupported" and failure.capability is not None:
        return ProviderCapabilityUnsupportedError(detail, capability=failure.capability)
    if failure.kind == "model_not_found":
        return ProviderModelNotFoundError(detail)
    if failure.kind == "model_unavailable":
        return ProviderModelUnavailableError(detail)
    if failure.kind == "temporary_unavailable":
        return ProviderUnavailableError(detail)
    return ProviderProtocolError(detail)


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
        value: dict[str, object] = {"role": message.role, "content": message.content}
        if message.tool_call_id is not None:
            value["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            value["tool_calls"] = [item.model_dump() for item in message.tool_calls]
        return value

    @staticmethod
    def _request_error_detail(exc: httpx.RequestError) -> str:
        name = type(exc).__name__
        message = str(exc).replace("\x00", "").strip()
        return f"{name}: {message[:700]}" if message else name

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        max_output_tokens: int | None = None,
        response_format: dict[str, object] | None = None,
    ) -> ProviderCompletion:
        return await self._complete(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=(),
            max_output_tokens=max_output_tokens,
            response_format=response_format,
        )

    async def complete_with_tools(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
        max_output_tokens: int | None = None,
    ) -> ProviderCompletion:
        return await self._complete(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=tools,
            max_output_tokens=max_output_tokens,
            response_format=None,
        )

    async def _complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
        max_output_tokens: int | None,
        response_format: dict[str, object] | None,
    ) -> ProviderCompletion:
        tool_payloads = [item.model_dump() for item in tools]
        tool_schema_chars = (
            len(json.dumps(tool_payloads, ensure_ascii=False, separators=(",", ":")))
            if tool_payloads
            else 0
        )
        payload: dict[str, object] = {
            "model": model,
            "temperature": temperature,
            "messages": [self._message_payload(item) for item in messages],
        }
        if max_output_tokens is not None:
            payload["max_tokens"] = max(1, min(int(max_output_tokens), 8192))
        if response_format is not None:
            payload["response_format"] = response_format
        if tool_payloads:
            payload["tools"] = tool_payloads
            payload["tool_choice"] = "auto"
        if self._uses_deepseek_api:
            payload["thinking"] = {"type": "disabled"}

        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        started = perf_counter()
        trace = ProviderTrace.start(
            endpoint=self.endpoint,
            model=model,
            temperature=temperature,
            messages=messages,
            available_tool_names=tuple(item.function.name for item in tools),
            tool_schema_count=len(tool_payloads),
            tool_schema_chars=tool_schema_chars,
        )
        requested = _requested_capabilities(tools=tools, response_format=response_format)

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                for attempt in range(self._max_retries + 1):
                    try:
                        response = await client.post(self.endpoint, json=payload, headers=headers)
                    except httpx.TimeoutException as exc:
                        trace.error(
                            reason=ProviderTimeoutError.reason_code,
                            detail=self._request_error_detail(exc),
                        )
                        raise ProviderTimeoutError(
                            "Model provider did not respond before the request timeout."
                        ) from exc
                    except httpx.RequestError as exc:
                        if attempt < self._max_retries:
                            trace.retry(attempt=attempt + 1, reason="network_error")
                            await asyncio.sleep(0)
                            continue
                        trace.error(
                            reason=ProviderUnavailableError.reason_code,
                            detail=self._request_error_detail(exc),
                        )
                        raise ProviderUnavailableError("Model provider could not be reached.") from exc

                    quota_observations = _quota_observations(response.headers)
                    if response.status_code == 408:
                        trace.error(
                            reason=ProviderTimeoutError.reason_code,
                            status_code=response.status_code,
                            response_body=response.text,
                            detail="The provider returned HTTP 408 Request Timeout.",
                        )
                        raise ProviderTimeoutError("Model provider returned HTTP 408.")

                    failure = classify_provider_response(
                        status_code=response.status_code,
                        body=response.text,
                        headers=dict(response.headers),
                        requested_capabilities=requested,
                    )
                    if failure is not None:
                        retryable_failure = failure.kind in {"rate_limited", "temporary_unavailable", "model_unavailable"}
                        if retryable_failure and attempt < self._max_retries:
                            trace.retry(
                                attempt=attempt + 1,
                                reason=failure.kind,
                                status_code=response.status_code,
                            )
                            await asyncio.sleep(0)
                            continue
                        error = _failure_error(failure, quota_observations=quota_observations)
                        trace.error(
                            reason=error.reason_code,
                            status_code=response.status_code,
                            response_body=response.text,
                            detail=failure.detail,
                        )
                        raise error

                    try:
                        body = response.json()
                        if not isinstance(body, dict):
                            raise TypeError("response must be an object")
                        choices = body["choices"]
                        if not isinstance(choices, list) or not choices:
                            raise TypeError("choices must be a non-empty list")
                        choice = choices[0]
                        if not isinstance(choice, dict):
                            raise TypeError("choice must be an object")
                        message = choice["message"]
                        if not isinstance(message, dict):
                            raise TypeError("message must be an object")
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
                            detail=f"Invalid chat-completion payload: {type(exc).__name__}.",
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
                            detail="The provider returned no visible content or tool call.",
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
                        finish_reason=str(finish_reason) if finish_reason is not None else None,
                        tool_call_names=tuple(item.function.name for item in tool_calls),
                    )
                    return ProviderCompletion(
                        text=text,
                        model=response_model,
                        latency_ms=round((perf_counter() - started) * 1000),
                        input_tokens=input_tokens if isinstance(input_tokens, int) else None,
                        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
                        finish_reason=str(finish_reason) if finish_reason is not None else None,
                        tool_calls=tool_calls,
                        quota_observations=quota_observations,
                    )

            trace.error(
                reason=ProviderUnavailableError.reason_code,
                detail="Provider retry loop ended without a response.",
            )
            raise ProviderUnavailableError("Model provider returned no terminal result.")
        except asyncio.CancelledError:
            trace.error(reason="request_cancelled", detail="Provider task was cancelled.")
            raise
        except ProviderError:
            raise
        except Exception as exc:
            detail = str(exc).replace("\x00", "").strip()
            trace.error(
                reason="provider_client_error",
                detail=f"{type(exc).__name__}: {detail[:700]}" if detail else type(exc).__name__,
            )
            raise ProviderProtocolError(
                "Model provider call failed before a valid response was produced."
            ) from exc
