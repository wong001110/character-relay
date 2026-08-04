"""Structured, secret-free model provider request and response tracing."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Literal
from uuid import uuid4

from echo_masque.providers.base import ChatMessage

ProviderTraceMode = Literal["off", "metadata", "summary", "content"]
_DEFAULT_TRACE_MODE: ProviderTraceMode = "summary"
_DEFAULT_MAX_CHARS = 4000
_LOGGER = logging.getLogger("uvicorn.error")


def _trace_mode() -> ProviderTraceMode:
    raw = os.getenv("ECHO_MASQUE_PROVIDER_TRACE_MODE", _DEFAULT_TRACE_MODE).strip().lower()
    if raw in {"off", "metadata", "summary", "content"}:
        return raw  # type: ignore[return-value]
    return _DEFAULT_TRACE_MODE


def _max_chars() -> int:
    raw = os.getenv("ECHO_MASQUE_PROVIDER_TRACE_MAX_CHARS", str(_DEFAULT_MAX_CHARS)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CHARS
    return min(max(parsed, 256), 20000)


def _preview(value: str, maximum: int) -> str:
    normalized = value.replace("\x00", "").strip()
    if len(normalized) <= maximum:
        return normalized
    omitted = len(normalized) - maximum
    return f"{normalized[:maximum]}… <{omitted} chars omitted>"


def _message_content(
    messages: tuple[ChatMessage, ...],
    *,
    mode: ProviderTraceMode,
    maximum: int,
) -> dict[str, object]:
    if mode == "metadata":
        return {}
    if mode == "summary":
        latest = next(
            (item for item in reversed(messages) if item.role != "system"),
            messages[-1] if messages else None,
        )
        return {
            "latest_message": (
                {"role": latest.role, "content": _preview(latest.content, maximum)}
                if latest is not None
                else None
            )
        }

    remaining = maximum
    traced: list[dict[str, str]] = []
    for item in messages:
        if remaining <= 0:
            break
        content = _preview(item.content, remaining)
        traced.append({"role": item.role, "content": content})
        remaining -= min(len(item.content), remaining)
    omitted_messages = max(len(messages) - len(traced), 0)
    return {
        "messages": traced,
        "omitted_messages": omitted_messages,
    }


def _emit(payload: dict[str, object]) -> None:
    _LOGGER.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


@dataclass(frozen=True)
class ProviderTrace:
    """One correlated trace for a provider request and its eventual result."""

    trace_id: str
    mode: ProviderTraceMode
    max_chars: int
    endpoint: str
    model: str
    started_at: float

    @classmethod
    def start(
        cls,
        *,
        endpoint: str,
        model: str,
        temperature: float,
        messages: tuple[ChatMessage, ...],
    ) -> ProviderTrace:
        mode = _trace_mode()
        trace = cls(
            trace_id=str(uuid4()),
            mode=mode,
            max_chars=_max_chars(),
            endpoint=endpoint,
            model=model,
            started_at=perf_counter(),
        )
        if mode == "off":
            return trace

        system_chars = sum(len(item.content) for item in messages if item.role == "system")
        event: dict[str, object] = {
            "event": "provider.request",
            "trace_id": trace.trace_id,
            "endpoint": endpoint,
            "model": model,
            "temperature": temperature,
            "message_count": len(messages),
            "message_roles": [item.role for item in messages],
            "message_chars": sum(len(item.content) for item in messages),
            "system_message_chars": system_chars,
            "trace_mode": mode,
        }
        event.update(_message_content(messages, mode=mode, maximum=trace.max_chars))
        _emit(event)
        return trace

    def retry(self, *, attempt: int, reason: str, status_code: int | None = None) -> None:
        if self.mode == "off":
            return
        _emit(
            {
                "event": "provider.retry",
                "trace_id": self.trace_id,
                "endpoint": self.endpoint,
                "model": self.model,
                "attempt": attempt,
                "reason": reason,
                "status_code": status_code,
            }
        )

    def response(
        self,
        *,
        status_code: int,
        response_model: str,
        text: str,
        input_tokens: int | None,
        output_tokens: int | None,
        finish_reason: str | None,
    ) -> None:
        if self.mode == "off":
            return
        event: dict[str, object] = {
            "event": "provider.response",
            "trace_id": self.trace_id,
            "endpoint": self.endpoint,
            "request_model": self.model,
            "response_model": response_model,
            "status_code": status_code,
            "latency_ms": round((perf_counter() - self.started_at) * 1000),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "finish_reason": finish_reason,
            "response_chars": len(text),
            "trace_mode": self.mode,
        }
        if self.mode in {"summary", "content"}:
            event["response_text"] = _preview(text, self.max_chars)
        _emit(event)

    def error(
        self,
        *,
        reason: str,
        status_code: int | None = None,
        response_body: str = "",
    ) -> None:
        if self.mode == "off":
            return
        event: dict[str, object] = {
            "event": "provider.error",
            "trace_id": self.trace_id,
            "endpoint": self.endpoint,
            "model": self.model,
            "status_code": status_code,
            "reason": reason,
            "latency_ms": round((perf_counter() - self.started_at) * 1000),
            "trace_mode": self.mode,
        }
        if response_body and self.mode in {"summary", "content"}:
            event["response_body"] = _preview(response_body, self.max_chars)
        _emit(event)


__all__ = ["ProviderTrace", "ProviderTraceMode"]
