"""One Character-turn coordinator for Knowledge and pending Tool gray zones.

The coordinator consumes evidence that was already produced by deterministic/sparse/E5 runtime
components. It never grants Tool authority and it never changes an unambiguous Knowledge route.
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
    "legacy_fallback_required",
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

    @property
    def knowledge_fallback_required(self) -> bool:
        return self.knowledge_source == "legacy_fallback_required"

    @property
    def pending_action_fallback_required(self) -> bool:
        return self.pending_action_source == "legacy_fallback_required"


@dataclass(frozen=True, slots=True)
class _KnowledgePlan:
    route: CharacterKnowledgeRoute | None
    request_utility: bool
    allowed_utility_routes: frozenset[CharacterKnowledgeRoute]


def _knowledge_plan(
    current: KnowledgeRouteAssessment,
    contextual: KnowledgeRouteAssessment | None,
) -> _KnowledgePlan:
    """Resolve all non-gray Knowledge combinations before any Utility call."""

    if current.route == "on":
        return _KnowledgePlan("current", False, frozenset())

    if current.route == "off":
        if contextual is None or contextual.route == "off":
            return _KnowledgePlan("off", False, frozenset())
        if contextual.route == "on":
            return _KnowledgePlan("contextual", False, frozenset())
        return _KnowledgePlan(None, True, frozenset(("off", "contextual")))

    # Current is gray. A deterministic contextual ON is already sufficient to retrieve a bounded
    # contextual query and avoids spending Utility merely to prefer a shorter query.
    if contextual is not None and contextual.route == "on":
        return _KnowledgePlan("contextual", False, frozenset())
    if contextual is None or contextual.route == "off":
        return _KnowledgePlan(None, True, frozenset(("off", "current")))
    return _KnowledgePlan(None, True, frozenset(("off", "current", "contextual")))


def _knowledge_evidence_text(
    current: KnowledgeRouteAssessment,
    contextual: KnowledgeRouteAssessment | None,
) -> str:
    def line(label: str, value: KnowledgeRouteAssessment) -> str:
        return (
            f"{label}: route={value.route}; fallback={'on' if value.fallback_should_retrieve else 'off'}; "
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
            f"tool_id={evidence.tool_id}",
            f"continuation_strength={evidence.continuation_strength:.6f}",
            f"pending_intent={evidence.pending_intent_summary}",
            f"pending_source_message_id={evidence.pending_source_message_id}",
        )
    )


class CharacterTurnIntelligenceCoordinator:
    """Resolve Knowledge + one authorized pending Tool gray-zone with one Utility invocation."""

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

        active_topic = pending_action.active_topic_label if pending_action is not None else ""
        topic_evidence = (
            pending_action.active_topic_summary if pending_action is not None else ""
        )
        result = self.service.decide(
            requested_tasks=tuple(requested),
            current_burst=current_burst,
            active_topic=active_topic,
            topic_evidence=topic_evidence,
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
        knowledge_source: CharacterTurnDecisionSource = (
            "deterministic" if not knowledge_plan.request_utility else "legacy_fallback_required"
        )
        if knowledge_plan.request_utility and result.knowledge is not None:
            route = result.knowledge.route
            if route in knowledge_plan.allowed_utility_routes:
                knowledge_route = route
                knowledge_source = "turn_intelligence"

        pending_continue: bool | None = None
        pending_tool_id = ""
        pending_source: CharacterTurnDecisionSource = "not_requested"
        if pending_action is not None:
            pending_source = "legacy_fallback_required"
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
