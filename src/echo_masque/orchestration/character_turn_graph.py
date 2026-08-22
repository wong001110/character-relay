"""Phase 3 LangGraph orchestration for one Character turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from echo_masque.api.connector_schemas import DiscordConnectorReplyView, DiscordInboundMessage
from echo_masque.character_invite_runtime import (
    CharacterInviteTurnState,
    activate_character_invite_turn,
    current_character_invite_turn,
)
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
from echo_masque.providers.trace import provider_trace_scope
from echo_masque.smart_output import SmartMentionPart
from echo_masque.targets import PromptModelToolTurn

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
    operation_id: str
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
    tool_status: StageStatus
    tool_rounds: int
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
    orchestration_version: str = "langgraph-phase-3"
    resolved: ResolvedCharacterTurn | None = None
    prepared: PreparedCharacterTurn | None = None
    invite_turn_state: CharacterInviteTurnState | None = None
    tool_turn: PromptModelToolTurn | None = None
    response: TargetResponse | None = None
    output: ResolvedCharacterOutput | None = None
    reply: DiscordConnectorReplyView | None = None


@dataclass(frozen=True, slots=True)
class CharacterTurnGraphResult:
    state: CharacterTurnGraphState
    reply: DiscordConnectorReplyView
    invite_candidate_deployment_id: str = ""
    mentioned_character_deployment_ids: tuple[str, ...] = ()


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
            operation_id=state.get("operation_id", ""),
            owner_id=state.get("owner_id", ""),
            deployment_id=state.get("deployment_id", ""),
            character_card_id=state.get("character_card_id", ""),
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
        deployment = context.resolved.deployment
        with provider_trace_scope(
            owner_id=deployment.owner_id,
            deployment_id=deployment.id,
            character_card_id=context.resolved.card.id,
            operation_id=state.get("operation_id", ""),
            graph_run_id=state.get("graph_run_id", ""),
            runtime_node="turn_context",
        ):
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
    if prepared.context_error:
        context.reply = DiscordConnectorReplyView(
            action="silent",
            reason=prepared.context_error,
            deployment_id=prepared.resolved.deployment.id,
            character_display_name=prepared.resolved.card.display_name,
            context_trace=(
                prepared.turn_context.trace if prepared.turn_context is not None else None
            ),
        )
        _emit(
            state,
            context,
            node_name="turn_context",
            node_kind="context",
            status="completed",
            changed_keys=("context_status", "rag_status", "status", "outcome"),
            metadata=(("result", prepared.context_error),),
        )
        return {
            "context_status": "failed",
            "rag_status": "failed",
            "status": "completed",
            "outcome": "silent",
        }
    invite_turn_state = current_character_invite_turn()
    if (
        invite_turn_state is not None
        and invite_turn_state.turn_token == prepared.smart_context.invite_turn_token
        and invite_turn_state.deployment_id == prepared.resolved.deployment.id
    ):
        context.invite_turn_state = invite_turn_state
    else:
        context.invite_turn_state = None
    rag_status: StageStatus = "completed" if prepared.context_bundle is not None else "skipped"
    _emit(
        state,
        context,
        node_name="turn_context",
        node_kind="context",
        status="completed",
        changed_keys=("context_status", "rag_status"),
        metadata=(("rag_pipeline", "v3" if prepared.context_bundle is not None else "none"),),
    )
    return {"context_status": "completed", "rag_status": rag_status}


def _route_after_context(state: CharacterTurnGraphState) -> str:
    return "end" if state.get("outcome") == "silent" else "model"


async def _invoke_model(
    state: CharacterTurnGraphState,
    runtime: Runtime[CharacterTurnGraphContext],
) -> CharacterTurnGraphState:
    context = runtime.context
    _emit(state, context, node_name="turn_model", node_kind="agentic", status="started")
    prepared = context.prepared
    if prepared is None:
        raise RuntimeError("Character Turn graph lost prepared context.")
    response: TargetResponse | None
    try:
        deployment = prepared.resolved.deployment
        with provider_trace_scope(
            owner_id=deployment.owner_id,
            deployment_id=deployment.id,
            character_card_id=prepared.resolved.card.id,
            operation_id=state.get("operation_id", ""),
            graph_run_id=state.get("graph_run_id", ""),
            runtime_node="turn_model",
        ):
            if context.tool_turn is None:
                context.tool_turn = await context.runtime.start_character_tool_turn(prepared)
            if context.tool_turn is None:
                response = await context.runtime.invoke_character_model(prepared)
            else:
                response = await context.runtime.advance_character_tool_model(
                    prepared,
                    context.tool_turn,
                )
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

    if response is None:
        turn = context.tool_turn
        if turn is None or not turn.pending_tool_calls:
            raise RuntimeError("Character model requested Tool routing without pending calls.")
        _emit(
            state,
            context,
            node_name="turn_model",
            node_kind="agentic",
            status="completed",
            changed_keys=("model_status", "tool_rounds"),
            metadata=(
                ("next", "tool_execution"),
                ("tool_rounds", str(turn.tool_rounds)),
            ),
        )
        return {
            "model_status": "running",
            "tool_rounds": turn.tool_rounds,
        }

    context.response = response
    turn = context.tool_turn
    tool_count = (
        len(turn.traces)
        if turn is not None
        else len(context.runtime._tool_traces(response.trace))
    )
    tool_rounds = turn.tool_rounds if turn is not None else 0
    _emit(
        state,
        context,
        node_name="turn_model",
        node_kind="agentic",
        status="completed",
        changed_keys=("model_status", "tool_rounds", "tool_result_count"),
        metadata=(
            ("next", "smart_output"),
            ("tool_rounds", str(tool_rounds)),
            ("tool_result_count", str(tool_count)),
        ),
    )
    return {
        "model_status": "completed",
        "tool_rounds": tool_rounds,
        "tool_result_count": tool_count,
    }


def _route_after_model(state: CharacterTurnGraphState) -> str:
    return "tools" if state.get("model_status") == "running" else "smart_output"


async def _execute_tools(
    state: CharacterTurnGraphState,
    runtime: Runtime[CharacterTurnGraphContext],
) -> CharacterTurnGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="turn_tool_execution",
        node_kind="capability",
        status="started",
    )
    prepared = context.prepared
    turn = context.tool_turn
    if prepared is None or turn is None:
        raise RuntimeError("Character Turn graph lost its pending Tool session.")
    try:
        if context.invite_turn_state is not None:
            activate_character_invite_turn(context.invite_turn_state)
        executed_count = await context.runtime.execute_character_tools(prepared, turn)
    except Exception as exc:
        _emit(
            state,
            context,
            node_name="turn_tool_execution",
            node_kind="capability",
            status="failed",
            changed_keys=("tool_status", "status", "outcome"),
            error=str(exc),
        )
        raise
    _emit(
        state,
        context,
        node_name="turn_tool_execution",
        node_kind="capability",
        status="completed",
        changed_keys=("tool_status", "tool_rounds", "tool_result_count"),
        metadata=(
            ("executed_count", str(executed_count)),
            ("tool_rounds", str(turn.tool_rounds)),
            ("tool_result_count", str(len(turn.traces))),
        ),
    )
    return {
        "tool_status": "completed",
        "tool_rounds": turn.tool_rounds,
        "tool_result_count": len(turn.traces),
    }


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
        if context.invite_turn_state is not None:
            activate_character_invite_turn(context.invite_turn_state)
        deployment = context.prepared.resolved.deployment
        with provider_trace_scope(
            owner_id=deployment.owner_id,
            deployment_id=deployment.id,
            character_card_id=context.prepared.resolved.card.id,
            operation_id=state.get("operation_id", ""),
            graph_run_id=state.get("graph_run_id", ""),
            runtime_node="turn_smart_output",
        ):
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

    epistemic_metadata: tuple[tuple[str, str], ...] = ()
    metadata_provider = getattr(context.runtime, "epistemic_trace_metadata", None)
    if callable(metadata_provider):
        candidate = metadata_provider(context.prepared)
        if isinstance(candidate, tuple):
            epistemic_metadata = candidate
    if epistemic_metadata:
        _emit(
            state,
            context,
            node_name="turn_media_epistemic",
            node_kind="state",
            status="completed",
            metadata=epistemic_metadata,
        )

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
    """Compile the Phase 3 Character Turn graph."""

    builder = StateGraph(
        state_schema=CharacterTurnGraphState,
        context_schema=CharacterTurnGraphContext,
    )
    builder.add_node("turn_resolve", _resolve_turn)
    builder.add_node("turn_context", _build_context)
    builder.add_node("turn_model", _invoke_model)
    builder.add_node("turn_tool_execution", _execute_tools)
    builder.add_node("turn_smart_output", _resolve_smart_output)
    builder.add_node("turn_authority", _authorize_output)
    builder.add_edge(START, "turn_resolve")
    builder.add_conditional_edges(
        "turn_resolve",
        _route_after_resolve,
        {"context": "turn_context", "end": END},
    )
    builder.add_conditional_edges(
        "turn_context",
        _route_after_context,
        {"model": "turn_model", "end": END},
    )
    builder.add_conditional_edges(
        "turn_model",
        _route_after_model,
        {
            "tools": "turn_tool_execution",
            "smart_output": "turn_smart_output",
        },
    )
    builder.add_edge("turn_tool_execution", "turn_model")
    builder.add_edge("turn_smart_output", "turn_authority")
    builder.add_edge("turn_authority", END)
    return builder.compile()


class CharacterTurnGraphRunner:
    """Run one reusable Character turn while Runtime services remain authoritative."""

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
            "operation_id": payload.runtime_operation_id,
            "status": "pending",
            "outcome": "pending",
            "deployment_id": payload.deployment_id,
            "resolve_status": "not_started",
            "context_status": "not_started",
            "rag_status": "not_started",
            "model_status": "not_started",
            "tool_status": "not_started",
            "tool_rounds": 0,
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
        mentioned: tuple[str, ...] = ()
        invite_candidate = ""
        smart_output = context.reply.smart_output
        if smart_output is not None and smart_output.action == "message":
            mentioned = tuple(
                part.mention.removeprefix("deployment:")
                for part in smart_output.content
                if isinstance(part, SmartMentionPart)
                and part.mention.startswith("deployment:")
            )
            proposal = (
                context.invite_turn_state.proposals[0]
                if context.invite_turn_state is not None
                and context.invite_turn_state.proposals
                else None
            )
            if proposal is not None and proposal.candidate_deployment_id in mentioned:
                invite_candidate = proposal.candidate_deployment_id
        return CharacterTurnGraphResult(
            state=result,
            reply=context.reply,
            invite_candidate_deployment_id=invite_candidate,
            mentioned_character_deployment_ids=mentioned,
        )

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
