"""Phase 3 direct-runtime LangGraph pilot for one Character turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from echo_masque.api.connector_schemas import DiscordConnectorReplyView, DiscordInboundMessage
from echo_masque.connector_runtime import (
    DiscordConnectorRuntime,
    PreparedCharacterTurn,
    ResolvedCharacterOutput,
    ResolvedCharacterTurn,
)
from echo_masque.domain import TargetResponse
from echo_masque.orchestration.trace import (
    RuntimeTraceEvent,
    RuntimeTraceSink,
    TraceNodeKind,
)

CharacterTurnOutcome = Literal["pending", "silent", "reply", "expression", "failed"]
StageStatus = Literal["not_started", "running", "completed", "skipped", "failed"]
GraphStatus = Literal["pending", "running", "completed", "failed"]


class CharacterTurnGraphState(TypedDict, total=False):
    """Privacy-safe coordination state for one Character turn.

    Raw messages, prompts, RAG excerpts, credentials, provider responses, Tool arguments,
    Tool results, and final reply text remain transient in graph context and are not state.
    Phase 3 does not add a checkpointer.
    """

    trace_id: str
    graph_run_id: str
    graph_name: Literal["character_turn"]
    orchestration_version: str
    status: GraphStatus
    outcome: CharacterTurnOutcome
    owner_id: str
    deployment_id: str
    character_card_id: str
    platform: str
    connection_id: str
    guild_id: str
    channel_id: str
    thread_id: str
    resolve_status: StageStatus
    context_status: StageStatus
    rag_status: StageStatus
    model_status: StageStatus
    tool_result_count: int
    smart_output_status: StageStatus
    authority_status: StageStatus
    errors: tuple[str, ...]


@dataclass(slots=True)
class CharacterTurnGraphContext:
    """Transient dependencies and raw turn values for one graph run."""

    payload: DiscordInboundMessage
    runtime: DiscordConnectorRuntime
    trace_sink: RuntimeTraceSink | None = None
    orchestration_version: str = "langgraph-phase-3-direct-pilot"
    resolved: ResolvedCharacterTurn | None = None
    prepared: PreparedCharacterTurn | None = None
    response: TargetResponse | None = None
    output: ResolvedCharacterOutput | None = None
    reply: DiscordConnectorReplyView | None = None


@dataclass(frozen=True, slots=True)
class CharacterTurnGraphResult:
    state: CharacterTurnGraphState
    reply: DiscordConnectorReplyView


def _emit(
    state: CharacterTurnGraphState,
    context: CharacterTurnGraphContext,
    *,
    node_name: str,
    node_kind: TraceNodeKind,
    status: Literal["started", "completed", "failed"],
    changed_keys: tuple[str, ...] = (),
    metadata: tuple[tuple[str, str], ...] = (),
    error: str = "",
) -> None:
    if context.trace_sink is None:
        return
    context.trace_sink.emit(
        RuntimeTraceEvent(
            trace_id=state.get("trace_id", ""),
            graph_run_id=state.get("graph_run_id", ""),
            graph_name="character_turn",
            node_name=node_name,
            node_kind=node_kind,
            status=status,
            changed_keys=changed_keys,
            metadata=metadata,
            error=error[:300],
        )
    )


def _resolve_turn(
    state: CharacterTurnGraphState,
    runtime: Runtime[CharacterTurnGraphContext],
) -> CharacterTurnGraphState:
    context = runtime.context
    _emit(state, context, node_name="turn_resolve", node_kind="decision", status="started")
    try:
        resolved, early_reply = context.runtime.resolve_character_turn(context.payload)
    except Exception as exc:
        _emit(
            state,
            context,
            node_name="turn_resolve",
            node_kind="decision",
            status="failed",
            changed_keys=("resolve_status", "status", "outcome"),
            error=str(exc),
        )
        raise
    if early_reply is not None:
        context.reply = early_reply
        update: CharacterTurnGraphState = {
            "resolve_status": "completed",
            "status": "completed",
            "outcome": "silent",
            "deployment_id": early_reply.deployment_id or context.payload.deployment_id,
        }
        _emit(
            state,
            context,
            node_name="turn_resolve",
            node_kind="decision",
            status="completed",
            changed_keys=("resolve_status", "status", "outcome", "deployment_id"),
            metadata=(("result", early_reply.reason),),
        )
        return update
    if resolved is None:
        raise RuntimeError("Character Turn graph resolution returned no runtime result.")
    context.resolved = resolved
    deployment = resolved.deployment
    update = {
        "resolve_status": "completed",
        "status": "running",
        "owner_id": deployment.owner_id,
        "deployment_id": deployment.id,
        "character_card_id": resolved.card.id,
        "platform": deployment.platform,
        "connection_id": deployment.connection_id,
        "guild_id": context.payload.guild_id,
        "channel_id": context.payload.channel_id,
        "thread_id": context.payload.thread_id,
    }
    _emit(
        state,
        context,
        node_name="turn_resolve",
        node_kind="decision",
        status="completed",
        changed_keys=tuple(update.keys()),
        metadata=(("target_kind", resolved.target_record.target_kind),),
    )
    return update


def _route_after_resolve(state: CharacterTurnGraphState) -> str:
    return "end" if state.get("outcome") == "silent" else "context"


def _build_context(
    state: CharacterTurnGraphState,
    runtime: Runtime[CharacterTurnGraphContext],
) -> CharacterTurnGraphState:
    context = runtime.context
    _emit(state, context, node_name="turn_context", node_kind="context", status="started")
    if context.resolved is None:
        raise RuntimeError("Character Turn graph lost resolved runtime dependencies.")
    try:
        prepared = context.runtime.prepare_character_turn(context.resolved)
    except Exception as exc:
        _emit(
            state,
            context,
            node_name="turn_context",
            node_kind="context",
            status="failed",
            changed_keys=("context_status", "rag_status", "status", "outcome"),
            error=str(exc),
        )
        raise
    context.prepared = prepared
    rag_status: StageStatus = "completed" if prepared.turn_context is not None else "skipped"
    _emit(
        state,
        context,
        node_name="turn_context",
        node_kind="context",
        status="completed",
        changed_keys=("context_status", "rag_status"),
        metadata=(("rag_pipeline", "available" if prepared.turn_context is not None else "none"),),
    )
    return {"context_status": "completed", "rag_status": rag_status}


async def _invoke_model(
    state: CharacterTurnGraphState,
    runtime: Runtime[CharacterTurnGraphContext],
) -> CharacterTurnGraphState:
    context = runtime.context
    _emit(state, context, node_name="turn_model", node_kind="agentic", status="started")
    if context.prepared is None:
        raise RuntimeError("Character Turn graph lost prepared context.")
    try:
        response = await context.runtime.invoke_character_model(context.prepared)
    except Exception as exc:
        _emit(
            state,
            context,
            node_name="turn_model",
            node_kind="agentic",
            status="failed",
            changed_keys=("model_status", "status", "outcome"),
            error=str(exc),
        )
        raise
    context.response = response
    tool_count = len(context.runtime._tool_traces(response.trace))
    _emit(
        state,
        context,
        node_name="turn_model",
        node_kind="agentic",
        status="completed",
        changed_keys=("model_status", "tool_result_count"),
        metadata=(("tool_result_count", str(tool_count)),),
    )
    return {"model_status": "completed", "tool_result_count": tool_count}


async def _resolve_smart_output(
    state: CharacterTurnGraphState,
    runtime: Runtime[CharacterTurnGraphContext],
) -> CharacterTurnGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="turn_smart_output",
        node_kind="decision",
        status="started",
    )
    if context.prepared is None or context.response is None:
        raise RuntimeError("Character Turn graph lost model output before Smart Output.")
    try:
        output = await context.runtime.resolve_character_output(
            context.prepared,
            context.response,
        )
    except Exception as exc:
        _emit(
            state,
            context,
            node_name="turn_smart_output",
            node_kind="decision",
            status="failed",
            changed_keys=("smart_output_status", "status", "outcome"),
            error=str(exc),
        )
        raise
    context.output = output
    _emit(
        state,
        context,
        node_name="turn_smart_output",
        node_kind="decision",
        status="completed",
        changed_keys=("smart_output_status",),
        metadata=(("action", output.smart_output.action), ("resolution", output.smart_reason)),
    )
    return {"smart_output_status": "completed"}


def _authorize_output(
    state: CharacterTurnGraphState,
    runtime: Runtime[CharacterTurnGraphContext],
) -> CharacterTurnGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="turn_authority",
        node_kind="authority",
        status="started",
    )
    if context.prepared is None or context.output is None:
        raise RuntimeError("Character Turn graph lost output before Runtime authority.")
    try:
        reply = context.runtime.authorize_character_output(context.prepared, context.output)
    except Exception as exc:
        _emit(
            state,
            context,
            node_name="turn_authority",
            node_kind="authority",
            status="failed",
            changed_keys=("authority_status", "status", "outcome"),
            error=str(exc),
        )
        raise
    context.reply = reply
    outcome = cast(CharacterTurnOutcome, reply.action)
    _emit(
        state,
        context,
        node_name="turn_authority",
        node_kind="authority",
        status="completed",
        changed_keys=("authority_status", "status", "outcome"),
        metadata=(("action", reply.action), ("reason", reply.reason)),
    )
    return {
        "authority_status": "completed",
        "status": "completed",
        "outcome": outcome,
    }


def build_character_turn_graph() -> Any:
    """Compile the Phase 3 direct-runtime Character Turn graph."""

    builder = StateGraph(
        state_schema=CharacterTurnGraphState,
        context_schema=CharacterTurnGraphContext,
    )
    builder.add_node("turn_resolve", _resolve_turn)
    builder.add_node("turn_context", _build_context)
    builder.add_node("turn_model", _invoke_model)
    builder.add_node("turn_smart_output", _resolve_smart_output)
    builder.add_node("turn_authority", _authorize_output)
    builder.add_edge(START, "turn_resolve")
    builder.add_conditional_edges(
        "turn_resolve",
        _route_after_resolve,
        {"context": "turn_context", "end": END},
    )
    builder.add_edge("turn_context", "turn_model")
    builder.add_edge("turn_model", "turn_smart_output")
    builder.add_edge("turn_smart_output", "turn_authority")
    builder.add_edge("turn_authority", END)
    return builder.compile()


class CharacterTurnGraphRunner:
    """Run Phase 3 directly without changing production Discord routing yet."""

    def __init__(
        self,
        runtime: DiscordConnectorRuntime,
        *,
        trace_sink: RuntimeTraceSink | None = None,
    ) -> None:
        self.runtime = runtime
        self.trace_sink = trace_sink
        self.graph = build_character_turn_graph()

    async def run(self, payload: DiscordInboundMessage) -> CharacterTurnGraphResult:
        context = CharacterTurnGraphContext(
            payload=payload,
            runtime=self.runtime,
            trace_sink=self.trace_sink,
        )
        state: CharacterTurnGraphState = {
            "trace_id": str(uuid4()),
            "graph_run_id": str(uuid4()),
            "graph_name": "character_turn",
            "orchestration_version": context.orchestration_version,
            "status": "pending",
            "outcome": "pending",
            "deployment_id": payload.deployment_id,
            "resolve_status": "not_started",
            "context_status": "not_started",
            "rag_status": "not_started",
            "model_status": "not_started",
            "tool_result_count": 0,
            "smart_output_status": "not_started",
            "authority_status": "not_started",
            "errors": (),
        }
        result = cast(
            CharacterTurnGraphState,
            await self.graph.ainvoke(state, context=context),
        )
        if context.reply is None:
            raise RuntimeError("Character Turn graph completed without a reply view.")
        return CharacterTurnGraphResult(state=result, reply=context.reply)

    async def __call__(self, payload: DiscordInboundMessage) -> DiscordConnectorReplyView:
        return (await self.run(payload)).reply


__all__ = [
    "CharacterTurnGraphContext",
    "CharacterTurnGraphResult",
    "CharacterTurnGraphRunner",
    "CharacterTurnGraphState",
    "CharacterTurnOutcome",
    "build_character_turn_graph",
]
