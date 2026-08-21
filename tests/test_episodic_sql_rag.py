from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository

from echo_masque.internal_context import InternalContextService
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository
from echo_masque.tool_runtime import ToolExecutionContext


class _RecallEncoder:
    model_name = "test/episodic-recall"
    dimension = 4

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if "salary target" in normalized or "10000" in normalized:
            return [1.0, 0.0, 0.0, 0.0]
        if "offer" in normalized or "5800" in normalized:
            return [0.0, 1.0, 0.0, 0.0]
        if "private unseen" in normalized:
            return [0.0, 0.0, 1.0, 0.0]
        return [0.25, 0.25, 0.25, 0.25]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passage(self, text: str) -> list[float]:
        return self._vector(text)


def _episode(
    repository: ConversationEpisodeRepository,
    *,
    key: str,
    topic_id: str,
    summary: str,
    channel_id: str,
    now: datetime,
):
    return repository.upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id=channel_id,
        thread_id="",
        episode_key=key,
        topic_id=topic_id,
        burst_ids=[],
        source_message_ids=[f"message-{key}"],
        participant_refs=["user-1"],
        media_refs=[],
        summary=summary,
        key_points=[summary],
        status="closed",
        now=now,
    )


def _link_topic(
    sql_rag: EpisodicSqlRagRepository,
    *,
    episode_id: str,
    topic_id: str,
) -> None:
    entity = sql_rag.upsert_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_type="topic",
        canonical_key=f"topic:{topic_id}",
        label=topic_id,
    )
    sql_rag.link_episode_entity(
        owner_id="owner-1",
        episode_id=episode_id,
        entity_id=entity.id,
    )


def test_sql_rag_expands_related_episode_but_never_unperceived_episode() -> None:
    database = Database("sqlite://")
    database.initialize()
    episodes = ConversationEpisodeRepository(database)
    sql_rag = EpisodicSqlRagRepository(database)
    now = datetime(2026, 8, 18, 1, 0, tzinfo=UTC)

    seed = _episode(
        episodes,
        key="seed",
        topic_id="job-topic",
        summary="salary target is 10000 MYR",
        channel_id="career",
        now=now,
    )
    related = _episode(
        episodes,
        key="related",
        topic_id="job-topic",
        summary="company offer is 5800 MYR",
        channel_id="offers",
        now=now + timedelta(minutes=5),
    )
    unseen = _episode(
        episodes,
        key="unseen",
        topic_id="job-topic",
        summary="private unseen compensation note",
        channel_id="private",
        now=now + timedelta(minutes=10),
    )
    for item in (seed, related, unseen):
        _link_topic(sql_rag, episode_id=item.id, topic_id="job-topic")

    for item in (seed, related):
        sql_rag.grant_character_access(
            owner_id="owner-1",
            character_card_id="character-ann",
            deployment_id="deployment-ann",
            episode_id=item.id,
            now=now,
        )

    expanded = sql_rag.expand_episode_ids(
        owner_id="owner-1",
        character_card_id="character-ann",
        seed_episode_ids=(seed.id,),
        connection_id="connection-1",
        guild_id="guild-1",
    )

    assert seed.id in expanded
    assert related.id in expanded
    assert unseen.id not in expanded


def test_internal_conversation_search_uses_server_wide_perceived_sql_expansion() -> None:
    database = Database("sqlite://")
    database.initialize()
    episodes = ConversationEpisodeRepository(database)
    sql_rag = EpisodicSqlRagRepository(database)
    now = datetime(2026, 8, 18, 1, 0, tzinfo=UTC)

    seed = _episode(
        episodes,
        key="seed",
        topic_id="job-topic",
        summary="salary target is 10000 MYR",
        channel_id="career",
        now=now,
    )
    related = _episode(
        episodes,
        key="related",
        topic_id="job-topic",
        summary="company offer is 5800 MYR",
        channel_id="offers",
        now=now + timedelta(minutes=5),
    )
    unseen = _episode(
        episodes,
        key="unseen",
        topic_id="job-topic",
        summary="private unseen compensation note",
        channel_id="private",
        now=now + timedelta(minutes=10),
    )
    for item in (seed, related, unseen):
        _link_topic(sql_rag, episode_id=item.id, topic_id="job-topic")
    for item in (seed, related):
        sql_rag.grant_character_access(
            owner_id="owner-1",
            character_card_id="character-ann",
            deployment_id="deployment-ann",
            episode_id=item.id,
            now=now,
        )

    service = InternalContextService(
        memory_repository=MemoryVNextRepository(database),
        topic_repository=ConversationTopicRepository(database),
        episode_repository=episodes,
        encoder=_RecallEncoder(),
    )
    context = ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-ann",
        character_card_id="character-ann",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="career",
    )

    result = json.loads(
        service.conversation_search({"query": "salary target", "limit": 5}, context)
    )
    refs = {item["ref"] for item in result["episodes"]}

    assert result["scope"] == "current_discord_server_perceived"
    assert result["retrieval_mode"] == "e5_seed_sql_event_entity_expand"
    assert seed.id in refs
    assert related.id in refs
    assert unseen.id not in refs
    related_item = next(item for item in result["episodes"] if item["ref"] == related.id)
    assert related_item["expanded_via_entity"] is True
