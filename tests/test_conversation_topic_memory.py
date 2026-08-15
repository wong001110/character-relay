from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.conversation_topic import ConversationTopicMemoryService
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database


class _TopicEncoder:
    model_name = "test/topic-e5"
    dimension = 4

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if (
            "retry the previous" in normalized
            or "continue the same previous" in normalized
            or "cancel, stop, abandon" in normalized
            or "clarify, correct" in normalized
            or "再试试" in normalized
            or "再来一次" in normalized
        ):
            return [0.0, 1.0, 0.0, 0.0]
        if "start a new unrelated" in normalized or "换个话题" in normalized:
            return [0.0, 0.0, 0.0, 1.0]
        if (
            "rag" in normalized
            or "llm wiki" in normalized
            or "cat" in normalized
            or "猫" in normalized
            or "image" in normalized
        ):
            return [1.0, 0.0, 0.0, 0.0]
        if (
            "weather" in normalized
            or "天气" in normalized
            or "绝区零" in normalized
            or "反派" in normalized
        ):
            return [0.0, 0.0, 1.0, 0.0]
        return [0.25, 0.25, 0.25, 0.25]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passage(self, text: str) -> list[float]:
        return self._vector(text)


def _service() -> ConversationTopicMemoryService:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationTopicRepository(database)
    return ConversationTopicMemoryService(
        repository,
        encoder=_TopicEncoder(),
        semantic_enabled=True,
    )


def _payload(
    text: str,
    *,
    message_id: str,
    channel_id: str = "general",
    thread_id: str = "",
    author_id: str = "user-1",
) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id=message_id,
        guild_id="guild-a",
        guild_name="Guild",
        channel_id=channel_id,
        channel_name=channel_id,
        category_id="",
        thread_id=thread_id,
        thread_name="",
        author_id=author_id,
        author_display_name="Juen",
        text=text,
        mentioned_bot=True,
        smart_candidate=True,
    )


def test_topic_observation_is_idempotent_for_same_discord_message() -> None:
    service = _service()
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("generate a cat image", message_id="m1"),
    )
    repeated = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("generate a cat image", message_id="m1"),
    )

    assert first is not None
    assert repeated is not None
    assert repeated.id == first.id
    assert repeated.message_count == 1
    assert repeated.capsule_version == first.capsule_version


def test_semantic_retry_phrase_continues_active_topic_without_regex() -> None:
    service = _service()
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("generate a cat image", message_id="m1"),
        now=now,
    )
    retry = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("你再试试", message_id="m2"),
        now=now + timedelta(minutes=5),
    )

    assert first is not None
    assert retry is not None
    assert retry.id == first.id
    assert retry.message_count == 2
    assert "你再试试" in retry.summary


def test_stale_contextual_continuation_does_not_revive_old_topic() -> None:
    service = _service()
    started = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("RAG and LLM Wiki architecture", message_id="m1"),
        now=started,
    )
    retry = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("你再试试", message_id="m2"),
        now=started + timedelta(days=2),
    )

    assert first is not None
    assert retry is not None
    assert retry.id != first.id
    previous = service.repository.get(first.id, "owner-1")
    assert previous is not None
    assert previous.status == "cooling"


def test_stale_topic_can_continue_with_explicit_identity_evidence() -> None:
    service = _service()
    started = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("RAG and LLM Wiki architecture", message_id="m1"),
        now=started,
    )
    resumed = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("Back to the RAG and LLM Wiki architecture", message_id="m2"),
        now=started + timedelta(days=2),
    )

    assert first is not None
    assert resumed is not None
    assert resumed.id == first.id
    assert resumed.message_count == 2


def test_topic_identity_does_not_include_mutable_summary_or_keywords() -> None:
    service = _service()
    topic = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("RAG and LLM Wiki architecture", message_id="m1"),
    )
    assert topic is not None

    record = service.repository.get(topic.id, "owner-1")
    assert record is not None
    service.repository.update_capsule(
        topic_id=record.id,
        owner_id="owner-1",
        topic_label=record.topic_label,
        summary="Juen: 绝区零剧情里谁是反派？",
        keywords_json='["绝区零", "剧情", "反派"]',
        open_loops_json=record.open_loops_json,
        pending_actions_json=record.pending_actions_json,
        participants_json=record.participants_json,
        last_message_id=record.last_message_id,
        increment_message_count=False,
    )
    poisoned = service.repository.get(topic.id, "owner-1")
    assert poisoned is not None

    semantic_text = service._topic_semantic_text(poisoned)
    assert semantic_text == "Topic identity: RAG and LLM Wiki architecture"
    assert "绝区零" not in semantic_text
    assert "反派" not in semantic_text


def test_old_rag_topic_does_not_absorb_new_zzz_discussion() -> None:
    service = _service()
    started = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("RAG and LLM Wiki architecture", message_id="m1"),
        now=started,
    )
    zzz = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("绝区零这段剧情谁是反派？", message_id="m2"),
        now=started + timedelta(days=2),
    )

    assert first is not None
    assert zzz is not None
    assert zzz.id != first.id
    assert "绝区零" in zzz.topic_label
    previous = service.repository.get(first.id, "owner-1")
    assert previous is not None
    assert previous.status == "cooling"


def test_unrelated_semantic_message_starts_new_topic_and_cools_previous() -> None:
    service = _service()
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("generate a cat image", message_id="m1"),
    )
    second = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("what is tomorrow's weather", message_id="m2"),
    )

    assert first is not None
    assert second is not None
    assert second.id != first.id
    previous = service.repository.get(first.id, "owner-1")
    assert previous is not None
    assert previous.status == "cooling"


def test_topic_scope_is_isolated_by_channel_and_thread() -> None:
    service = _service()
    channel_topic = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("generate a cat image", message_id="m1", channel_id="general"),
    )
    thread_topic = service.observe_turn(
        owner_id="owner-1",
        payload=_payload(
            "generate a cat image",
            message_id="m2",
            channel_id="general",
            thread_id="thread-1",
        ),
    )

    assert channel_topic is not None
    assert thread_topic is not None
    assert channel_topic.id != thread_topic.id


def test_pending_action_is_structured_and_actor_scoped() -> None:
    service = _service()
    topic = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("generate a cat image", message_id="m1"),
    )
    assert topic is not None
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

    action = service.record_pending_action(
        topic_id=topic.id,
        owner_id="owner-1",
        tool_id="image.generate",
        state="blocked_unavailable",
        requested_by_user_id="user-1",
        target_character_card_id="card-ann",
        deployment_id="deployment-ann",
        source_message_id="m1",
        intent_summary="generate a cat image",
        now=now,
        ttl=timedelta(hours=2),
    )

    refreshed_record = service.repository.get(topic.id, "owner-1")
    assert refreshed_record is not None
    refreshed = service.snapshot(refreshed_record)
    assert refreshed.pending_actions == [action]
    assert action.model_dump().keys() == {
        "tool_id",
        "state",
        "requested_by_user_id",
        "target_character_card_id",
        "deployment_id",
        "source_message_id",
        "intent_summary",
        "created_at",
        "updated_at",
        "expires_at",
    }

    eligible = service.pending_for_actor(
        snapshot=refreshed,
        requested_by_user_id="user-1",
        target_character_card_id="card-ann",
        deployment_id="deployment-ann",
        now=now + timedelta(minutes=10),
    )
    wrong_user = service.pending_for_actor(
        snapshot=refreshed,
        requested_by_user_id="user-2",
        target_character_card_id="card-ann",
        deployment_id="deployment-ann",
        now=now + timedelta(minutes=10),
    )

    assert eligible == (action,)
    assert wrong_user == ()
