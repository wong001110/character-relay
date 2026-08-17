from __future__ import annotations

from echo_masque.conversation_topic_observed import ObservedConversationTopicMemoryService
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database


def test_topic_semantic_identity_evolves_with_summary_while_display_label_stays_stable() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationTopicRepository(database)
    topic = repository.create(
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        thread_id="",
        topic_label="Initial architecture question",
        summary="Initial architecture question",
        keywords_json='["architecture"]',
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json="[]",
        last_message_id="m1",
    )
    first = ObservedConversationTopicMemoryService._topic_semantic_text(topic)
    updated = repository.update_capsule(
        topic_id=topic.id,
        owner_id="owner-1",
        topic_label=topic.topic_label,
        summary="The conversation is now focused on SQL RAG episodic memory and recall.",
        keywords_json='["sql","rag","episodic","memory"]',
        open_loops_json="[]",
        pending_actions_json="[]",
        participants_json="[]",
        last_message_id="m2",
        increment_message_count=True,
    )
    second = ObservedConversationTopicMemoryService._topic_semantic_text(updated)

    assert updated.topic_label == "Initial architecture question"
    assert first != second
    assert "SQL RAG" in second
    assert "episodic" in second
