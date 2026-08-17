from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from echo_masque.conversation_intelligence_governance import (
    ConversationIntelligenceGovernanceService,
)
from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_models import (
    CharacterEpisodeAccessRecord,
    ConversationEntityRecord,
    ConversationEpisodeEntityRecord,
)
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository
from echo_masque.persistence.memory_vnext_models import ConversationMemoryVNextRecord
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository


def test_topic_cleanup_removes_sql_rag_indexes_but_preserves_core_memory() -> None:
    database = Database("sqlite://")
    database.initialize()
    now = datetime(2026, 8, 18, 2, 0, tzinfo=UTC)
    topics = ConversationTopicRepository(database)
    episodes = ConversationEpisodeRepository(database)
    sql_rag = EpisodicSqlRagRepository(database)

    topic = topics.create(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        topic_label="Polluted old topic",
        summary="mixed unrelated content",
        keywords_json="[]",
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json="[]",
        last_message_id="message-1",
        now=now,
    )
    episode = episodes.upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        episode_key="episode-1",
        topic_id=topic.id,
        burst_ids=[],
        source_message_ids=["message-1"],
        participant_refs=["user-1"],
        media_refs=[],
        summary="polluted evidence",
        key_points=["polluted evidence"],
        status="closed",
        now=now,
    )
    entity = sql_rag.upsert_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_type="topic",
        canonical_key=f"topic:{topic.id}",
        label=topic.topic_label,
    )
    sql_rag.link_episode_entity(
        owner_id="owner-1",
        episode_id=episode.id,
        entity_id=entity.id,
    )
    sql_rag.grant_character_access(
        owner_id="owner-1",
        character_card_id="character-ann",
        deployment_id="deployment-ann",
        episode_id=episode.id,
        now=now,
    )
    synthesized = MemoryVNextRepository(database).create(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="fact",
        content="polluted synthesized memory",
        provenance_episode_ids=(episode.id,),
    )
    core = CoreMemoryRepository(database).upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="fact",
        content="explicit durable memory must survive derived cleanup",
    )

    impact = ConversationIntelligenceGovernanceService(database).delete_topic_derived(
        owner_id="owner-1",
        topic_id=topic.id,
    )

    assert impact.topic_found is True
    assert impact.episodes == 1
    assert impact.memories == 1
    assert topics.get(topic.id, "owner-1") is None
    assert MemoryVNextRepository(database).get(synthesized.id, "owner-1") is None
    assert CoreMemoryRepository(database).get(owner_id="owner-1", memory_id=core.id) is not None

    with database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(ConversationEpisodeRecord)
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(CharacterEpisodeAccessRecord)
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(ConversationEpisodeEntityRecord)
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(ConversationEntityRecord)
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(ConversationMemoryVNextRecord)
        ) == 0
