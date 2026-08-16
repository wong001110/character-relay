from __future__ import annotations

from datetime import UTC, datetime

import pytest

from echo_masque.conversation_consolidation import ConversationConsolidationService
from echo_masque.conversation_consolidation_events import ConversationConsolidationEventBus
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordConnectorEventRecord,
)
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository
from echo_masque.persistence.server_knowledge_repository import (
    ConsolidationCheckpointRepository,
    ConversationAuthorityGraphRepository,
    ServerWikiRepository,
)
from echo_masque.utility_gateway_contracts import WikiUtilityResult


def _database() -> Database:
    database = Database("sqlite:///:memory:")
    database.initialize()
    return database


def _topic(database: Database, *, guild_id: str = "guild-a"):
    return ConversationTopicRepository(database).create(
        owner_id="owner-1",
        platform="discord",
        connection_id="conn-1",
        guild_id=guild_id,
        channel_id="channel-1",
        thread_id="",
        topic_label="Zenless Zone Zero antagonist discussion",
        summary="Member: I think the apparent antagonist is a misdirection.",
        keywords_json='["zenless", "antagonist", "plot"]',
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json='[{"user_id":"user-1","display_name":"Member"}]',
        last_message_id="msg-1",
    )


def _episode(database: Database, topic_id: str, *, guild_id: str = "guild-a"):
    return ConversationEpisodeRepository(database).upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="conn-1",
        guild_id=guild_id,
        channel_id="channel-1",
        thread_id="",
        episode_key="message:msg-1",
        topic_id=topic_id,
        burst_ids=[],
        source_message_ids=["msg-1"],
        participant_refs=["user-1"],
        media_refs=[],
        summary="I think the apparent antagonist is a misdirection.",
        key_points=["The member doubts the apparent antagonist reveal."],
        status="closed",
    )


def _service(database: Database, gateway=None) -> ConversationConsolidationService:
    return ConversationConsolidationService(
        topic_repository=ConversationTopicRepository(database),
        episode_repository=ConversationEpisodeRepository(database),
        memory_repository=MemoryVNextRepository(database),
        wiki_repository=ServerWikiRepository(database),
        graph_repository=ConversationAuthorityGraphRepository(database),
        checkpoint_repository=ConsolidationCheckpointRepository(database),
        gateway=gateway,
        poll_seconds=5,
        maintenance_every=2,
    )


def test_server_wiki_is_isolated_by_discord_guild() -> None:
    database = _database()
    repository = ServerWikiRepository(database)
    repository.upsert_topic_page(
        owner_id="owner-1",
        connection_id="conn-1",
        guild_id="guild-a",
        topic_id="topic-a",
        title="Guild A plot notes",
        body="The group discussed the apparent antagonist.",
        keywords=("antagonist",),
        source_episode_ids=("episode-a",),
        source_hash="a" * 64,
        confidence=0.8,
    )
    repository.upsert_topic_page(
        owner_id="owner-1",
        connection_id="conn-1",
        guild_id="guild-b",
        topic_id="topic-b",
        title="Guild B cooking notes",
        body="The group discussed noodles.",
        keywords=("noodles",),
        source_episode_ids=("episode-b",),
        source_hash="b" * 64,
        confidence=0.8,
    )

    guild_a = repository.lookup(
        owner_id="owner-1",
        connection_id="conn-1",
        guild_id="guild-a",
        query="antagonist",
        limit=5,
    )
    guild_b = repository.lookup(
        owner_id="owner-1",
        connection_id="conn-1",
        guild_id="guild-b",
        query="antagonist",
        limit=5,
    )

    assert [item["title"] for item in guild_a] == ["Guild A plot notes"]
    assert guild_b == []


