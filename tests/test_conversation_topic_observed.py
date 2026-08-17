from __future__ import annotations

from datetime import UTC, datetime

from echo_masque.conversation_topic_observed import ObservedConversationTopicMemoryService
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database


class _CountingEncoder:
    model_name = "test/topic-observed"
    dimension = 4

    def __init__(self) -> None:
        self.query_count = 0

    def embed_query(self, text: str) -> list[float]:
        self.query_count += 1
        normalized = text.casefold()
        if "weather" in normalized:
            return [0.0, 0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        normalized = text.casefold()
        if "switch" in normalized:
            return [0.0, 0.0, 0.0, 1.0]
        if "weather" in normalized:
            return [0.0, 0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0, 0.0]


def test_observed_topic_reuses_exact_continuity_decision_for_same_capsule_and_text() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationTopicRepository(database)
    encoder = _CountingEncoder()
    service = ObservedConversationTopicMemoryService(
        repository,
        encoder=encoder,
        semantic_enabled=True,
    )
    active = repository.create(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        topic_label="cat image generation",
        summary="cat image generation",
        keywords_json="[]",
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json="[]",
        last_message_id="m1",
        now=datetime(2026, 8, 18, 2, 0, tzinfo=UTC),
    )

    first = service.classify_continuity(text="continue cat image", active=active)
    second = service.classify_continuity(text="continue cat image", active=active)

    assert first is second
    assert encoder.query_count == 1


def test_observed_topic_cache_key_changes_with_capsule_version() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationTopicRepository(database)
    encoder = _CountingEncoder()
    service = ObservedConversationTopicMemoryService(
        repository,
        encoder=encoder,
        semantic_enabled=True,
    )
    active = repository.create(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        topic_label="cat image generation",
        summary="cat image generation",
        keywords_json="[]",
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json="[]",
        last_message_id="m1",
    )
    service.classify_continuity(text="continue cat image", active=active)
    updated = repository.update_capsule(
        topic_id=active.id,
        owner_id="owner-1",
        topic_label=active.topic_label,
        summary=active.summary,
        keywords_json=active.keywords_json,
        open_loops_json=active.open_loops_json,
        pending_actions_json=active.pending_actions_json,
        participants_json=active.participants_json,
        last_message_id="m2",
        increment_message_count=True,
    )
    service.classify_continuity(text="continue cat image", active=updated)

    assert encoder.query_count == 2
