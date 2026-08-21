from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from echo_masque.internal_context import InternalContextService
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository
from echo_masque.tool_runtime import ToolExecutionContext


class _RecallEncoder:
    model_name = "test/episodic-recall"
    dimension = 4

    def embed_query(self, text: str) -> list[float]:
        return self.embed_passage(text)

    def embed_passage(self, text: str) -> list[float]:
        lowered = text.casefold()
        if "salary target" in lowered or "10000" in lowered:
            return [1.0, 0.0, 0.0, 0.0]
        if "offer" in lowered or "5800" in lowered:
            return [0.0, 1.0, 0.0, 0.0]
        return [0.25, 0.25, 0.25, 0.25]


def _episode(
    runtime: ConversationRuntimeRepository,
    *,
    key: str,
    summary: str,
    channel_id: str,
    now: datetime,
):
    episode = runtime.append_episode_segment(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id=channel_id,
        discord_thread_id="",
        conversation_thread_id=f"thread-{key}",
        segment_id=f"segment-{key}",
        source_message_ids=(f"message-{key}",),
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


def _link_entity(sql_rag: EpisodicSqlRagRepository, *, episode_id: str) -> None:
    entity = sql_rag.upsert_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_type="project",
        canonical_key="project:job-search",
        label="Job search",
    )
    sql_rag.link_episode_entity(owner_id="owner-1", episode_id=episode_id, entity_id=entity.id)


def test_sql_rag_expands_related_v3_episode_but_never_unperceived_episode() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = ConversationRuntimeRepository(database)
    sql_rag = EpisodicSqlRagRepository(database)
    now = datetime(2026, 8, 18, 1, 0, tzinfo=UTC)
    seed = _episode(
        runtime, key="seed", summary="salary target is 10000 MYR", channel_id="career", now=now
    )
    related = _episode(
        runtime,
        key="related",
        summary="company offer is 5800 MYR",
        channel_id="offers",
        now=now + timedelta(minutes=5),
    )
    unseen = _episode(
        runtime,
        key="unseen",
        summary="private unseen compensation note",
        channel_id="private",
        now=now + timedelta(minutes=10),
    )
    for item in (seed, related, unseen):
        _link_entity(sql_rag, episode_id=item.id)
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


def test_internal_conversation_search_reads_v3_episodes_without_topic_scope() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = ConversationRuntimeRepository(database)
    now = datetime(2026, 8, 18, 1, 0, tzinfo=UTC)
    seed = _episode(
        runtime, key="seed", summary="salary target is 10000 MYR", channel_id="career", now=now
    )
    related = _episode(
        runtime,
        key="related",
        summary="company offer is 5800 MYR",
        channel_id="offers",
        now=now + timedelta(minutes=5),
    )
    service = InternalContextService(
        BeliefRepository(database),
        ConversationStructureRepository(database),
        runtime,
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
    refs = {item["ref"] for item in result["results"] if item["kind"] == "episode"}
    assert result["scope"] == "current_discord_server_conversation"
    assert seed.id in refs
    assert related.id not in refs
