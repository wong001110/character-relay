from __future__ import annotations

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.context_layer import ContextOrchestrator
from echo_masque.knowledge_route_gate import KnowledgeRouteGate
from echo_masque.persistence import Database, KnowledgeRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord


class _RouteEncoder:
    model_name = "test/route-e5"
    dimension = 3

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if "smart output" in normalized or "结构化聊天行为" in normalized:
            return [0.0, 1.0, 0.0]
        if "image" in normalized or "猫" in normalized:
            return [1.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_passage(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class _CountingKnowledgeRepository(KnowledgeRepository):
    def __init__(self, database: Database) -> None:
        super().__init__(database, semantic_enabled=False)
        self.retrieve_calls = 0

    def retrieve_for_turn(self, **kwargs):  # type: ignore[no-untyped-def, override]
        self.retrieve_calls += 1
        return super().retrieve_for_turn(**kwargs)


def _repository() -> _CountingKnowledgeRepository:
    database = Database("sqlite://")
    database.initialize()
    return _CountingKnowledgeRepository(database)


def _seed(repo: KnowledgeRepository) -> None:
    base = repo.create_base(
        owner_id="owner-1",
        name="Character Relay docs",
        description="Architecture and runtime behavior documentation.",
        scope_type="server",
        connection_id="connection-1",
        guild_id="guild-a",
    )
    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="Smart Output V1",
        content=(
            "Character Relay calls the structured Discord behavior layer Smart Output V1. "
            "It controls message, reaction, expression, and ignore actions."
        ),
    )


def _deployment() -> CharacterDeploymentRecord:
    return CharacterDeploymentRecord(
        id="deployment-ann",
        owner_id="owner-1",
        character_card_id="card-ann",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-a",
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


def _payload(text: str) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="message-1",
        guild_id="guild-a",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        category_id="",
        thread_id="",
        thread_name="",
        author_id="user-1",
        author_display_name="Juen",
        text=text,
        emojis=[],
        mentioned_bot=False,
        replied_to_bot=False,
        smart_candidate=True,
        author_is_bot=False,
        stickers=[],
        available_characters=[],
        mentionable_participants=[],
        recent_messages=[],
        interaction_session_id="",
        interaction_type="",
        interaction_intensity="",
        interaction_round=0,
        interaction_total_rounds=0,
        interaction_position=0,
        interaction_participant_count=0,
        interaction_target_user_id="",
        interaction_target_display_name="",
        expression_run_id="",
        expression_candidates=[],
    )


def _gate(repo: KnowledgeRepository) -> KnowledgeRouteGate:
    return KnowledgeRouteGate(
        repo,
        encoder=_RouteEncoder(),
        semantic_enabled=True,
    )


def test_route_gate_rejects_unrelated_turn_before_chunk_retrieval() -> None:
    repo = _repository()
    _seed(repo)
    decision = _gate(repo).decide(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-a",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-ann",
        query="generate a cat image",
    )

    assert decision.status == "not_relevant"
    assert decision.should_retrieve is False
    assert decision.eligible_base_count == 1


def test_route_gate_matches_cross_language_semantic_query() -> None:
    repo = _repository()
    _seed(repo)
    decision = _gate(repo).decide(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-a",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-ann",
        query="这个结构化聊天行为层叫什么?",
    )

    assert decision.status == "matched"
    assert decision.should_retrieve is True
    assert decision.best_dense_score == 1.0


def test_context_orchestrator_does_not_call_rag_for_unrelated_turn() -> None:
    repo = _repository()
    _seed(repo)
    orchestrator = ContextOrchestrator(repo, knowledge_route_gate=_gate(repo))

    context = orchestrator.build(
        payload=_payload("generate a cat image"),
        deployment=_deployment(),
        character_name="Ann",
    )

    assert repo.retrieve_calls == 0
    assert context.knowledge == ()
    assert context.trace.rag_status == "skipped"
    assert context.trace.rag_reason == "knowledge_gate_not_relevant"
    assert context.trace.rag_gate_status == "not_relevant"
    assert context.trace.candidate_chunk_count == 0


def test_context_orchestrator_retrieves_after_route_match() -> None:
    repo = _repository()
    _seed(repo)
    orchestrator = ContextOrchestrator(repo, knowledge_route_gate=_gate(repo))

    context = orchestrator.build(
        payload=_payload("What is Smart Output V1?"),
        deployment=_deployment(),
        character_name="Ann",
    )

    assert repo.retrieve_calls == 1
    assert context.trace.rag_gate_status == "matched"
    assert context.trace.rag_status == "completed"
    assert context.trace.rag_reason == "ok"
    assert context.knowledge
