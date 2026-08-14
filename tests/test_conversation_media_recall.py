from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.api.connector_schemas import (
    DiscordContextMessage,
    DiscordInboundMessage,
)
from echo_masque.conversation_media import (
    ConversationMediaMemory,
    ConversationMediaReferenceService,
)
from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)


class MatchingMediaEncoder:
    model_name = "fake-media"
    dimension = 2

    def embed_query(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]


def _service() -> tuple[
    ConversationMediaReferenceRepository,
    ConversationMediaReferenceService,
]:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationMediaReferenceRepository(database)
    service = ConversationMediaReferenceService(
        repository,
        semantic_encoder=MatchingMediaEncoder(),
        semantic_enabled=True,
    )
    return repository, service


def _context(source_key: str = "image:storage") -> LiveMediaContext:
    return LiveMediaContext(
        source_key=source_key,
        kind="image",
        label="storage screenshot",
        summary="A game storage screen with a full 30/30 storage device.",
        visible_text="寄物装置 容量: 30/30 今日可取用次数: 5/5 UID: 800478718",
        notable_details=(
            "The storage device is full.",
            "The inventory contains many materials.",
        ),
    )


def _remember(
    repository: ConversationMediaReferenceRepository,
    *,
    when: datetime,
    message_id: str = "media-1",
) -> None:
    repository.remember(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="character-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        message_id=message_id,
        context=_context(),
        now=when,
    )


def _payload(
    text: str,
    *,
    message_id: str = "trigger-1",
    recent_messages: list[DiscordContextMessage] | None = None,
    reply_to_message_id: str | None = None,
) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id=message_id,
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="human-1",
        author_display_name="Member",
        text=text,
        recent_messages=recent_messages or [],
        reply_to_message_id=reply_to_message_id or "",
    )


def test_low_information_trigger_does_not_recall_media_from_previous_link() -> None:
    repository, service = _service()
    _remember(repository, when=datetime.now(UTC) - timedelta(minutes=5))
    previous = DiscordContextMessage(
        message_id="previous-1",
        author_id="human-1",
        author_display_name="Member",
        text="【视频】 https://example.test/watch/123",
        is_bot=False,
    )

    memories = service.resolve_for_turn(
        deployment_id="deployment-1",
        character_card_id="character-1",
        payload=_payload("安", recent_messages=[previous]),
    )

    assert memories == ()


def test_automatic_semantic_recall_rejects_old_unexpired_media() -> None:
    repository, service = _service()
    _remember(repository, when=datetime.now(UTC) - timedelta(days=3))

    memories = service.resolve_for_turn(
        deployment_id="deployment-1",
        character_card_id="character-1",
        payload=_payload("这个游戏仓库看起来已经装满了"),
    )

    assert memories == ()


def test_explicit_media_reference_can_recall_older_media() -> None:
    repository, service = _service()
    _remember(repository, when=datetime.now(UTC) - timedelta(days=3))

    memories = service.resolve_for_turn(
        deployment_id="deployment-1",
        character_card_id="character-1",
        payload=_payload("之前那张图的容量是多少？"),
    )

    assert len(memories) == 1
    assert memories[0].message_id == "media-1"


def test_reply_to_media_bypasses_automatic_age_gate() -> None:
    repository, service = _service()
    _remember(repository, when=datetime.now(UTC) - timedelta(days=3))

    memories = service.resolve_for_turn(
        deployment_id="deployment-1",
        character_card_id="character-1",
        payload=_payload("安", reply_to_message_id="media-1"),
    )

    assert len(memories) == 1
    assert memories[0].message_id == "media-1"


def test_guidance_defaults_to_single_summary_without_duplicate_details_or_ocr() -> None:
    memory = ConversationMediaMemory(
        message_id="media-1",
        context=_context(),
        recall_query="你觉得这个怎么样？",
    )

    guidance = "\n".join(ConversationMediaReferenceService.guidance((memory,)))

    assert "Summary:" in guidance
    assert "Relevant readable excerpt:" not in guidance
    assert "Notable details:" not in guidance
    assert "UID: 800478718" not in guidance


def test_guidance_lazily_includes_readable_text_for_text_specific_followup() -> None:
    memory = ConversationMediaMemory(
        message_id="media-1",
        context=_context(),
        recall_query="那张图的容量是多少？",
    )

    guidance = "\n".join(ConversationMediaReferenceService.guidance((memory,)))

    assert "Summary:" in guidance
    assert "Relevant readable excerpt:" in guidance
    assert "容量: 30/30" in guidance
    assert "Notable details:" not in guidance
