"""Compatibility re-export for the neutral Runtime Trace contract."""

from echo_masque.runtime_trace import (
    RuntimeTraceEvent,
    RuntimeTraceSink,
    TraceEventStatus,
    TraceNodeKind,
)

__all__ = [
    "RuntimeTraceEvent",
    "RuntimeTraceSink",
    "TraceEventStatus",
    "TraceNodeKind",
]
