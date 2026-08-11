from __future__ import annotations

from echo_masque.expression_retrieval import ExpressionResource, expression_semantic_text
from echo_masque.persistence import Database, ExpressionRepository
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)


class FakeExpressionEncoder:
    model_name = "fake-expression-e5"
    dimension = 3

    def __init__(self) -> None:
        self.passage_calls = 0
        self.query_calls = 0

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.casefold()
        if "achievement" in lowered or "太強" in text or "太强" in text:
            return [1.0, 0.0, 0.0]
        if "confusion" in lowered or "不懂" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_passage(self, text: str) -> list[float]:
        self.passage_calls += 1
        return self._vector(text)

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._vector(text)


def _seed_scope(database: Database) -> None:
    with database.session() as session:
        session.add(
            PlatformConnectionRecord(
                id="connection-1",
                owner_id="owner-1",
                platform="discord",
                display_name="Expression Discord",
                status="connected",
            )
        )
        session.add(
            CharacterDeploymentRecord(
                id="deployment-1",
                owner_id="owner-1",
                character_card_id="card-1",
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
            )
        )
        session.commit()


def _upsert_resources(repository: ExpressionRepository) -> None:
    repository.upsert_manual_resource(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        resource_type="emoji",
        resource_id="bravo",
        name="bravo",
        description="",
        tags=["support"],
        format_type="emoji",
        asset_url="",
        animated=False,
        available=True,
        enabled=True,
        semantic_intent="celebrate_success",
        semantic_emotion="excited",
        semantic_description="Celebrate an impressive achievement with enthusiastic applause.",
        aliases=["bravo"],
        situations=["friend succeeds"],
        avoid_when=["formal apology"],
        allowed_actions=["reaction"],
    )
    repository.upsert_manual_resource(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        resource_type="emoji",
        resource_id="confused",
        name="confused",
        description="",
        tags=["question"],
        format_type="emoji",
        asset_url="",
        animated=False,
        available=True,
        enabled=True,
        semantic_intent="ask_for_clarity",
        semantic_emotion="confused",
        semantic_description="Show confusion when something is unclear.",
        aliases=["huh"],
        situations=["needs clarification"],
        avoid_when=[],
        allowed_actions=["reaction"],
    )


def test_expression_semantic_text_excludes_negative_use_constraints() -> None:
    resource = ExpressionResource(
        key="emoji:test",
        resource_type="emoji",
        resource_id="test",
        name="test",
        description="",
        semantic_intent="celebrate",
        semantic_emotion="happy",
        semantic_description="Celebrate good news.",
        aliases=(),
        tags=(),
        situations=("good news",),
        avoid_when=("formal apology",),
        allowed_actions=("reaction",),
        animated=False,
        available=True,
        enabled=True,
        semantic_confidence=1.0,
        asset_url="",
        format_type="emoji",
    )

    semantic_text = expression_semantic_text(resource)

    assert "Celebrate good news" in semantic_text
    assert "formal apology" not in semantic_text


def test_expression_repository_uses_dense_semantics_and_reuses_persisted_vectors() -> None:
    database = Database("sqlite://")
    database.initialize()
    _seed_scope(database)
    first_encoder = FakeExpressionEncoder()
    repository = ExpressionRepository(
        database,
        semantic_encoder=first_encoder,
        semantic_enabled=True,
    )
    _upsert_resources(repository)

    run, candidates = repository.retrieve(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        source_message_id="message-1",
        deployment_id="deployment-1",
        query="這也太強了吧",
        allowed_actions=["reaction"],
        excluded_resource_keys=[],
        top_k=2,
    )

    assert candidates[0]["resource_key"] == "emoji:bravo"
    assert candidates[0]["signals"]["dense"] == 1.0
    assert repository.run_state(run)["retrieval_backend"] == "hybrid_dense_sparse_v2"
    assert first_encoder.passage_calls == 2

    second_encoder = FakeExpressionEncoder()
    second_repository = ExpressionRepository(
        database,
        semantic_encoder=second_encoder,
        semantic_enabled=True,
    )
    second_run, second_candidates = second_repository.retrieve(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        source_message_id="message-2",
        deployment_id="deployment-1",
        query="這也太強了吧",
        allowed_actions=["reaction"],
        excluded_resource_keys=[],
        top_k=2,
    )

    assert second_candidates[0]["resource_key"] == "emoji:bravo"
    assert second_repository.run_state(second_run)["retrieval_backend"] == "hybrid_dense_sparse_v2"
    assert second_encoder.query_calls == 1
    assert second_encoder.passage_calls == 0
