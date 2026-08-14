"""Non-legacy Character context routing built from one Turn Intelligence gray-zone decision."""

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


@dataclass(frozen=True, slots=True)
class CharacterContextRoutingPlan:
    gate: KnowledgeRouteDecision
    fallback_gate: KnowledgeRouteDecision | None
    final_query: str
    retrieval_mode: ContextKnowledgeMode
    pending_tool_id: str
    knowledge_source: str
    pending_action_source: str
    requested_tasks: tuple[TurnIntelligenceTask, ...]
    current_assessment: KnowledgeRouteAssessment
    contextual_assessment: KnowledgeRouteAssessment | None
    unified_outcome: CharacterTurnIntelligenceOutcome
    contextual_no_hit_gate: KnowledgeRouteDecision | None = None


@dataclass(frozen=True, slots=True)
class _LegacyKnowledgeRoute:
    gate: KnowledgeRouteDecision
    fallback_gate: KnowledgeRouteDecision | None
    final_query: str
    retrieval_mode: ContextKnowledgeMode


class CharacterContextRoutingService:
    """Apply shadow/active Turn Intelligence without weakening legacy fallback authority."""

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

    def _legacy_knowledge_route(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        current_query: str,
        contextual_query: str,
    ) -> _LegacyKnowledgeRoute:
        gate = self.knowledge_gate.decide(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
            query=current_query,
        )
        fallback_gate: KnowledgeRouteDecision | None = None
        final_query = current_query
        retrieval_mode: ContextKnowledgeMode = "current"
        if not gate.should_retrieve and contextual_query:
            fallback_gate = self.knowledge_gate.decide(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                character_card_id=character_card_id,
                query=contextual_query,
            )
            if fallback_gate.should_retrieve:
                gate = fallback_gate
                final_query = contextual_query
                retrieval_mode = "contextual"
        return _LegacyKnowledgeRoute(
            gate=gate,
            fallback_gate=fallback_gate,
            final_query=final_query,
            retrieval_mode=retrieval_mode,
        )

    @staticmethod
    def _accepted_route(
        outcome: CharacterTurnIntelligenceOutcome,
        *,
        current: KnowledgeRouteAssessment,
        contextual: KnowledgeRouteAssessment | None,
        current_query: str,
        contextual_query: str,
    ) -> _LegacyKnowledgeRoute | None:
        route = outcome.knowledge_route
        if route is None:
            return None
        if route == "current":
            gate = KnowledgeRouteGate.decision_from_assessment(
                current,
                should_retrieve=True,
            )
            return _LegacyKnowledgeRoute(gate, None, current_query, "current")
        if route == "contextual" and contextual is not None and contextual_query:
            gate = KnowledgeRouteGate.decision_from_assessment(
                contextual,
                should_retrieve=True,
            )
            return _LegacyKnowledgeRoute(gate, gate, contextual_query, "contextual")
        if route == "off":
            gate = KnowledgeRouteGate.decision_from_assessment(
                current,
                should_retrieve=False,
            )
            return _LegacyKnowledgeRoute(gate, None, current_query, "current")
        return None

    @staticmethod
    def _contextual_no_hit_gate(
        contextual: KnowledgeRouteAssessment | None,
    ) -> KnowledgeRouteDecision | None:
        if contextual is None or contextual.route == "off":
            return None
        should_retrieve = (
            contextual.route == "on"
            or (contextual.route == "gray" and contextual.fallback_should_retrieve)
        )
        if not should_retrieve:
            return None
        return KnowledgeRouteGate.decision_from_assessment(
            contextual,
            should_retrieve=True,
        )

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
            raise ValueError("CharacterContextRoutingService requires shadow or active mode.")

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

        if mode == "shadow":
            actual = self._legacy_knowledge_route(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                character_card_id=character_card_id,
                current_query=current_query,
                contextual_query=contextual_query,
            )
            pending_tool_id = (
                self.tool_continuation.resolve_pending_action_evidence(pending_action)
                if pending_action is not None
                else ""
            )
            return CharacterContextRoutingPlan(
                gate=actual.gate,
                fallback_gate=actual.fallback_gate,
                final_query=actual.final_query,
                retrieval_mode=actual.retrieval_mode,
                pending_tool_id=pending_tool_id,
                knowledge_source="legacy_shadow",
                pending_action_source=(
                    "legacy_shadow" if pending_action is not None else "not_requested"
                ),
                requested_tasks=outcome.requested_tasks,
                current_assessment=current,
                contextual_assessment=contextual,
                unified_outcome=outcome,
            )

        actual = self._accepted_route(
            outcome,
            current=current,
            contextual=contextual,
            current_query=current_query,
            contextual_query=contextual_query,
        )
        knowledge_source = outcome.knowledge_source
        if actual is None or outcome.knowledge_fallback_required:
            actual = self._legacy_knowledge_route(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                character_card_id=character_card_id,
                current_query=current_query,
                contextual_query=contextual_query,
            )
            knowledge_source = "legacy_fallback"

        pending_tool_id = ""
        pending_source = outcome.pending_action_source
        if pending_action is not None:
            if outcome.pending_action_fallback_required:
                pending_tool_id = self.tool_continuation.resolve_pending_action_evidence(
                    pending_action
                )
                pending_source = "legacy_fallback"
            elif outcome.pending_action_continue:
                pending_tool_id = pending_action.tool_id

        no_hit_gate = (
            self._contextual_no_hit_gate(contextual)
            if actual.retrieval_mode == "current"
            else None
        )
        return CharacterContextRoutingPlan(
            gate=actual.gate,
            fallback_gate=actual.fallback_gate,
            final_query=actual.final_query,
            retrieval_mode=actual.retrieval_mode,
            pending_tool_id=pending_tool_id,
            knowledge_source=knowledge_source,
            pending_action_source=pending_source,
            requested_tasks=outcome.requested_tasks,
            current_assessment=current,
            contextual_assessment=contextual,
            unified_outcome=outcome,
            contextual_no_hit_gate=no_hit_gate,
        )


__all__ = [
    "CharacterContextRoutingPlan",
    "CharacterContextRoutingService",
    "ContextKnowledgeMode",
]
