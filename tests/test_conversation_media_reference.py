from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.conversation_media import ConversationMediaReferenceService
from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)


def payload(
    *,
    message_id: str,
    text: str = "",
    reply_to_message_id: str = "",
) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="conn-1",
        deployment_id="dep-1",
        message_id=message_id,
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Member",
        text=text,
        reply_to_message_id=reply_to_message_id,
    )


def test_perceived_media_can_be_rehydrated_by_reply_and_deictic_follow_up() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationMediaReferenceRepository(database)
    service = ConversationMediaReferenceService(repository)
    source = payload(message_id="message-image")
    context = LiveMediaContext(
        source_key="sha256:abc",
        kind="image",
        label="cat.png",
        summary="A white cat is sitting beside a blue mug.",
        notable_details=("Blue mug on the right",),
    )

    service.remember_perceived(
        owner_id="owner-1",
        deployment_id="dep-1",
        character_card_id="card-ann",
        payload=source,
        contexts=(context,),
    )

    explicit = service.resolve_for_turn(
        deployment_id="dep-1",
        character_card_id="card-ann",
        payload=payload(
            message_id="message-follow-up",
            text="右边那个是什么?",
            reply_to_message_id="message-image",
        ),
    )
    assert len(explicit) == 1
    assert explicit[0].context.summary.startswith("A white cat")

    recent = service.resolve_for_turn(
        deployment_id="dep-1",
        character_card_id="card-ann",
        payload=payload(message_id="message-recent", text="刚才那张图右边是什么?"),
    )
    assert len(recent) == 1
    assert recent[0].message_id == "message-image"


def test_conversation_media_does_not_cross_character_epistemic_scope() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationMediaReferenceRepository(database)
    service = ConversationMediaReferenceService(repository)
    context = LiveMediaContext(
        source_key="sha256:secret-image",
        kind="image",
        label="secret.png",
        summary="Only Ann inspected this image.",
    )
    service.remember_perceived(
        owner_id="owner-1",
        deployment_id="dep-1",
        character_card_id="card-ann",
        payload=payload(message_id="message-image"),
        contexts=(context,),
    )

    ning = service.resolve_for_turn(
        deployment_id="dep-1",
        character_card_id="card-ning",
        payload=payload(
            message_id="message-reply",
            text="这张呢?",
            reply_to_message_id="message-image",
        ),
    )
    assert ning == ()


def test_unrelated_follow_up_does_not_implicitly_pull_recent_media() -> None:
    database = Database("sqlite://")
    database.initialize()
    repository = ConversationMediaReferenceRepository(database)
    service = ConversationMediaReferenceService(repository)
    service.remember_perceived(
        owner_id="owner-1",
        deployment_id="dep-1",
        character_card_id="card-ann",
        payload=payload(message_id="message-image"),
        contexts=(
            LiveMediaContext(
                source_key="sha256:abc",
                kind="image",
                label="cat.png",
                summary="A cat.",
            ),
        ),
    )

    result = service.resolve_for_turn(
        deployment_id="dep-1",
        character_card_id="card-ann",
        payload=payload(message_id="message-other", text="今天天气怎么样?"),
    )
    assert result == ()
