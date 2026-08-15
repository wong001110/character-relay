from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.api.connector_schemas import (
    DiscordEmbedContent,
    DiscordInboundMessage,
)
from echo_masque.conversation_topic import ConversationTopicMemoryService
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database


def _payload(
    text: str,
    *,
    message_id: str,
    embeds: list[DiscordEmbedContent] | None = None,
) -> DiscordInboundMessage:
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
        embeds=embeds or [],
        mentioned_bot=True,
        smart_candidate=True,
    )


def _service() -> tuple[ConversationTopicMemoryService, ConversationTopicRepository]:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationTopicRepository(database)
    return ConversationTopicMemoryService(repository, semantic_enabled=False), repository


def test_url_only_message_does_not_create_topic_before_content_is_inspected() -> None:
    service, repository = _service()

    result = service.observe_turn(
        owner_id="owner-1",
        payload=_payload(
            "https://www.bilibili.com/video/BV1example",
            message_id="m1",
            embeds=[
                DiscordEmbedContent(
                    embed_type="video",
                    url="https://www.bilibili.com/video/BV1example",
                    title="A preview title must not become topic identity",
                    description="Discord preview metadata is not inspected page content.",
                    provider_name="Bilibili",
                )
            ],
        ),
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert result is None
    assert (
        repository.active_for_scope(
            owner_id="owner-1",
            platform="discord",
            connection_id="connection-1",
            guild_id="guild-a",
            channel_id="general",
            thread_id="",
        )
        is None
    )


def test_url_only_message_does_not_mutate_or_refresh_existing_topic() -> None:
    service, _ = _service()
    started = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("RAG and LLM Wiki architecture", message_id="m1"),
        now=started,
    )
    assert first is not None

    link = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("https://www.bilibili.com/video/BV1different", message_id="m2"),
        now=started + timedelta(days=2),
    )

    assert link is not None
    assert link.id == first.id
    assert link.topic_label == first.topic_label
    assert link.summary == first.summary
    assert link.keywords == first.keywords
    assert link.message_count == first.message_count
    assert link.last_message_id == first.last_message_id
    assert link.last_active_at == first.last_active_at


def test_link_with_explicit_caption_uses_caption_not_url_as_topic_evidence() -> None:
    service, _ = _service()
    started = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    first = service.observe_turn(
        owner_id="owner-1",
        payload=_payload("RAG and LLM Wiki architecture", message_id="m1"),
        now=started,
    )
    assert first is not None

    zzz = service.observe_turn(
        owner_id="owner-1",
        payload=_payload(
            "https://www.bilibili.com/video/BV1zzz 绝区零这段剧情谁是反派",
            message_id="m2",
        ),
        now=started + timedelta(minutes=2),
    )

    assert zzz is not None
    assert zzz.id != first.id
    assert zzz.topic_label == "绝区零这段剧情谁是反派"
    assert "bilibili" not in " ".join(zzz.keywords).casefold()
    assert "http" not in zzz.summary.casefold()
