from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from echo_masque.conversation_intelligence_governance import (
    ConversationIntelligenceGovernanceService,
    DerivedResetResult,
)
from echo_masque.conversation_topic_lifecycle import evaluate_topic_lifecycle
from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.conversation_topic_decision_models import ConversationTopicDecisionRecord
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_vnext_models import ConversationMemoryVNextRecord


def _database() -> Database:
    database = Database("sqlite://")
    database.initialize()
    return database


def _topic_record(*, now: datetime, status: str = "active") -> ConversationTopicRecord:
    return ConversationTopicRecord(
        id="topic-1",
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        topic_label="Topic",
        summary="summary",
        status=status,
        message_count=1,
        last_message_id="m1",
        started_at=now,
        last_active_at=now,
        updated_at=now,
    )


def test_reset_result_remains_api_serializable() -> None:
    result = DerivedResetResult(topics=2, memories=3)
    assert result.__dict__["topics"] == 2
    assert result.__dict__["memories"] == 3


def test_topic_lifecycle_cools_stale_active_topic() -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    topic = _topic_record(now=now - timedelta(hours=7))

    decision = evaluate_topic_lifecycle(topic, now=now)

    assert decision is not None
    assert decision.from_status == "active"
    assert decision.to_status == "cooling"
    assert decision.reason == "active_idle_timeout"


def test_live_pending_action_holds_active_topic_open() -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    topic = _topic_record(now=now - timedelta(hours=7))
    topic.pending_actions_json = json.dumps(
        [
            {
                "tool_id": "image.generate",
                "state": "blocked_unavailable",
                "expires_at": (now + timedelta(hours=1)).isoformat(),
            }
        ]
    )

    assert evaluate_topic_lifecycle(topic, now=now) is None


def test_repository_lazy_lifecycle_removes_stale_topic_from_active_lookup() -> None:
    database = _database()
    topics = ConversationTopicRepository(database)
    old = datetime.now(UTC) - timedelta(hours=7)
    topic = topics.create(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        topic_label="old topic",
        summary="old topic summary",
        keywords_json="[]",
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json='["user:user-1"]',
        last_message_id="m1",
        now=old,
    )

    active = topics.active_for_scope(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
    )

    assert active is None
    persisted = topics.get(topic.id, "owner-1")
    assert persisted is not None
    assert persisted.status == "cooling"
    traces = topics.decisions.recent_for_scope(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
    )
    assert any(item.decision == "lifecycle" and "active_to_cooling" in item.reason for item in traces)


def test_delete_topic_derived_removes_episode_memory_and_decision_trace() -> None:
    database = _database()
    topics = ConversationTopicRepository(database)
    episodes = ConversationEpisodeRepository(database)
    governance = ConversationIntelligenceGovernanceService(database)
    now = datetime.now(UTC)

    topic = topics.create(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        topic_label="polluted topic",
        summary="mixed unrelated content",
        keywords_json="[]",
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json='["user:user-1"]',
        last_message_id="raw-discord-message-1",
        now=now,
    )
    episode = episodes.upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        episode_key="burst-1",
        topic_id=topic.id,
        burst_ids=["burst-1"],
        source_message_ids=["raw-discord-message-1"],
        participant_refs=["user:user-1"],
        media_refs=[],
        summary="episode",
        key_points=["mixed"],
        now=now,
    )
    memory = ConversationMemoryVNextRecord(
        id="memory-1",
        owner_id="owner-1",
        character_card_id="card-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="topic_local",
        subject_user_id="",
        topic_id=topic.id,
        memory_type="fact",
        content="polluted memory",
        confidence=0.8,
        importance=0.5,
        status="active",
        provenance_episode_ids_json=json.dumps([episode.id]),
        source_message_ids_json=json.dumps(["raw-discord-message-1"]),
        created_at=now,
        updated_at=now,
    )
    with database.session() as session:
        session.add(memory)
        session.commit()

    impact = governance.topic_delete_impact(owner_id="owner-1", topic_id=topic.id)
    assert impact.topic_found
    assert impact.episodes == 1
    assert impact.memories == 1

    deleted = governance.delete_topic_derived(owner_id="owner-1", topic_id=topic.id)
    assert deleted.topic_found
    assert topics.get(topic.id, "owner-1") is None
    with database.session() as session:
        assert session.scalar(select(ConversationEpisodeRecord).where(ConversationEpisodeRecord.id == episode.id)) is None
        assert session.scalar(select(ConversationMemoryVNextRecord).where(ConversationMemoryVNextRecord.id == memory.id)) is None
        assert session.scalar(
            select(ConversationTopicDecisionRecord).where(
                (ConversationTopicDecisionRecord.from_topic_id == topic.id)
                | (ConversationTopicDecisionRecord.to_topic_id == topic.id)
            )
        ) is None

    # The governance service only owns derived intelligence. The source Discord message ID is
    # carried as provenance and is never interpreted as a request to delete connector evidence.
    assert "raw-discord-message-1" in episode.source_message_ids_json
