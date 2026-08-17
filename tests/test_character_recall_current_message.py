from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.character_recall import CharacterRecallService
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository


class _AlphaEncoder:
    model_name = "test/current-message-recall"
    dimension = 3

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def test_explicit_history_recall_excludes_current_trigger_episode() -> None:
    database = Database("sqlite://")
    database.initialize()
    episodes = ConversationEpisodeRepository(database)
    sql_rag = EpisodicSqlRagRepository(database)
    now = datetime(2026, 8, 18, 3, 0, tzinfo=UTC)

    historical = episodes.upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        episode_key="historical",
        topic_id="topic-alpha",
        burst_ids=[],
        source_message_ids=["old-message"],
        participant_refs=["user-1"],
        media_refs=[],
        summary="Earlier Project Alpha architecture discussion.",
        key_points=["Project Alpha architecture"],
        status="closed",
        now=now,
    )
    current = episodes.upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        episode_key="current",
        topic_id="topic-alpha",
        burst_ids=[],
        source_message_ids=["current-message"],
        participant_refs=["user-1"],
        media_refs=[],
        summary="还记得之前的 Project Alpha architecture 吗？",
        key_points=["Project Alpha architecture"],
        status="closed",
        now=now + timedelta(minutes=5),
    )
    topic = sql_rag.upsert_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_type="topic",
        canonical_key="topic:topic-alpha",
        label="Project Alpha",
    )
    for episode in (historical, current):
        sql_rag.link_episode_entity(
            owner_id="owner-1",
            episode_id=episode.id,
            entity_id=topic.id,
        )
        sql_rag.grant_character_access(
            owner_id="owner-1",
            character_card_id="character-ann",
            deployment_id="deployment-ann",
            episode_id=episode.id,
            now=now,
        )

    result = CharacterRecallService(
        MemoryVNextRepository(database),
        encoder=_AlphaEncoder(),
    ).high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        topic_id="topic-alpha",
        query="还记得之前的 Project Alpha architecture 吗？",
        exclude_source_message_id="current-message",
    )

    episode_refs = {item.ref for item in result.items if item.origin == "episode"}
    assert historical.id in episode_refs
    assert current.id not in episode_refs
