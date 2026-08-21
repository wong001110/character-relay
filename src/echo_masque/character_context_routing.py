"""Character context routing from deterministic evidence plus bounded Turn Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from echo_masque.character_turn_intelligence import (
    CharacterTurnIntelligenceCoordinator,
    CharacterTurnIntelligenceOutcome,
)
from echo_masque.config import CharacterTurnIntelligenceMode
from echo_masque.knowledge_route_gate import (
    KnowledgeRouteAssessment,
    KnowledgeRouteDecision,
    KnowledgeRouteGate,
)
from echo_masque.tool_continuation import (
    PendingActionContinuationEvidence,
    ToolContinuationService,
)
from echo_masque.turn_intelligence import TurnIntelligenceTask

ContextKnowledgeMode = Literal["current", "contextual"]
CharacterContextDecisionSource = Literal[
    "deterministic",
    "turn_intelligence",
    "deterministic_fallback",
    "not_requested",
]


@dataclass(frozen=True, slots=True)
class CharacterContextRoutingPlan:
    gate: KnowledgeRouteDecision
    fallback_gate: KnowledgeRouteDecision | None
    final_query: str
    retrieval_mode: ContextKnowledgeMode
    pending_tool_id: str
    knowledge_source: CharacterContextDecisionSource
    pending_action_source: CharacterContextDecisionSource
    requested_tasks: tuple[TurnIntelligenceTask, ...]
    current_assessment: KnowledgeRouteAssessment
    contextual_assessment: KnowledgeRouteAssessment | None
    unified_outcome: CharacterTurnIntelligenceOutcome
    contextual_no_hit_gate: KnowledgeRouteDecision | None = None


class CharacterContextRoutingService:
    """Apply one authority path; configured shadow mode no longer runs a second runtime."""

    def __init__(
        self,
        knowledge_gate: KnowledgeRouteGate,
        tool_continuation: ToolContinuationService,
        coordinator: CharacterTurnIntelligenceCoordinator,
    ) -> None:
        self.knowledge_gate = knowledge_gate
        self.tool_continuation = tool_continuation
        self.coordinator = coordinator

    def _assessment(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        query: str,
    ) -> KnowledgeRouteAssessment:
        return self.knowledge_gate.assess(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
            query=query,
        )

    @staticmethod
    def _decision(
        assessment: KnowledgeRouteAssessment,
        *,
        should_retrieve: bool,
    ) -> KnowledgeRouteDecision:
        return KnowledgeRouteGate.decision_from_assessment(
            assessment,
            should_retrieve=should_retrieve,
        )

    @staticmethod
    def _contextual_no_hit_gate(
        contextual: KnowledgeRouteAssessment | None,
    ) -> KnowledgeRouteDecision | None:
        if contextual is None or contextual.route == "off":
            return None
        should_retrieve = contextual.route == "on" or (
            contextual.route == "gray" and contextual.fallback_should_retrieve
        )
        if not should_retrieve:
            return None
        return KnowledgeRouteGate.decision_from_assessment(
            contextual,
            should_retrieve=True,
        )

    @classmethod
    def _route_from_outcome(
        cls,
        outcome: CharacterTurnIntelligenceOutcome,
        *,
        current: KnowledgeRouteAssessment,
        contextual: KnowledgeRouteAssessment | None,
        current_query: str,
        contextual_query: str,
    ) -> tuple[KnowledgeRouteDecision, KnowledgeRouteDecision | None, str, ContextKnowledgeMode]:
        route = outcome.knowledge_route
        if route == "current":
            return cls._decision(current, should_retrieve=True), None, current_query, "current"
        if route == "contextual" and contextual is not None and contextual_query:
            gate = cls._decision(contextual, should_retrieve=True)
            return gate, gate, contextual_query, "contextual"
        if route == "off":
            return cls._decision(current, should_retrieve=False), None, current_query, "current"
        should_current = current.route == "on" or (
            current.route == "gray" and current.fallback_should_retrieve
        )
        if should_current:
            return cls._decision(current, should_retrieve=True), None, current_query, "current"
        should_contextual = contextual is not None and (
            contextual.route == "on"
            or (contextual.route == "gray" and contextual.fallback_should_retrieve)
        )
        if should_contextual and contextual is not None and contextual_query:
            gate = cls._decision(contextual, should_retrieve=True)
            return gate, gate, contextual_query, "contextual"
        return cls._decision(current, should_retrieve=False), None, current_query, "current"

    def resolve(
        self,
        *,
        mode: CharacterTurnIntelligenceMode,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        current_query: str,
        contextual_query: str,
        pending_action: PendingActionContinuationEvidence | None,
    ) -> CharacterContextRoutingPlan:
        if mode == "off":
            raise ValueError("CharacterContextRoutingService requires an enabled mode.")

        current = self._assessment(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
            query=current_query,
        )
        contextual = (
            self._assessment(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                character_card_id=character_card_id,
                query=contextual_query,
            )
            if contextual_query
            else None
        )
        outcome = self.coordinator.decide(
            current_burst=current_query,
            current_knowledge=current,
            contextual_knowledge=contextual,
            pending_action=pending_action,
        )
        gate, fallback_gate, final_query, retrieval_mode = self._route_from_outcome(
            outcome,
            current=current,
            contextual=contextual,
            current_query=current_query,
            contextual_query=contextual_query,
        )
        pending_tool_id = (
            pending_action.tool_id
            if pending_action is not None and outcome.pending_action_continue
            else ""
        )
        no_hit_gate = (
            self._contextual_no_hit_gate(contextual)
            if retrieval_mode == "current"
            else None
        )
        return CharacterContextRoutingPlan(
            gate=gate,
            fallback_gate=fallback_gate,
            final_query=final_query,
            retrieval_mode=retrieval_mode,
            pending_tool_id=pending_tool_id,
            knowledge_source=outcome.knowledge_source,
            pending_action_source=outcome.pending_action_source,
            requested_tasks=outcome.requested_tasks,
            current_assessment=current,
            contextual_assessment=contextual,
            unified_outcome=outcome,
            contextual_no_hit_gate=no_hit_gate,
        )


__all__ = [
    "CharacterContextDecisionSource",
    "CharacterContextRoutingPlan",
    "CharacterContextRoutingService",
    "ContextKnowledgeMode",
]
