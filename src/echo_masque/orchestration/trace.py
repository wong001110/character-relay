"""Privacy-safe trace contracts for LangGraph orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

TraceNodeKind = Literal[
    "decision",
    "context",
    "agentic",
    "capability",
    "authority",
    "state",
    "side_effect",
    "foundation",
]
TraceEventStatus = Literal["started", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class RuntimeTraceEvent:
    """One orchestration event suitable for the future Runtime Trace Explorer.

    Metadata must remain classification-level only. Do not place credentials, raw prompts,
    retrieved private content, Tool arguments/results, authorization headers, or other secret
    material in this contract.
    """

    trace_id: str
    graph_run_id: str
    graph_name: str
    node_name: str
    node_kind: TraceNodeKind
    status: TraceEventStatus
    operation_id: str = ""
    owner_id: str = ""
    deployment_id: str = ""
    character_card_id: str = ""
    changed_keys: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    error: str = ""


class RuntimeTraceSink(Protocol):
    """Minimal sink interface so tracing remains independent from Provider Trace storage."""

    def emit(self, event: RuntimeTraceEvent) -> None:
        """Record one privacy-safe orchestration event."""


__all__ = [
    "RuntimeTraceEvent",
    "RuntimeTraceSink",
    "TraceEventStatus",
    "TraceNodeKind",
]
