from __future__ import annotations

from sqlalchemy import select

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.media_continuation import SkippedMediaContinuationService
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.conversation_media_repository import ConversationMediaReferenceRepository


class _MediaContinuationEncoder:
    model_name = "test/media-continuation-e5"
    dimension = 2

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if (
            "previously chose not to inspect" in normalized
            or "看看" in text
            or "看一下" in text
            or "inspect the previous" in normalized
        ):
            return [1.0, 0.0]
        return [0.0, 1.0]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passage(self, text: str) -> list[float]:
        return self._vector(text)


def _service() -> tuple[
    Database,
    ConversationMediaReferenceRepository,
    SkippedMediaContinuationService,
]:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationMediaReferenceRepository(database)
    service = SkippedMediaContinuationService(
        repository,
        encoder=_MediaContinuationEncoder(),
        semantic_enabled=True,
    )
    return database, repository, service


def _payload(text: str, *, message_id: str) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id=message_id,
        guild_id="guild-a",
        guild_name="Guild",
        channel_id="general",
        channel_name="general",
        category_id="",
        thread_id="",
        thread_name="",
        author_id="user-1",
        author_display_name="Juen",
        text=text,
        mentioned_bot=True,
        smart_candidate=True,
    )


def test_skipped_media_persists_source_without_perception() -> None:
    database, _, service = _service()
    original = _payload(
        "看看这个 https://www.bilibili.com/video/BV1test",
        message_id="media-1",
    )

    stored = service.remember_skipped(
        owner_id="owner-1",
        deployment_id="deployment-ann",
        character_card_id="card-ann",
        payload=original,
        topic_id="topic-1",
    )

    assert len(stored) == 1
    assert stored[0].message_id == "media-1"
    assert stored[0].source_uri == "https://www.bilibili.com/video/BV1test"
    with database.session() as session:
        record = session.scalar(select(ConversationMediaReferenceRecord))
        assert record is not None
        assert record.context_json == ""
        assert record.source_key.startswith("skipped-topic:topic-1:")


def test_same_topic_semantic_reconsider_restores_skipped_source() -> None:
    _, _, service = _service()
    service.remember_skipped(
        owner_id="owner-1",
        deployment_id="deployment-ann",
        character_card_id="card-ann",
        payload=_payload(
            "看看这个 https://www.bilibili.com/video/BV1test",
            message_id="media-1",
        ),
        topic_id="topic-1",
    )

    reference = service.resolve_for_turn(
        deployment_id="deployment-ann",
        character_card_id="card-ann",
        payload=_payload("你还是看看刚才那个视频吧", message_id="follow-up-1"),
        topic_id="topic-1",
    )

    assert reference is not None
    assert reference.message_id == "media-1"
    rebuilt = service.payload_for_reference(
        _payload("你还是看看刚才那个视频吧", message_id="follow-up-1"),
        reference,
    )
    assert rebuilt.message_id == "media-1"
    assert rebuilt.text == "https://www.bilibili.com/video/BV1test"


def test_skipped_media_does_not_cross_topic_or_follow_unrelated_turn() -> None:
    _, _, service = _service()
    service.remember_skipped(
        owner_id="owner-1",
        deployment_id="deployment-ann",
        character_card_id="card-ann",
        payload=_payload(
            "看看这个 https://www.bilibili.com/video/BV1test",
            message_id="media-1",
        ),
        topic_id="topic-1",
    )

    wrong_topic = service.resolve_for_turn(
        deployment_id="deployment-ann",
        character_card_id="card-ann",
        payload=_payload("你还是看看刚才那个视频吧", message_id="follow-up-1"),
        topic_id="topic-2",
    )
    unrelated = service.resolve_for_turn(
        deployment_id="deployment-ann",
        character_card_id="card-ann",
        payload=_payload("明天天气怎么样", message_id="follow-up-2"),
        topic_id="topic-1",
    )

    assert wrong_topic is None
    assert unrelated is None


def test_successful_reconsider_can_remove_skipped_reference() -> None:
    database, _, service = _service()
    stored = service.remember_skipped(
        owner_id="owner-1",
        deployment_id="deployment-ann",
        character_card_id="card-ann",
        payload=_payload(
            "看看这个 https://www.bilibili.com/video/BV1test",
            message_id="media-1",
        ),
        topic_id="topic-1",
    )
    assert stored

    service.forget(stored[0])

    with database.session() as session:
        assert session.scalar(select(ConversationMediaReferenceRecord)) is None
