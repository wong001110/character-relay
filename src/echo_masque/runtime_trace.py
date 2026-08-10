"""Privacy-safe Runtime Trace contract shared by orchestration and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

TraceNodeKind = Literal[
    "context",
    "retrieval",
    "decision",
    "agentic",
    "capability",
    "side_effect",
    "authority",
]
TraceEventStatus = Literal["started", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class RuntimeTraceEvent:
    """One bounded orchestration trace event without prompt or user content."""

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
    def emit(self, event: RuntimeTraceEvent) -> None: ...


__all__ = [
    "RuntimeTraceEvent",
    "RuntimeTraceSink",
    "TraceEventStatus",
    "TraceNodeKind",
]
