"""Phase 1 shadow graph used to validate Character Relay orchestration contracts."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from echo_masque.orchestration.runtime_context import OrchestrationRuntimeContext
from echo_masque.orchestration.state import CharacterRuntimeState
from echo_masque.orchestration.trace import RuntimeTraceEvent


def _foundation_node(
    state: CharacterRuntimeState,
    runtime: Runtime[OrchestrationRuntimeContext],
) -> CharacterRuntimeState:
    """Exercise state/context/trace plumbing without changing product behavior."""

    trace_id = state.get("trace_id", "")
    graph_run_id = state.get("graph_run_id", "")
    sink = runtime.context.trace_sink
    if sink is not None:
        sink.emit(
            RuntimeTraceEvent(
                trace_id=trace_id,
                graph_run_id=graph_run_id,
                graph_name="foundation",
                node_name="foundation",
                node_kind="foundation",
                status="started",
            )
        )

    update: CharacterRuntimeState = {
        "graph_name": "foundation",
        "orchestration_version": runtime.context.orchestration_version,
        "status": "completed",
    }

    if sink is not None:
        sink.emit(
            RuntimeTraceEvent(
                trace_id=trace_id,
                graph_run_id=graph_run_id,
                graph_name="foundation",
                node_name="foundation",
                node_kind="foundation",
                status="completed",
                changed_keys=("graph_name", "orchestration_version", "status"),
                metadata=(("shadow_mode", str(runtime.context.shadow_mode).lower()),),
            )
        )
    return update


def build_foundation_graph() -> Any:
    """Compile the Phase 1 graph; production traffic is not wired to it yet."""

    builder = StateGraph(
        state_schema=CharacterRuntimeState,
        context_schema=OrchestrationRuntimeContext,
    )
    builder.add_node("foundation", _foundation_node)
    builder.add_edge(START, "foundation")
    builder.add_edge("foundation", END)
    return builder.compile()


__all__ = ["build_foundation_graph"]
