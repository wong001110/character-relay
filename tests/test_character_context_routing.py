from __future__ import annotations

from echo_masque.character_context_routing import CharacterContextRoutingService
from echo_masque.character_turn_intelligence import CharacterTurnIntelligenceOutcome
from echo_masque.knowledge_route_gate import (
    KnowledgeRouteAssessment,
    KnowledgeRouteDecision,
    KnowledgeRouteGate,
)
from echo_masque.tool_continuation import PendingActionContinuationEvidence


def assessment(route: str, *, fallback: bool = False, contextual: bool = False):  # type: ignore[no-untyped-def]
    return KnowledgeRouteAssessment(
        status="matched" if fallback else "not_relevant",
        route=route,  # type: ignore[arg-type]
        fallback_should_retrieve=fallback,
        eligible_base_count=1,
        best_sparse_score=0.01,
        best_dense_score=0.50,
        route_labels=("Docs",),
        current_message="question",
        normalized_query="question",
        is_contextual=contextual,
    )


def pending() -> PendingActionContinuationEvidence:
    return PendingActionContinuationEvidence(
        tool_id="image.generate",
        current_message="maybe again",
        active_topic_label="image generation",
        active_topic_summary="one pending image",
        pending_intent_summary="generate image",
        pending_source_message_id="message-1",
        continuation_strength=0.35,
    )


class FakeGate:
    def __init__(
        self,
        current: KnowledgeRouteAssessment,
        contextual: KnowledgeRouteAssessment | None,
    ) -> None:
        self.current = current
        self.contextual = contextual
        self.assess_calls: list[str] = []
        self.decide_calls: list[str] = []

    def assess(self, *, query: str, **_kwargs: object) -> KnowledgeRouteAssessment:
        self.assess_calls.append(query)
        if "context" in query and self.contextual is not None:
            return self.contextual
        return self.current

    def decide(self, *, query: str, **_kwargs: object) -> KnowledgeRouteDecision:
        self.decide_calls.append(query)
        value = (
            self.contextual
            if "context" in query and self.contextual is not None
            else self.current
        )
        return KnowledgeRouteGate.decision_from_assessment(
            value,
            should_retrieve=value.fallback_should_retrieve,
        )


class FakeToolContinuation:
    def __init__(self, legacy_result: str = "image.generate") -> None:
        self.legacy_result = legacy_result
        self.calls = 0

    def resolve_pending_action_evidence(
        self,
        _evidence: PendingActionContinuationEvidence,
    ) -> str:
        self.calls += 1
        return self.legacy_result


class FakeCoordinator:
    def __init__(self, outcome: CharacterTurnIntelligenceOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    def decide(self, **_kwargs: object) -> CharacterTurnIntelligenceOutcome:
        self.calls += 1
        return self.outcome


def outcome(
    *,
    route: str | None,
    knowledge_source: str,
    pending_continue: bool | None,
    pending_source: str,
):
    return CharacterTurnIntelligenceOutcome(
        knowledge_route=route,  # type: ignore[arg-type]
        knowledge_source=knowledge_source,  # type: ignore[arg-type]
        pending_action_continue=pending_continue,
        pending_action_tool_id="image.generate" if pending_continue else "",
        pending_action_source=pending_source,  # type: ignore[arg-type]
        requested_tasks=("knowledge", "pending_action"),
    )


def service(
    gate: FakeGate,
    tool: FakeToolContinuation,
    coordinator: FakeCoordinator,
) -> CharacterContextRoutingService:
    return CharacterContextRoutingService(
        gate,  # type: ignore[arg-type]
        tool,  # type: ignore[arg-type]
        coordinator,  # type: ignore[arg-type]
    )


COMMON = dict(
    owner_id="owner-1",
    connection_id="connection-1",
    guild_id="guild-1",
    channel_id="channel-1",
    thread_id="",
    character_card_id="card-ann",
    current_query="current question",
    contextual_query="context question",
)


def test_active_applies_both_accepted_fields_without_legacy_judges() -> None:
    gate = FakeGate(assessment("gray"), assessment("gray", fallback=True, contextual=True))
    tool = FakeToolContinuation()
    coordinator = FakeCoordinator(
        outcome(
            route="contextual",
            knowledge_source="turn_intelligence",
            pending_continue=True,
            pending_source="turn_intelligence",
        )
    )

    result = service(gate, tool, coordinator).resolve(
        mode="active",
        pending_action=pending(),
        **COMMON,
    )

    assert coordinator.calls == 1
    assert gate.decide_calls == []
    assert tool.calls == 0
    assert result.retrieval_mode == "contextual"
    assert result.final_query == "context question"
    assert result.gate.should_retrieve is True
    assert result.pending_tool_id == "image.generate"
    assert result.knowledge_source == "turn_intelligence"
    assert result.pending_action_source == "turn_intelligence"


def test_active_falls_back_only_the_rejected_knowledge_field() -> None:
    gate = FakeGate(assessment("gray", fallback=False), assessment("off", contextual=True))
    tool = FakeToolContinuation()
    coordinator = FakeCoordinator(
        outcome(
            route=None,
            knowledge_source="legacy_fallback_required",
            pending_continue=False,
            pending_source="turn_intelligence",
        )
    )

    result = service(gate, tool, coordinator).resolve(
        mode="active",
        pending_action=pending(),
        **COMMON,
    )

    assert coordinator.calls == 1
    assert gate.decide_calls == ["current question", "context question"]
    assert tool.calls == 0
    assert result.pending_tool_id == ""
    assert result.pending_action_source == "turn_intelligence"
    assert result.knowledge_source == "legacy_fallback"


def test_shadow_runs_unified_comparison_but_preserves_both_legacy_paths() -> None:
    gate = FakeGate(
        assessment("gray", fallback=False),
        assessment("gray", fallback=True, contextual=True),
    )
    tool = FakeToolContinuation("image.generate")
    coordinator = FakeCoordinator(
        outcome(
            route="off",
            knowledge_source="turn_intelligence",
            pending_continue=False,
            pending_source="turn_intelligence",
        )
    )

    result = service(gate, tool, coordinator).resolve(
        mode="shadow",
        pending_action=pending(),
        **COMMON,
    )

    assert coordinator.calls == 1
    assert gate.decide_calls == ["current question", "context question"]
    assert tool.calls == 1
    assert result.knowledge_source == "legacy_shadow"
    assert result.pending_action_source == "legacy_shadow"
    assert result.pending_tool_id == "image.generate"


def test_active_current_route_reuses_contextual_gray_fallback_without_second_utility() -> None:
    gate = FakeGate(assessment("gray"), assessment("gray", fallback=True, contextual=True))
    tool = FakeToolContinuation()
    coordinator = FakeCoordinator(
        outcome(
            route="current",
            knowledge_source="turn_intelligence",
            pending_continue=None,
            pending_source="not_requested",
        )
    )

    result = service(gate, tool, coordinator).resolve(
        mode="active",
        pending_action=None,
        **COMMON,
    )

    assert result.retrieval_mode == "current"
    assert result.contextual_no_hit_gate is not None
    assert result.contextual_no_hit_gate.should_retrieve is True
    assert gate.decide_calls == []
