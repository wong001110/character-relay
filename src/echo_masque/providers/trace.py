"""Bounded model-provider tracing routed to a private persistence sink."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from typing import Literal
from uuid import uuid4

from echo_masque.providers.base import ChatMessage

ProviderTraceMode = Literal["off", "metadata", "summary", "content"]
ProviderTraceSink = Callable[[dict[str, object]], None]
_DEFAULT_TRACE_MODE: ProviderTraceMode = "summary"
_DEFAULT_MAX_CHARS = 4000
_TRACE_SINK: ProviderTraceSink | None = None


@dataclass(frozen=True)
class _ProviderTraceScope:
    owner_id: str = ""
    deployment_id: str = ""
    character_card_id: str = ""
    operation_id: str = ""
    graph_run_id: str = ""
    runtime_node: str = ""


_TRACE_SCOPE: ContextVar[_ProviderTraceScope | None] = ContextVar(
    "provider_trace_scope",
    default=None,
)


def configure_provider_trace_sink(sink: ProviderTraceSink | None) -> None:
    """Install the process-level private trace sink used by provider adapters."""

    global _TRACE_SINK
    _TRACE_SINK = sink


@contextmanager
def provider_trace_scope(
    *,
    owner_id: str | None = None,
    deployment_id: str | None = None,
    character_card_id: str | None = None,
    operation_id: str | None = None,
    graph_run_id: str | None = None,
    runtime_node: str | None = None,
) -> Iterator[None]:
    """Bind account/runtime identifiers to provider traces for the current async context."""

    current = _TRACE_SCOPE.get() or _ProviderTraceScope()
    scope = _ProviderTraceScope(
        owner_id=owner_id.strip() if owner_id is not None else current.owner_id,
        deployment_id=(
            deployment_id.strip() if deployment_id is not None else current.deployment_id
        ),
        character_card_id=(
            character_card_id.strip()
            if character_card_id is not None
            else current.character_card_id
        ),
        operation_id=(
            operation_id.strip() if operation_id is not None else current.operation_id
        ),
        graph_run_id=(
            graph_run_id.strip() if graph_run_id is not None else current.graph_run_id
        ),
        runtime_node=(
            runtime_node.strip() if runtime_node is not None else current.runtime_node
        ),
    )
    token = _TRACE_SCOPE.set(scope)
    try:
        yield
    finally:
        _TRACE_SCOPE.reset(token)


def _trace_mode() -> ProviderTraceMode:
    raw = os.getenv("CHARACTER_RELAY_PROVIDER_TRACE_MODE", _DEFAULT_TRACE_MODE).strip().lower()
    if raw in {"off", "metadata", "summary", "content"}:
        return raw  # type: ignore[return-value]
    return _DEFAULT_TRACE_MODE


def _max_chars() -> int:
    raw = os.getenv(
        "CHARACTER_RELAY_PROVIDER_TRACE_MAX_CHARS",
        str(_DEFAULT_MAX_CHARS),
    ).strip()
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


def _prior_tool_call_names(messages: tuple[ChatMessage, ...]) -> list[str]:
    names: list[str] = []
    for message in messages:
        for call in message.tool_calls:
            name = call.function.name.strip()
            if name and name not in names:
                names.append(name)
    return names


def _emit(payload: dict[str, object]) -> None:
    sink = _TRACE_SINK
    if sink is None:
        return
    try:
        sink(payload)
    except Exception:
        return


@dataclass(frozen=True)
class ProviderTrace:
    """One correlated trace for a provider request and its eventual result."""

    trace_id: str
    mode: ProviderTraceMode
    max_chars: int
    endpoint: str
    model: str
    started_at: float
    owner_id: str = ""
    deployment_id: str = ""
    character_card_id: str = ""
    operation_id: str = ""
    graph_run_id: str = ""
    runtime_node: str = ""

    @classmethod
    def start(
        cls,
        *,
        endpoint: str,
        model: str,
        temperature: float,
        messages: tuple[ChatMessage, ...],
        available_tool_names: tuple[str, ...] = (),
        tool_schema_count: int = 0,
        tool_schema_chars: int = 0,
    ) -> ProviderTrace:
        mode = _trace_mode()
        scope = _TRACE_SCOPE.get() or _ProviderTraceScope()
        trace = cls(
            trace_id=str(uuid4()),
            mode=mode,
            max_chars=_max_chars(),
            endpoint=endpoint,
            model=model,
            started_at=perf_counter(),
            owner_id=scope.owner_id,
            deployment_id=scope.deployment_id,
            character_card_id=scope.character_card_id,
            operation_id=scope.operation_id,
            graph_run_id=scope.graph_run_id,
            runtime_node=scope.runtime_node,
        )
        if mode == "off":
            return trace

        system_chars = sum(len(item.content) for item in messages if item.role == "system")
        prior_tools = _prior_tool_call_names(messages)
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
            "available_tool_names": list(dict.fromkeys(available_tool_names)),
            "tool_schema_count": max(0, tool_schema_count),
            "tool_schema_chars": max(0, tool_schema_chars),
            "prior_tool_call_names": prior_tools,
            "tool_result_count": sum(1 for item in messages if item.role == "tool"),
            "trace_mode": mode,
            **trace._scope_payload(),
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
                "trace_mode": self.mode,
                **self._scope_payload(),
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
        tool_call_names: tuple[str, ...] = (),
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
            "tool_call_names": list(dict.fromkeys(tool_call_names)),
            "trace_mode": self.mode,
            **self._scope_payload(),
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
        detail: str = "",
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
            **self._scope_payload(),
        }
        if detail:
            event["detail"] = _preview(detail, min(self.max_chars, 1000))
        if response_body and self.mode in {"summary", "content"}:
            event["response_body"] = _preview(response_body, self.max_chars)
        _emit(event)

    def _scope_payload(self) -> dict[str, str]:
        return {
            "owner_id": self.owner_id,
            "deployment_id": self.deployment_id,
            "character_card_id": self.character_card_id,
            "operation_id": self.operation_id,
            "graph_run_id": self.graph_run_id,
            "runtime_node": self.runtime_node,
        }


__all__ = [
    "ProviderTrace",
    "ProviderTraceMode",
    "ProviderTraceSink",
    "configure_provider_trace_sink",
    "provider_trace_scope",
]
