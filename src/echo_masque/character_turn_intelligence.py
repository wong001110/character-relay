"""One Character-turn coordinator for Knowledge and PendingAction gray zones.

The coordinator consumes evidence already produced by deterministic/sparse/semantic runtime
components. It never grants Tool authority and never changes an unambiguous Knowledge route.
When both supported tasks are ambiguous, exactly one Turn Intelligence invocation is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from echo_masque.knowledge_route_gate import KnowledgeRouteAssessment
from echo_masque.tool_continuation import PendingActionContinuationEvidence
from echo_masque.turn_intelligence import (
    TurnIntelligenceResult,
    TurnIntelligenceService,
    TurnIntelligenceTask,
)

CharacterKnowledgeRoute = Literal["off", "current", "contextual"]
CharacterTurnDecisionSource = Literal[
    "deterministic",
    "turn_intelligence",
    "deterministic_fallback",
    "not_requested",
]


@dataclass(frozen=True, slots=True)
class CharacterTurnIntelligenceOutcome:
    knowledge_route: CharacterKnowledgeRoute | None
    knowledge_source: CharacterTurnDecisionSource
    pending_action_continue: bool | None
    pending_action_tool_id: str
    pending_action_source: CharacterTurnDecisionSource
    requested_tasks: tuple[TurnIntelligenceTask, ...]
    result: TurnIntelligenceResult | None = None


@dataclass(frozen=True, slots=True)
class _KnowledgePlan:
    route: CharacterKnowledgeRoute | None
    request_utility: bool
    allowed_utility_routes: frozenset[CharacterKnowledgeRoute]


def _knowledge_plan(
    current: KnowledgeRouteAssessment,
    contextual: KnowledgeRouteAssessment | None,
) -> _KnowledgePlan:
    if current.route == "on":
        return _KnowledgePlan("current", False, frozenset())
    if current.route == "off":
        if contextual is None or contextual.route == "off":
            return _KnowledgePlan("off", False, frozenset())
        if contextual.route == "on":
            return _KnowledgePlan("contextual", False, frozenset())
        return _KnowledgePlan(None, True, frozenset(("off", "contextual")))
    if contextual is not None and contextual.route == "on":
        return _KnowledgePlan("contextual", False, frozenset())
    if contextual is None or contextual.route == "off":
        return _KnowledgePlan(None, True, frozenset(("off", "current")))
    return _KnowledgePlan(None, True, frozenset(("off", "current", "contextual")))


def _fallback_knowledge_route(
    current: KnowledgeRouteAssessment,
    contextual: KnowledgeRouteAssessment | None,
) -> CharacterKnowledgeRoute:
    if current.route == "on" or (
        current.route == "gray" and current.fallback_should_retrieve
    ):
        return "current"
    if contextual is not None and (
        contextual.route == "on"
        or (contextual.route == "gray" and contextual.fallback_should_retrieve)
    ):
        return "contextual"
    return "off"


def _knowledge_evidence_text(
    current: KnowledgeRouteAssessment,
    contextual: KnowledgeRouteAssessment | None,
) -> str:
    def line(label: str, value: KnowledgeRouteAssessment) -> str:
        fallback = "on" if value.fallback_should_retrieve else "off"
        return (
            f"{label}: route={value.route}; fallback={fallback}; "
            f"dense={value.best_dense_score:.6f}; sparse={value.best_sparse_score:.6f}; "
            f"eligible_bases={value.eligible_base_count}; contextual={value.is_contextual}"
        )

    values = [line("current", current)]
    if contextual is not None:
        values.append(line("contextual", contextual))
    return "\n".join(values)


def _pending_action_evidence_text(evidence: PendingActionContinuationEvidence) -> str:
    return "\n".join(
        (
            f"action_id={evidence.action_id}",
            f"tool_id={evidence.tool_id}",
            f"conversation_thread_id={evidence.conversation_thread_id}",
            f"continuation_strength={evidence.continuation_strength:.6f}",
            f"pending_intent={evidence.pending_intent_summary}",
            f"pending_source_message_id={evidence.pending_source_message_id}",
        )
    )


class CharacterTurnIntelligenceCoordinator:
    """Resolve Knowledge + one authorized PendingAction gray-zone with one Utility invocation."""

    def __init__(self, service: TurnIntelligenceService) -> None:
        self.service = service

    def decide(
        self,
        *,
        current_burst: str,
        current_knowledge: KnowledgeRouteAssessment,
        contextual_knowledge: KnowledgeRouteAssessment | None,
        pending_action: PendingActionContinuationEvidence | None,
    ) -> CharacterTurnIntelligenceOutcome:
        knowledge_plan = _knowledge_plan(current_knowledge, contextual_knowledge)
        requested: list[TurnIntelligenceTask] = []
        if knowledge_plan.request_utility:
            requested.append("knowledge")
        if pending_action is not None:
            requested.append("pending_action")

        if not requested:
            return CharacterTurnIntelligenceOutcome(
                knowledge_route=knowledge_plan.route,
                knowledge_source="deterministic",
                pending_action_continue=None,
                pending_action_tool_id="",
                pending_action_source="not_requested",
                requested_tasks=(),
            )

        result = self.service.decide(
            requested_tasks=tuple(requested),
            current_burst=current_burst,
            knowledge_evidence=(
                _knowledge_evidence_text(current_knowledge, contextual_knowledge)
                if knowledge_plan.request_utility
                else ""
            ),
            pending_tool_id=pending_action.tool_id if pending_action is not None else "",
            pending_action_evidence=(
                _pending_action_evidence_text(pending_action)
                if pending_action is not None
                else ""
            ),
        )

        knowledge_route = knowledge_plan.route
        knowledge_source: CharacterTurnDecisionSource = "deterministic"
        if knowledge_plan.request_utility:
            knowledge_route = _fallback_knowledge_route(
                current_knowledge,
                contextual_knowledge,
            )
            knowledge_source = "deterministic_fallback"
            if result.knowledge is not None:
                route = result.knowledge.route
                if route in knowledge_plan.allowed_utility_routes:
                    knowledge_route = route
                    knowledge_source = "turn_intelligence"

        pending_continue: bool | None = None
        pending_tool_id = ""
        pending_source: CharacterTurnDecisionSource = "not_requested"
        if pending_action is not None:
            pending_continue = False
            pending_source = "deterministic_fallback"
            if result.pending_action is not None:
                pending_continue = result.pending_action.continue_action
                pending_tool_id = (
                    pending_action.tool_id if result.pending_action.continue_action else ""
                )
                pending_source = "turn_intelligence"

        return CharacterTurnIntelligenceOutcome(
            knowledge_route=knowledge_route,
            knowledge_source=knowledge_source,
            pending_action_continue=pending_continue,
            pending_action_tool_id=pending_tool_id,
            pending_action_source=pending_source,
            requested_tasks=tuple(requested),
            result=result,
        )


__all__ = [
    "CharacterKnowledgeRoute",
    "CharacterTurnDecisionSource",
    "CharacterTurnIntelligenceCoordinator",
    "CharacterTurnIntelligenceOutcome",
]
