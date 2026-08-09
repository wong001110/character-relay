"""Phase 2 LangGraph pilot for one claimed Condition Watch attempt."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from echo_masque.condition_watch_service import (
    ConditionEvaluator,
    ConditionNotifier,
    ConditionWatchEvaluation,
)
from echo_masque.orchestration.trace import (
    RuntimeTraceEvent,
    RuntimeTraceSink,
    TraceNodeKind,
)
from echo_masque.persistence.condition_watch_models import ConditionWatchRecord
from echo_masque.persistence.condition_watch_repository import ConditionWatchRepository

WatchOutcome = Literal["pending", "not_met", "triggered", "failed"]
NotificationStatus = Literal["not_started", "completed", "failed"]
GraphStatus = Literal["pending", "running", "completed", "failed"]


class ConditionWatchGraphState(TypedDict, total=False):
    """Privacy-safe coordination state for one Condition Watch attempt.

    The persisted Condition Watch record, provider credentials, prompts, Tool results, and
    evaluation summary remain outside graph state. Phase 2 does not add a checkpointer.
    """

    trace_id: str
    graph_run_id: str
    graph_name: Literal["condition_watch"]
    orchestration_version: str
    watch_id: str
    status: GraphStatus
    outcome: WatchOutcome
    evaluation_triggered: bool
    notification_status: NotificationStatus


@dataclass(slots=True)
class ConditionWatchGraphContext:
    """Run-scoped dependencies and transient values for one claimed watch."""

    watch: ConditionWatchRecord
    repository: ConditionWatchRepository
    evaluator: ConditionEvaluator
    notifier: ConditionNotifier
    trace_sink: RuntimeTraceSink | None = None
    orchestration_version: str = "langgraph-phase-2"
    evaluation: ConditionWatchEvaluation | None = None
    error: str = ""


def _emit(
    state: ConditionWatchGraphState,
    context: ConditionWatchGraphContext,
    *,
    node_name: str,
    node_kind: TraceNodeKind,
    status: Literal["started", "completed", "failed"],
    changed_keys: tuple[str, ...] = (),
    metadata: tuple[tuple[str, str], ...] = (),
    error: str = "",
) -> None:
    sink = context.trace_sink
    if sink is None:
        return
    sink.emit(
        RuntimeTraceEvent(
            trace_id=state.get("trace_id", ""),
            graph_run_id=state.get("graph_run_id", ""),
            graph_name="condition_watch",
            node_name=node_name,
            node_kind=node_kind,
            status=status,
            changed_keys=changed_keys,
            metadata=metadata,
            error=error[:300],
        )
    )


async def _evaluate_watch(
    state: ConditionWatchGraphState,
    runtime: Runtime[ConditionWatchGraphContext],
) -> ConditionWatchGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="watch_evaluate",
        node_kind="agentic",
        status="started",
    )
    try:
        evaluation = await context.evaluator(context.watch)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        context.error = str(exc)
        _emit(
            state,
            context,
            node_name="watch_evaluate",
            node_kind="agentic",
            status="failed",
            changed_keys=("outcome", "status"),
            error=context.error,
        )
        return {"outcome": "failed", "status": "failed"}

    context.evaluation = evaluation
    update: ConditionWatchGraphState = {
        "evaluation_triggered": evaluation.triggered,
        "outcome": "triggered" if evaluation.triggered else "not_met",
        "status": "running",
    }
    _emit(
        state,
        context,
        node_name="watch_evaluate",
        node_kind="agentic",
        status="completed",
        changed_keys=("evaluation_triggered", "outcome", "status"),
        metadata=(("triggered", str(evaluation.triggered).lower()),),
    )
    return update


def _route_after_evaluation(state: ConditionWatchGraphState) -> str:
    outcome = state.get("outcome", "failed")
    if outcome == "triggered":
        return "notify"
    if outcome == "not_met":
        return "not_met"
    return "failed"


async def _notify_watch(
    state: ConditionWatchGraphState,
    runtime: Runtime[ConditionWatchGraphContext],
) -> ConditionWatchGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="watch_notify",
        node_kind="side_effect",
        status="started",
    )
    evaluation = context.evaluation
    if evaluation is None:
        context.error = "Condition Watch graph lost its evaluation result."
        _emit(
            state,
            context,
            node_name="watch_notify",
            node_kind="side_effect",
            status="failed",
            changed_keys=("notification_status", "outcome", "status"),
            error=context.error,
        )
        return {
            "notification_status": "failed",
            "outcome": "failed",
            "status": "failed",
        }

    try:
        await context.notifier(context.watch, evaluation)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        context.error = str(exc)
        _emit(
            state,
            context,
            node_name="watch_notify",
            node_kind="side_effect",
            status="failed",
            changed_keys=("notification_status", "outcome", "status"),
            error=context.error,
        )
        return {
            "notification_status": "failed",
            "outcome": "failed",
            "status": "failed",
        }

    _emit(
        state,
        context,
        node_name="watch_notify",
        node_kind="side_effect",
        status="completed",
        changed_keys=("notification_status",),
    )
    return {"notification_status": "completed"}


def _route_after_notification(state: ConditionWatchGraphState) -> str:
    if state.get("notification_status") == "completed":
        return "triggered"
    return "failed"


def _mark_not_met(
    state: ConditionWatchGraphState,
    runtime: Runtime[ConditionWatchGraphContext],
) -> ConditionWatchGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="watch_mark_not_met",
        node_kind="state",
        status="started",
    )
    context.repository.mark_not_met(context.watch.id)
    _emit(
        state,
        context,
        node_name="watch_mark_not_met",
        node_kind="state",
        status="completed",
        changed_keys=("outcome", "status"),
        metadata=(("business_transition", "not_met"),),
    )
    return {"outcome": "not_met", "status": "completed"}


def _mark_triggered(
    state: ConditionWatchGraphState,
    runtime: Runtime[ConditionWatchGraphContext],
) -> ConditionWatchGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="watch_mark_triggered",
        node_kind="state",
        status="started",
    )
    context.repository.mark_triggered(context.watch.id)
    _emit(
        state,
        context,
        node_name="watch_mark_triggered",
        node_kind="state",
        status="completed",
        changed_keys=("outcome", "status"),
        metadata=(("business_transition", "triggered"),),
    )
    return {"outcome": "triggered", "status": "completed"}


def _mark_failure(
    state: ConditionWatchGraphState,
    runtime: Runtime[ConditionWatchGraphContext],
) -> ConditionWatchGraphState:
    context = runtime.context
    error = context.error or "Condition Watch graph failed without an error message."
    _emit(
        state,
        context,
        node_name="watch_mark_failure",
        node_kind="state",
        status="started",
    )
    context.repository.mark_failure(context.watch.id, error)
    _emit(
        state,
        context,
        node_name="watch_mark_failure",
        node_kind="state",
        status="completed",
        changed_keys=("outcome", "status"),
        metadata=(("business_transition", "failure"),),
    )
    return {"outcome": "failed", "status": "failed"}


def build_condition_watch_graph() -> Any:
    """Compile the Phase 2 graph for one already-claimed Condition Watch attempt."""

    builder = StateGraph(
        state_schema=ConditionWatchGraphState,
        context_schema=ConditionWatchGraphContext,
    )
    builder.add_node("watch_evaluate", _evaluate_watch)
    builder.add_node("watch_notify", _notify_watch)
    builder.add_node("watch_mark_not_met", _mark_not_met)
    builder.add_node("watch_mark_triggered", _mark_triggered)
    builder.add_node("watch_mark_failure", _mark_failure)
    builder.add_edge(START, "watch_evaluate")
    builder.add_conditional_edges(
        "watch_evaluate",
        _route_after_evaluation,
        {
            "notify": "watch_notify",
            "not_met": "watch_mark_not_met",
            "failed": "watch_mark_failure",
        },
    )
    builder.add_conditional_edges(
        "watch_notify",
        _route_after_notification,
        {
            "triggered": "watch_mark_triggered",
            "failed": "watch_mark_failure",
        },
    )
    builder.add_edge("watch_mark_not_met", END)
    builder.add_edge("watch_mark_triggered", END)
    builder.add_edge("watch_mark_failure", END)
    return builder.compile()


class ConditionWatchGraphRunner:
    """Run the Phase 2 graph while existing repositories remain business authority."""

    def __init__(
        self,
        repository: ConditionWatchRepository,
        *,
        evaluator: ConditionEvaluator,
        notifier: ConditionNotifier,
        trace_sink: RuntimeTraceSink | None = None,
    ) -> None:
        self.repository = repository
        self.evaluator = evaluator
        self.notifier = notifier
        self.trace_sink = trace_sink
        self.graph = build_condition_watch_graph()

    async def run(self, watch: ConditionWatchRecord) -> ConditionWatchGraphState:
        context = ConditionWatchGraphContext(
            watch=watch,
            repository=self.repository,
            evaluator=self.evaluator,
            notifier=self.notifier,
            trace_sink=self.trace_sink,
        )
        state: ConditionWatchGraphState = {
            "trace_id": str(uuid4()),
            "graph_run_id": str(uuid4()),
            "graph_name": "condition_watch",
            "orchestration_version": context.orchestration_version,
            "watch_id": watch.id,
            "status": "pending",
            "outcome": "pending",
            "notification_status": "not_started",
        }
        result = await self.graph.ainvoke(state, context=context)
        return cast(ConditionWatchGraphState, result)

    async def __call__(self, watch: ConditionWatchRecord) -> None:
        await self.run(watch)


__all__ = [
    "ConditionWatchGraphContext",
    "ConditionWatchGraphRunner",
    "ConditionWatchGraphState",
    "NotificationStatus",
    "WatchOutcome",
    "build_condition_watch_graph",
]
