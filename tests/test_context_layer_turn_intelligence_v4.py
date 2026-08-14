from __future__ import annotations

from dataclasses import dataclass

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.character_context_routing import CharacterContextRoutingPlan
from echo_masque.character_turn_intelligence import CharacterTurnIntelligenceOutcome
from echo_masque.config import Settings
from echo_masque.context_layer import ContextOrchestrator
from echo_masque.knowledge_route_gate import KnowledgeRouteAssessment, KnowledgeRouteDecision
from echo_masque.persistence import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord


@dataclass(frozen=True)
class FakeRetrievalResult:
    candidates: tuple[object, ...] = ()
    eligible_base_count: int = 1
    candidate_chunk_count: int = 0


class FakeKnowledgeRepository:
    def __init__(self, result: FakeRetrievalResult | None = None) -> None:
        self.database = Database("sqlite://")
        self.database.initialize()
        self.result = result or FakeRetrievalResult(eligible_base_count=0)
        self.retrieve_queries: list[str] = []

    def retrieve_for_turn(self, *, query: str, **_kwargs: object) -> FakeRetrievalResult:
        self.retrieve_queries.append(query)
        return self.result


class FakeKnowledgeGate:
    def __init__(self, decision: KnowledgeRouteDecision) -> None:
        self.decision_value = decision
        self.decide_calls = 0

    def decide(self, **_kwargs: object) -> KnowledgeRouteDecision:
        self.decide_calls += 1
        return self.decision_value


class FakeRoutingService:
    def __init__(self, plan: CharacterContextRoutingPlan) -> None:
        self.plan = plan
        self.calls = 0

    def resolve(self, **_kwargs: object) -> CharacterContextRoutingPlan:
        self.calls += 1
        return self.plan


def deployment() -> CharacterDeploymentRecord:
    return CharacterDeploymentRecord(
        id="deployment-ann",
        owner_id="owner-1",
        character_card_id="card-ann",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-1",
        workspace_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        thread_id="",
        thread_name="",
        participation_mode="smart",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="active",
        last_error="",
    )


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


def outcome(*, route: str | None) -> CharacterTurnIntelligenceOutcome:
    return CharacterTurnIntelligenceOutcome(
        knowledge_route=route,  # type: ignore[arg-type]
        knowledge_source="turn_intelligence",
        pending_action_continue=None,
        pending_action_tool_id="",
        pending_action_source="not_requested",
        requested_tasks=("knowledge",),
    )


def test_off_mode_keeps_legacy_gate() -> None:
    repository = FakeKnowledgeRepository()
    gate = FakeKnowledgeGate(KnowledgeRouteDecision("no_eligible_bases", False, 0))
    orchestrator = ContextOrchestrator(
        repository,  # type: ignore[arg-type]
        settings=Settings(
            environment="test",
            semantic_embedding_enabled=False,
            turn_intelligence_character_context_mode="off",
        ),
        knowledge_route_gate=gate,  # type: ignore[arg-type]
    )

    result = orchestrator.build(
        payload=payload(),
        deployment=deployment(),
        character_name="Ann",
    )

    assert gate.decide_calls == 1
    assert repository.retrieve_queries == []
    assert result.trace.rag_reason == "no_matching_knowledge_base"
    assert result.trace.turn_intelligence_mode == "off"


def test_shadow_mode_uses_legacy_result_but_records_unified_plan() -> None:
    repository = FakeKnowledgeRepository()
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
        unified_outcome=outcome(route="off"),
    )
    routing = FakeRoutingService(plan)
    orchestrator = ContextOrchestrator(
        repository,  # type: ignore[arg-type]
        settings=Settings(
            environment="test",
            semantic_embedding_enabled=False,
            turn_intelligence_character_context_mode="shadow",
        ),
        character_context_routing_service=routing,  # type: ignore[arg-type]
    )

    result = orchestrator.build(
        payload=payload(),
        deployment=deployment(),
        character_name="Ann",
    )

    assert routing.calls == 1
    assert repository.retrieve_queries == []
    assert result.trace.turn_intelligence_mode == "shadow"
    assert result.trace.turn_intelligence_requested_tasks == ["knowledge"]
    assert result.trace.turn_intelligence_knowledge_source == "legacy_shadow"
    assert result.trace.turn_intelligence_knowledge_route == "off"


def test_active_current_no_hits_reuses_precomputed_contextual_gate() -> None:
    repository = FakeKnowledgeRepository(FakeRetrievalResult())
    current = assessment("gray")
    contextual = assessment("gray", contextual=True)
    contextual_gate = KnowledgeRouteDecision("matched", True, 1, best_dense_score=0.5)
    plan = CharacterContextRoutingPlan(
        gate=KnowledgeRouteDecision("matched", True, 1, best_dense_score=0.5),
        fallback_gate=None,
        final_query="current question",
        retrieval_mode="current",
        pending_tool_id="",
        knowledge_source="turn_intelligence",
        pending_action_source="not_requested",
        requested_tasks=("knowledge",),
        current_assessment=current,
        contextual_assessment=contextual,
        unified_outcome=outcome(route="current"),
        contextual_no_hit_gate=contextual_gate,
    )
    routing = FakeRoutingService(plan)
    orchestrator = ContextOrchestrator(
        repository,  # type: ignore[arg-type]
        settings=Settings(
            environment="test",
            semantic_embedding_enabled=False,
            turn_intelligence_character_context_mode="active",
        ),
        character_context_routing_service=routing,  # type: ignore[arg-type]
    )
    current_payload = payload()
    current_payload.recent_messages = [
        DiscordContextMessage(
            message_id="message-1",
            author_id="user-1",
            author_display_name="Alice",
            text="context question",
            emojis=[],
            stickers=[],
            is_bot=False,
        )
    ]

    result = orchestrator.build(
        payload=current_payload,
        deployment=deployment(),
        character_name="Ann",
    )

    assert routing.calls == 1
    assert repository.retrieve_queries == [
        "current question",
        "context question\ncurrent question",
    ]
    assert result.trace.turn_intelligence_mode == "active"
    assert result.trace.turn_intelligence_knowledge_source == "turn_intelligence"
    assert result.trace.retrieval_mode == "contextual_fallback"
