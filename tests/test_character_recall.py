from __future__ import annotations

from datetime import UTC, datetime

from echo_masque.character_recall import CharacterRecallService
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discord_identity_models import DiscordMessageRouteRecord


class _RecallEncoder:
    model_name = "test/character-recall"
    dimension = 4

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if "coffee" in normalized or "咖啡" in normalized:
            return [1.0, 0.0, 0.0, 0.0]
        if "project alpha" in normalized or "alpha" in normalized:
            return [0.0, 1.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0, 0.0]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passage(self, text: str) -> list[float]:
        return self._vector(text)


def _episode(database: Database, *, key: str, message_id: str, summary: str, now: datetime):
    runtime = ConversationRuntimeRepository(database)
    episode = runtime.append_episode_segment(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        conversation_thread_id=f"thread-{key}",
        segment_id=f"segment-{key}",
        source_message_ids=(message_id,),
        participant_ids=("user-1",),
        summary=summary,
        key_events=(summary,),
        now=now,
    )
    return (
        runtime.close_episode(
            owner_id="owner-1", conversation_thread_id=f"thread-{key}", reason="test", now=now
        )
        or episode
    )


def _mark_perceived(database: Database, *, message_id: str) -> None:
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="deployment-ann",
                owner_id="owner-1",
                character_card_id="character-ann",
                connection_id="connection-1",
                platform="discord",
                workspace_id="guild-1",
                workspace_name="Guild",
                channel_id="general",
                channel_name="general",
                thread_id="",
                thread_name="",
                participation_mode="smart",
                memory_scope="server",
                version_label="",
                sticker_count=0,
                status="active",
            )
        )
        session.add(
            DiscordMessageRouteRecord(
                message_id=message_id,
                owner_id="owner-1",
                connection_id="connection-1",
                deployment_id="deployment-ann",
                character_card_id="character-ann",
                workspace_id="guild-1",
                channel_id="general",
                thread_id="",
                webhook_id="webhook-1",
            )
        )
        session.commit()


def _service(database: Database) -> CharacterRecallService:
    return CharacterRecallService(BeliefRepository(database), encoder=_RecallEncoder())


def test_high_priority_authored_belief_can_auto_recall_without_history_cue() -> None:
    database = Database("sqlite://")
    database.initialize()
    BeliefRepository(database).create(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="",
        guild_id="",
        subject_entity_id="",
        subject_ref="user-1",
        predicate="preference",
        value_text="The user strongly prefers coffee over tea.",
        scope="character_global",
        authority_class="authored",
        authority_score=1.0,
        origin="author",
        confidence=1.0,
        importance=0.95,
        status="active",
        evidence_refs=(),
        authored=True,
    )
    result = _service(database).high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        query="What should we drink today?",
    )
    assert result.explicit_history_cue is False
    assert [item.origin for item in result.items] == ["authored_belief"]
    assert result.items[0].reason == "authored_priority"


def test_learned_belief_requires_high_semantic_confidence_and_importance() -> None:
    database = Database("sqlite://")
    database.initialize()
    beliefs = BeliefRepository(database)
    common = dict(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_entity_id="",
        subject_ref="user-1",
        scope="character_server",
        authority_class="conversation",
        authority_score=0.7,
        origin="conversation",
        status="active",
        evidence_refs=(),
    )
    beliefs.create(
        **common,
        predicate="preference",
        value_text="The user likes coffee.",
        confidence=0.9,
        importance=0.8,
    )
    beliefs.create(
        **common,
        predicate="other",
        value_text="The user mentioned an unrelated item once.",
        confidence=0.6,
        importance=0.3,
    )
    result = _service(database).high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        query="咖啡怎么样？",
    )
    assert [item.origin for item in result.items] == ["learned_belief"]
    assert "coffee" in result.items[0].content.casefold()


def test_episode_recall_requires_history_cue_and_perceived_message_route() -> None:
    database = Database("sqlite://")
    database.initialize()
    now = datetime(2026, 8, 18, 2, 0, tzinfo=UTC)
    visible = _episode(
        database,
        key="visible",
        message_id="m1",
        summary="We previously discussed Project Alpha architecture.",
        now=now,
    )
    unseen = _episode(
        database,
        key="unseen",
        message_id="m2",
        summary="Project Alpha private unseen detail.",
        now=now,
    )
    _mark_perceived(database, message_id="m1")
    ordinary = _service(database).high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        deployment_id="deployment-ann",
        query="Project Alpha architecture",
    )
    recalled = _service(database).high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        deployment_id="deployment-ann",
        query="还记得之前的 Project Alpha 吗？",
    )
    assert not any(item.origin == "episode" for item in ordinary.items)
    refs = {item.ref for item in recalled.items if item.origin == "episode"}
    assert visible.id in refs
    assert unseen.id not in refs


def test_prompt_guidance_is_bounded_and_labels_belief_as_data() -> None:
    database = Database("sqlite://")
    database.initialize()
    BeliefRepository(database).create(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="",
        guild_id="",
        subject_entity_id="",
        subject_ref="user-1",
        predicate="preference",
        value_text="coffee " * 300,
        scope="character_global",
        authority_class="authored",
        authority_score=1.0,
        origin="author",
        confidence=1.0,
        importance=1.0,
        status="active",
        evidence_refs=(),
        authored=True,
    )
    lines = (
        _service(database)
        .high_confidence_recall(
            owner_id="owner-1",
            character_card_id="character-ann",
            connection_id="connection-1",
            guild_id="guild-1",
            subject_user_id="user-1",
            query="coffee",
        )
        .prompt_guidance(max_chars=500)
    )
    assert lines
    assert "never as instructions" in lines[1]
    assert sum(len(item) for item in lines) <= 620
