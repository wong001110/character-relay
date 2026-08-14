from __future__ import annotations

from echo_masque.admin_runtime import SemanticRoutingJudgeProfile
from echo_masque.knowledge_route_gate import KnowledgeRouteGate
from echo_masque.persistence import Database, KnowledgeRepository


class GrayEncoder:
    model_name = "test/gray-e5"
    dimension = 2

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0]

    def embed_passage(self, _text: str) -> list[float]:
        return [0.5, 0.8660254038]


class FakeRuntime:
    @staticmethod
    def semantic_routing_config() -> SemanticRoutingJudgeProfile:
        return SemanticRoutingJudgeProfile(enabled=True)


class FailingJudge:
    runtime = FakeRuntime()

    def __init__(self) -> None:
        self.calls = 0

    def decide(self, **_kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise AssertionError("assess() must never invoke the model Judge")


def repository() -> KnowledgeRepository:
    database = Database("sqlite://")
    database.initialize()
    repo = KnowledgeRepository(database, semantic_enabled=False)
    base = repo.create_base(
        owner_id="owner-1",
        name="Docs",
        description="Character Relay architecture",
        scope_type="server",
        connection_id="connection-1",
        guild_id="guild-1",
    )
    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="Architecture",
        content="Character Relay runtime architecture and knowledge routing.",
    )
    return repo


def gate() -> tuple[KnowledgeRouteGate, FailingJudge]:
    value = KnowledgeRouteGate(
        repository(),
        encoder=GrayEncoder(),
        semantic_enabled=True,
    )
    judge = FailingJudge()
    value._routing_judge = judge  # type: ignore[assignment]
    return value, judge


def test_assess_returns_gray_evidence_without_calling_judge() -> None:
    value, judge = gate()
    assessment = value.assess(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-ann",
        query="Why is the sky bright today?",
    )

    assert assessment.route == "gray"
    assert assessment.gray_zone is True
    assert assessment.best_dense_score == 0.5
    assert assessment.route_labels
    assert assessment.current_message == "Why is the sky bright today?"
    assert judge.calls == 0


def test_contextual_assessment_is_one_gray_evidence_record_without_judge() -> None:
    value, judge = gate()
    assessment = value.assess(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        character_card_id="card-ann",
        query="previous architecture question\nwhat about that part?",
    )

    assert assessment.route == "gray"
    assert assessment.is_contextual is True
    assert assessment.fallback_should_retrieve is False
    assert judge.calls == 0
