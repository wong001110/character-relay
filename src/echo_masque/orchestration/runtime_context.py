"""Run-scoped dependency context for Character Relay graphs."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.orchestration.trace import RuntimeTraceSink


@dataclass(frozen=True, slots=True)
class OrchestrationRuntimeContext:
    """Static per-run dependencies and migration controls.

    Phase 1 intentionally keeps existing Character Relay services outside graph state. Later
    phases will add typed service adapters here as individual production graphs are migrated.
    """

    orchestration_version: str = "langgraph-phase-1"
    shadow_mode: bool = True
    trace_sink: RuntimeTraceSink | None = None


__all__ = ["OrchestrationRuntimeContext"]
