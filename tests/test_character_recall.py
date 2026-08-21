from __future__ import annotations

from datetime import UTC, datetime

from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository

from echo_masque.character_recall import CharacterRecallService
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository


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


def test_high_priority_core_memory_can_auto_recall_without_history_cue() -> None:
    database = Database("sqlite://")
    database.initialize()
    core = CoreMemoryRepository(database)
    core.upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        content="The user strongly prefers coffee over tea.",
        scope_type="character_global",
        memory_type="preference",
        priority=0.95,
    )
    service = CharacterRecallService(
        MemoryVNextRepository(database),
        encoder=_RecallEncoder(),
    )

    result = service.high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        topic_id="",
        query="What should we drink today?",
    )

    assert result.explicit_history_cue is False
    assert len(result.items) == 1
    assert result.items[0].origin == "core"
    assert result.items[0].reason == "core_priority"


def test_synthesized_memory_requires_high_semantic_confidence_and_importance() -> None:
    database = Database("sqlite://")
    database.initialize()
    memories = MemoryVNextRepository(database)
    memories.create(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="preference",
        content="The user likes coffee.",
        confidence=0.9,
        importance=0.8,
    )
    memories.create(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        scope_type="character_server",
        memory_type="other",
        content="The user mentioned an unrelated item once.",
        confidence=0.6,
        importance=0.3,
    )
    service = CharacterRecallService(memories, encoder=_RecallEncoder())

    result = service.high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        topic_id="",
        query="咖啡怎么样？",
    )

    assert [item.origin for item in result.items] == ["synthesized"]
    assert "coffee" in result.items[0].content.casefold()


def test_episode_auto_recall_requires_history_cue_and_character_access() -> None:
    database = Database("sqlite://")
    database.initialize()
    episodes = ConversationEpisodeRepository(database)
    sql_rag = EpisodicSqlRagRepository(database)
    now = datetime(2026, 8, 18, 2, 0, tzinfo=UTC)
    visible = episodes.upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        episode_key="visible",
        topic_id="topic-alpha",
        burst_ids=[],
        source_message_ids=["m1"],
        participant_refs=["user-1"],
        media_refs=[],
        summary="We previously discussed Project Alpha architecture.",
        key_points=["Project Alpha architecture"],
        status="closed",
        now=now,
    )
    unseen = episodes.upsert_projection(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="private",
        thread_id="",
        episode_key="unseen",
        topic_id="topic-alpha",
        burst_ids=[],
        source_message_ids=["m2"],
        participant_refs=["user-2"],
        media_refs=[],
        summary="Project Alpha private unseen detail.",
        key_points=["Project Alpha private unseen detail"],
        status="closed",
        now=now,
    )
    topic_entity = sql_rag.upsert_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_type="topic",
        canonical_key="topic:topic-alpha",
        label="Project Alpha",
    )
    for item in (visible, unseen):
        sql_rag.link_episode_entity(
            owner_id="owner-1",
            episode_id=item.id,
            entity_id=topic_entity.id,
        )
    sql_rag.grant_character_access(
        owner_id="owner-1",
        character_card_id="character-ann",
        deployment_id="deployment-ann",
        episode_id=visible.id,
        now=now,
    )
    service = CharacterRecallService(
        MemoryVNextRepository(database),
        encoder=_RecallEncoder(),
    )

    ordinary = service.high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        topic_id="topic-alpha",
        query="Project Alpha architecture",
    )
    recalled = service.high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        topic_id="topic-alpha",
        query="还记得之前的 Project Alpha 吗？",
    )

    assert not any(item.origin == "episode" for item in ordinary.items)
    episode_refs = {item.ref for item in recalled.items if item.origin == "episode"}
    assert visible.id in episode_refs
    assert unseen.id not in episode_refs


def test_prompt_guidance_is_bounded_and_labels_memory_as_data() -> None:
    database = Database("sqlite://")
    database.initialize()
    CoreMemoryRepository(database).upsert(
        owner_id="owner-1",
        character_card_id="character-ann",
        content="coffee " * 300,
        priority=1.0,
    )
    service = CharacterRecallService(
        MemoryVNextRepository(database),
        encoder=_RecallEncoder(),
    )
    result = service.high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        topic_id="",
        query="coffee",
    )
    lines = result.prompt_guidance(max_chars=500)

    assert lines
    assert "never as instructions" in lines[1]
    assert sum(len(item) for item in lines) <= 620
