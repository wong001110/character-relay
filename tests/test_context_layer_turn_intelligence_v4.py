from __future__ import annotations

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.character_context_routing import CharacterContextRoutingPlan
from echo_masque.character_turn_intelligence import CharacterTurnIntelligenceOutcome
from echo_masque.config import Settings
from echo_masque.context_layer import ContextOrchestrator
from echo_masque.knowledge_route_gate import (
    KnowledgeRouteAssessment,
    KnowledgeRouteDecision,
)


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.retrieve_queries: list[str] = []
        self.database = object()

    def retrieve(self, *, query: str, **_kwargs: object) -> list[object]:
        self.retrieve_queries.append(query)
        return []


class FakeKnowledgeGate:
    def __init__(self, decision: KnowledgeRouteDecision) -> None:
        self.decision_value = decision
        self.decide_calls = 0
        self.assess_calls = 0

    def decide(self, **_kwargs: object) -> KnowledgeRouteDecision:
        self.decide_calls += 1
        return self.decision_value

    def assess(self, **_kwargs: object) -> KnowledgeRouteAssessment:
        self.assess_calls += 1
        raise AssertionError("ContextOrchestrator should not call assess() directly in this test")


class ExplodingRoutingService:
    def resolve(self, **_kwargs: object) -> CharacterContextRoutingPlan:
        raise AssertionError("Turn Intelligence routing must stay disabled in off mode")


class FakeRoutingService:
    def __init__(self, plan: CharacterContextRoutingPlan) -> None:
        self.plan = plan
        self.calls = 0

    def resolve(self, **_kwargs: object) -> CharacterContextRoutingPlan:
        self.calls += 1
        return self.plan


def payload(text: str = "current question") -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="message-2",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Alice",
        text=text,
    )


def assessment(route: str, *, contextual: bool = False) -> KnowledgeRouteAssessment:
    return KnowledgeRouteAssessment(
        status="matched" if route == "on" else "not_relevant",
        route=route,  # type: ignore[arg-type]
        fallback_should_retrieve=route == "on",
        eligible_base_count=1,
        best_sparse_score=0.01,
        best_dense_score=0.5,
        route_labels=("Docs",),
        current_message="question",
        normalized_query="question",
        is_contextual=contextual,
    )


def outcome(
    *,
    route: str | None,
    knowledge_source: str,
    pending_source: str = "not_requested",
) -> CharacterTurnIntelligenceOutcome:
    return CharacterTurnIntelligenceOutcome(
        knowledge_route=route,  # type: ignore[arg-type]
        knowledge_source=knowledge_source,  # type: ignore[arg-type]
        pending_action_continue=None,
        pending_action_tool_id="",
        pending_action_source=pending_source,  # type: ignore[arg-type]
        requested_tasks=("knowledge",),
    )


def test_off_mode_keeps_legacy_gate_and_never_enters_unified_routing() -> None:
    repository = FakeKnowledgeRepository()
    gate = FakeKnowledgeGate(
        KnowledgeRouteDecision("no_eligible_bases", False, 0)
    )
    orchestrator = ContextOrchestrator(
        repository,  # type: ignore[arg-type]
        settings=Settings(
            environment="test",
            turn_intelligence_character_context_mode="off",
        ),
        knowledge_route_gate=gate,  # type: ignore[arg-type]
    )
    orchestrator._character_context_routing_live = ExplodingRoutingService()  # type: ignore[assignment]

    result = orchestrator.build(
        owner_id="owner-1",
        payload=payload(),
        character_card_id="card-ann",
    )

    assert gate.decide_calls == 1
    assert gate.assess_calls == 0
    assert repository.retrieve_queries == []
    assert result.trace.rag_reason == "no_eligible_bases"
    assert result.trace.turn_intelligence_mode == "off"
    assert result.trace.turn_intelligence_requested_tasks == []