@pytest.mark.asyncio
async def test_topic_cooling_signal_builds_wiki_and_typed_graph() -> None:
    database = _database()
    topic = _topic(database)
    episode = _episode(database, topic.id)
    service = _service(database)
    ConversationConsolidationEventBus.configure(service.signal_topic)
    try:
        ConversationTopicRepository(database).set_status(
            topic_id=topic.id,
            owner_id="owner-1",
            status="cooling",
        )
        processed = await service.run_once()
    finally:
        ConversationConsolidationEventBus.configure(None)

    assert processed == 1
    page = ServerWikiRepository(database).get_topic_page(
        owner_id="owner-1",
        topic_id=topic.id,
    )
    assert page is not None
    assert page.visibility_scope == "server"
    assert page.stale is False
    assert episode.id in page.source_episode_ids_json

    graph = ConversationAuthorityGraphRepository(database)
    provenance = graph.list_scope(
        owner_id="owner-1",
        connection_id="conn-1",
        guild_id="guild-a",
        authority_class="provenance",
    )
    derived = graph.list_scope(
        owner_id="owner-1",
        connection_id="conn-1",
        guild_id="guild-a",
        authority_class="derived_index",
    )
    assert any(item.relation == "contains_episode" for item in provenance)
    assert any(item.relation == "contains_message" for item in provenance)
    assert any(item.relation == "keyword_index" for item in derived)


class _FakeGateway:
    def invoke(self, capability, schema, **kwargs):
        del kwargs
        if capability == "knowledge_wiki":
            return (
                WikiUtilityResult(
                    title="Antagonist discussion",
                    body="The server discussed evidence around an apparent antagonist reveal.",
                    keywords=("antagonist", "plot"),
                    confidence=0.9,
                ),
                object(),
            )
        assert capability == "memory_intelligence"
        return (
            schema.model_validate(
                {
                    "schema_version": "conversation-memory-consolidation.v1",
                    "proposals": [
                        {
                            "action": "create",
                            "scope_type": "character_user",
                            "subject_ref": "u1",
                            "memory_type": "preference",
                            "content": "The member enjoys discussing antagonist theories.",
                            "target_ref": "",
                            "confidence": 0.88,
                            "importance": 0.7,
                            "reason_code": "repeated_interest",
                        }
                    ],
                }
            ),
            object(),
        )


def test_consolidation_writes_scoped_memory_and_temporal_fact_edge() -> None:
    database = _database()
    topic = _topic(database)
    _episode(database, topic.id)
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="deployment-1",
                owner_id="owner-1",
                character_card_id="character-1",
                connection_id="conn-1",
                platform="discord",
                workspace_id="guild-a",
                workspace_name="Guild A",
                channel_id="channel-1",
                channel_name="general",
                thread_id="",
                thread_name="",
                status="active",
            )
        )
        session.add(
            DiscordConnectorEventRecord(
                id="event-1",
                owner_id="connector-owner",
                connection_id="conn-1",
                level="info",
                event_type="delivery_success",
                message="Character reply delivered.",
                guild_id="guild-a",
                channel_id="channel-1",
                source_message_id="msg-1",
                deployment_id="deployment-1",
                character_name="Ann",
                occurred_at=datetime.now(UTC),
            )
        )
        session.commit()

    result = _service(database, _FakeGateway()).consolidate_topic(
        owner_id="owner-1",
        topic_id=topic.id,
        reason="topic_cooling",
    )

    assert result.status == "completed"
    assert result.memory_count == 1
    memories = MemoryVNextRepository(database).active_candidates(
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="conn-1",
        guild_id="guild-a",
        subject_user_id="user-1",
        topic_id=topic.id,
    )
    assert len(memories) == 1
    assert memories[0].scope_type == "character_user"
    assert "antagonist theories" in memories[0].content

    other_server = MemoryVNextRepository(database).active_candidates(
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="conn-1",
        guild_id="guild-b",
        subject_user_id="user-1",
        topic_id=topic.id,
    )
    assert other_server == []

    temporal = ConversationAuthorityGraphRepository(database).list_scope(
        owner_id="owner-1",
        connection_id="conn-1",
        guild_id="guild-a",
        authority_class="temporal_fact",
    )
    assert len(temporal) == 1
    assert temporal[0].source_ref == "user:user-1"
    assert temporal[0].target_ref.startswith("memory:")


def test_checkpoint_skips_unchanged_completed_projection() -> None:
    database = _database()
    topic = _topic(database)
    _episode(database, topic.id)
    service = _service(database)

    first = service.consolidate_topic(
        owner_id="owner-1",
        topic_id=topic.id,
        reason="manual",
    )
    second = service.consolidate_topic(
        owner_id="owner-1",
        topic_id=topic.id,
        reason="manual",
    )

    assert first.status == "completed"
    assert second.status == "skipped"
    checkpoint = ConsolidationCheckpointRepository(database).get(
        owner_id="owner-1",
        topic_id=topic.id,
    )
    assert checkpoint is not None
    assert checkpoint.status == "completed"
