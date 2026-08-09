"""Phase 4 stateless continuation graph for ordered multi-Character turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from echo_masque.api.social_turn_schemas import (
    DiscordSocialPendingTurn,
    DiscordSocialTurnCursor,
    DiscordSocialTurnStepRequest,
    DiscordSocialTurnStepView,
    SocialTurnOrigin,
)
from echo_masque.orchestration.character_turn_graph import (
    CharacterTurnGraphResult,
    CharacterTurnGraphRunner,
)
from echo_masque.orchestration.trace import (
    RuntimeTraceEvent,
    RuntimeTraceSink,
    TraceNodeKind,
)

SocialGraphStatus = Literal["pending", "running", "completed", "failed"]
SocialStageStatus = Literal["not_started", "running", "completed", "skipped", "failed"]


class CharacterTurnRunner(Protocol):
    async def run(self, payload: object) -> CharacterTurnGraphResult: ...


class SocialTurnGraphState(TypedDict, total=False):
    """Privacy-safe coordination state for one externally-delimited social step."""

    trace_id: str
    graph_run_id: str
    graph_name: Literal["social_turn"]
    orchestration_version: str
    status: SocialGraphStatus
    participation_status: SocialStageStatus
    character_turn_status: SocialStageStatus
    continuation_status: SocialStageStatus
    current_deployment_id: str
    pending_deployment_ids: tuple[str, ...]
    completed_deployment_ids: tuple[str, ...]
    continuation_depth: int
    continuation_budget_remaining: int
    invite_candidate_deployment_id: str
    continuation_candidate_ids: tuple[str, ...]
    done: bool
    stop_reason: str


@dataclass(slots=True)
class SocialTurnGraphContext:
    """Run-scoped raw request and transient Character result."""

    request: DiscordSocialTurnStepRequest
    character_runner: CharacterTurnGraphRunner
    trace_sink: RuntimeTraceSink | None = None
    orchestration_version: str = "langgraph-phase-4"
    cursor: DiscordSocialTurnCursor | None = None
    current_turn: DiscordSocialPendingTurn | None = None
    character_result: CharacterTurnGraphResult | None = None
    next_turn: DiscordSocialPendingTurn | None = None


@dataclass(frozen=True, slots=True)
class SocialTurnGraphResult:
    state: SocialTurnGraphState
    view: DiscordSocialTurnStepView


def _emit(
    state: SocialTurnGraphState,
    context: SocialTurnGraphContext,
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
            graph_name="social_turn",
            node_name=node_name,
            node_kind=node_kind,
            status=status,
            changed_keys=changed_keys,
            metadata=metadata,
            error=error[:300],
        )
    )


def _unique_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def _initialize_cursor(request: DiscordSocialTurnStepRequest) -> DiscordSocialTurnCursor:
    initial = _unique_ids(request.initial_deployment_ids)
    available = set(_unique_ids(request.available_deployment_ids))
    pending = [
        DiscordSocialPendingTurn(deployment_id=item, origin="selected", depth=0)
        for item in initial
        if item in available
    ]
    return DiscordSocialTurnCursor(
        pending_turns=pending,
        completed_deployment_ids=[],
        continuation_budget_remaining=request.continuation_budget,
        max_depth=request.max_depth,
        step_index=0,
    )


def _admit_participant(
    state: SocialTurnGraphState,
    runtime: Runtime[SocialTurnGraphContext],
) -> SocialTurnGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="social_participation",
        node_kind="decision",
        status="started",
    )
    cursor = context.request.cursor.model_copy(deep=True) if context.request.cursor else None
    cursor = cursor or _initialize_cursor(context.request)
    context.cursor = cursor
    if not cursor.pending_turns:
        raise ValueError("Social Turn cursor has no pending participant.")
    current = cursor.pending_turns[0]
    context.current_turn = current
    payload = context.request.payload
    available = set(_unique_ids(context.request.available_deployment_ids))
    if current.deployment_id not in available:
        raise ValueError("The next Social Turn participant is no longer available.")
    if payload.deployment_id != current.deployment_id:
        raise ValueError("The supplied Character payload does not match the Social Turn cursor.")
    if payload.connection_id == "":
        raise ValueError("Social Turn payload requires a connector connection.")
    if current.deployment_id in cursor.completed_deployment_ids:
        raise ValueError("A completed Character cannot re-enter the same Social Turn.")
    update: SocialTurnGraphState = {
        "status": "running",
        "participation_status": "completed",
        "current_deployment_id": current.deployment_id,
        "pending_deployment_ids": tuple(item.deployment_id for item in cursor.pending_turns),
        "completed_deployment_ids": tuple(cursor.completed_deployment_ids),
        "continuation_depth": current.depth,
        "continuation_budget_remaining": cursor.continuation_budget_remaining,
    }
    _emit(
        state,
        context,
        node_name="social_participation",
        node_kind="decision",
        status="completed",
        changed_keys=tuple(update.keys()),
        metadata=(("origin", current.origin), ("depth", str(current.depth))),
    )
    return update


async def _run_character_turn(
    state: SocialTurnGraphState,
    runtime: Runtime[SocialTurnGraphContext],
) -> SocialTurnGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="social_character_turn",
        node_kind="agentic",
        status="started",
    )
    try:
        result = await context.character_runner.run(context.request.payload)
    except Exception as exc:
        _emit(
            state,
            context,
            node_name="social_character_turn",
            node_kind="agentic",
            status="failed",
            changed_keys=("character_turn_status", "status"),
            error=str(exc),
        )
        raise
    context.character_result = result
    _emit(
        state,
        context,
        node_name="social_character_turn",
        node_kind="agentic",
        status="completed",
        changed_keys=("character_turn_status", "invite_candidate_deployment_id"),
        metadata=(
            ("action", result.reply.action),
            ("character_outcome", result.state.get("outcome", "")),
        ),
    )
    return {
        "character_turn_status": "completed",
        "invite_candidate_deployment_id": result.invite_candidate_deployment_id,
    }


def _candidate_turn(
    deployment_id: str,
    *,
    origin: SocialTurnOrigin,
    depth: int,
    source_deployment_id: str,
) -> DiscordSocialPendingTurn:
    return DiscordSocialPendingTurn(
        deployment_id=deployment_id,
        origin=origin,
        depth=depth,
        source_deployment_id=source_deployment_id,
    )


def _expand_and_advance(
    state: SocialTurnGraphState,
    runtime: Runtime[SocialTurnGraphContext],
) -> SocialTurnGraphState:
    context = runtime.context
    _emit(
        state,
        context,
        node_name="social_continuation_authority",
        node_kind="authority",
        status="started",
    )
    cursor = context.cursor
    current = context.current_turn
    result = context.character_result
    if cursor is None or current is None or result is None:
        raise RuntimeError("Social Turn graph lost its continuation context.")

    rest = list(cursor.pending_turns[1:])
    completed = list(dict.fromkeys([*cursor.completed_deployment_ids, current.deployment_id]))
    known = set(completed)
    known.update(item.deployment_id for item in rest)
    available = set(_unique_ids(context.request.available_deployment_ids))
    next_depth = current.depth + 1
    inserted: list[DiscordSocialPendingTurn] = []
    continuation_ids: list[str] = []

    proposals: list[tuple[str, SocialTurnOrigin]] = []
    invite = result.invite_candidate_deployment_id
    if invite and not context.request.payload.author_is_bot:
        proposals.append((invite, "invite"))
    for candidate in result.mentioned_character_deployment_ids:
        if candidate != invite:
            proposals.append((candidate, "mention"))

    if next_depth <= cursor.max_depth:
        for candidate, origin in proposals:
            if cursor.continuation_budget_remaining <= 0:
                break
            if candidate not in available or candidate in known:
                continue
            inserted.append(
                _candidate_turn(
                    candidate,
                    origin=origin,
                    depth=next_depth,
                    source_deployment_id=current.deployment_id,
                )
            )
            continuation_ids.append(candidate)
            known.add(candidate)
            cursor.continuation_budget_remaining -= 1

    cursor.pending_turns = [*inserted, *rest]
    cursor.completed_deployment_ids = completed
    cursor.step_index += 1
    context.next_turn = cursor.pending_turns[0] if cursor.pending_turns else None
    done = context.next_turn is None
    stop_reason = "completed" if done else "await_delivery"
    update: SocialTurnGraphState = {
        "status": "completed",
        "continuation_status": "completed",
        "pending_deployment_ids": tuple(item.deployment_id for item in cursor.pending_turns),
        "completed_deployment_ids": tuple(completed),
        "continuation_budget_remaining": cursor.continuation_budget_remaining,
        "continuation_candidate_ids": tuple(continuation_ids),
        "done": done,
        "stop_reason": stop_reason,
    }
    _emit(
        state,
        context,
        node_name="social_continuation_authority",
        node_kind="authority",
        status="completed",
        changed_keys=tuple(update.keys()),
        metadata=(
            ("inserted", str(len(inserted))),
            ("done", str(done).lower()),
            ("next", context.next_turn.deployment_id if context.next_turn else ""),
        ),
    )
    return update


def build_social_turn_graph() -> Any:
    """Compile one delivery-delimited Phase 4 Social Turn step."""

    builder = StateGraph(
        state_schema=SocialTurnGraphState,
        context_schema=SocialTurnGraphContext,
    )
    builder.add_node("social_participation", _admit_participant)
    builder.add_node("social_character_turn", _run_character_turn)
    builder.add_node("social_continuation_authority", _expand_and_advance)
    builder.add_edge(START, "social_participation")
    builder.add_edge("social_participation", "social_character_turn")
    builder.add_edge("social_character_turn", "social_continuation_authority")
    builder.add_edge("social_continuation_authority", END)
    return builder.compile()


class SocialTurnGraphRunner:
    """Run one Character and return control to Discord for real delivery."""

    def __init__(
        self,
        character_runner: CharacterTurnGraphRunner,
        *,
        trace_sink: RuntimeTraceSink | None = None,
    ) -> None:
        self.character_runner = character_runner
        self.trace_sink = trace_sink
        self.graph = build_social_turn_graph()

    async def run(self, request: DiscordSocialTurnStepRequest) -> SocialTurnGraphResult:
        context = SocialTurnGraphContext(
            request=request,
            character_runner=self.character_runner,
            trace_sink=self.trace_sink,
        )
        state: SocialTurnGraphState = {
            "trace_id": str(uuid4()),
            "graph_run_id": str(uuid4()),
            "graph_name": "social_turn",
            "orchestration_version": context.orchestration_version,
            "status": "pending",
            "participation_status": "not_started",
            "character_turn_status": "not_started",
            "continuation_status": "not_started",
            "current_deployment_id": request.payload.deployment_id,
            "pending_deployment_ids": (),
            "completed_deployment_ids": (),
            "continuation_depth": 0,
            "continuation_budget_remaining": request.continuation_budget,
            "invite_candidate_deployment_id": "",
            "continuation_candidate_ids": (),
            "done": False,
            "stop_reason": "",
        }
        result = cast(
            SocialTurnGraphState,
            await self.graph.ainvoke(state, context=context),
        )
        character_result = context.character_result
        cursor = context.cursor
        if character_result is None or cursor is None:
            raise RuntimeError("Social Turn graph completed without a Character result.")
        view = DiscordSocialTurnStepView(
            reply=character_result.reply,
            cursor=cursor,
            current_deployment_id=request.payload.deployment_id,
            next_turn=context.next_turn,
            done=result.get("done", False),
            stop_reason=result.get("stop_reason", ""),
            invite_candidate_deployment_id=(
                character_result.invite_candidate_deployment_id
            ),
            mentioned_character_deployment_ids=list(
                character_result.mentioned_character_deployment_ids
            ),
        )
        return SocialTurnGraphResult(state=result, view=view)

    async def __call__(self, request: DiscordSocialTurnStepRequest) -> DiscordSocialTurnStepView:
        return (await self.run(request)).view


__all__ = [
    "SocialTurnGraphContext",
    "SocialTurnGraphResult",
    "SocialTurnGraphRunner",
    "SocialTurnGraphState",
    "build_social_turn_graph",
]