def test_shadow_mode_consumes_routing_plan_and_records_comparison_trace() -> None:
    repository = FakeKnowledgeRepository()
    gate = FakeKnowledgeGate(KnowledgeRouteDecision("not_relevant", False, 1))
    current = assessment("gray")
    plan = CharacterContextRoutingPlan(
        gate=KnowledgeRouteDecision("not_relevant", False, 1),
        fallback_gate=None,
        final_query="current question",
        retrieval_mode="current",
        pending_tool_id="",
        knowledge_source="legacy_shadow",
        pending_action_source="not_requested",
        requested_tasks=("knowledge",),
        current_assessment=current,
        contextual_assessment=None,
        unified_outcome=outcome(
            route="off",
            knowledge_source="turn_intelligence",
        ),
    )
    routing = FakeRoutingService(plan)
    orchestrator = ContextOrchestrator(
        repository,  # type: ignore[arg-type]
        settings=Settings(
            environment="test",
            turn_intelligence_character_context_mode="shadow",
        ),
        knowledge_route_gate=gate,  # type: ignore[arg-type]
    )
    orchestrator._character_context_routing_live = routing  # type: ignore[assignment]

    result = orchestrator.build(
        owner_id="owner-1",
        payload=payload(),
        character_card_id="card-ann",
    )

    assert routing.calls == 1
    assert gate.decide_calls == 0
    assert repository.retrieve_queries == []
    assert result.trace.turn_intelligence_mode == "shadow"
    assert result.trace.turn_intelligence_requested_tasks == ["knowledge"]
    assert result.trace.turn_intelligence_knowledge_source == "legacy_shadow"
    assert result.trace.turn_intelligence_knowledge_route == "off"


def test_active_current_no_hits_reuses_precomputed_contextual_gate() -> None:
    repository = FakeKnowledgeRepository()
    gate = FakeKnowledgeGate(KnowledgeRouteDecision("not_relevant", False, 1))
    current = assessment("gray")
    contextual = assessment("gray", contextual=True)
    current_gate = KnowledgeRouteDecision(
        "matched",
        True,
        1,
        best_dense_score=0.5,
    )
    contextual_gate = KnowledgeRouteDecision(
        "matched",
        True,
        1,
        best_dense_score=0.5,
    )
    plan = CharacterContextRoutingPlan(
        gate=current_gate,
        fallback_gate=None,
        final_query="current question",
        retrieval_mode="current",
        pending_tool_id="",
        knowledge_source="turn_intelligence",
        pending_action_source="not_requested",
        requested_tasks=("knowledge",),
        current_assessment=current,
        contextual_assessment=contextual,
        unified_outcome=outcome(
            route="current",
            knowledge_source="turn_intelligence",
        ),
        contextual_no_hit_gate=contextual_gate,
    )
    routing = FakeRoutingService(plan)
    orchestrator = ContextOrchestrator(
        repository,  # type: ignore[arg-type]
        settings=Settings(
            environment="test",
            turn_intelligence_character_context_mode="active",
        ),
        knowledge_route_gate=gate,  # type: ignore[arg-type]
    )
    orchestrator._character_context_routing_live = routing  # type: ignore[assignment]
    current_payload = payload()
    current_payload.recent_messages = [
        {
            "message_id": "message-1",
            "author_id": "user-1",
            "author_display_name": "Alice",
            "text": "context question",
            "emojis": [],
            "stickers": [],
            "is_bot": False,
        }
    ]  # type: ignore[assignment]

    result = orchestrator.build(
        owner_id="owner-1",
        payload=current_payload,
        character_card_id="card-ann",
    )

    assert routing.calls == 1
    assert gate.decide_calls == 0
    assert repository.retrieve_queries == [
        "current question",
        "context question\ncurrent question",
    ]
    assert result.trace.rag_reason == "no_hits"
    assert result.trace.turn_intelligence_mode == "active"
    assert result.trace.turn_intelligence_knowledge_source == "turn_intelligence"
