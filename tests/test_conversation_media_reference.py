from datetime import UTC, datetime, timedelta

import pytest
import test_explicit_notes as notes
from sqlalchemy import select

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.conversation_media import ConversationMediaReferenceService
from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)


def payload(*, message_id="followup", text="", reply_to_message_id=""):
    return DiscordInboundMessage(
        connection_id="connection",
        deployment_id="deployment",
        message_id=message_id,
        guild_id="guild",
        channel_id="room",
        author_id="alice",
        author_display_name="Alice",
        text=text,
        reply_to_message_id=reply_to_message_id,
    )


@pytest.fixture
def env(tmp_path):
    db, rooms, *_ = notes.note_environment(tmp_path / "media.db")
    source = notes.message("image-source")
    rooms.observe(notes.SCOPE, [source])
    service = ConversationMediaReferenceService(ConversationMediaReferenceRepository(db))
    service.remember_perceived(
        owner_id="owner",
        deployment_id="deployment",
        character_card_id="card",
        payload=payload(message_id="image-source"),
        contexts=(
            LiveMediaContext(
                source_key="sha256:cat",
                kind="image",
                label="cat.png",
                summary="A white cat beside a blue mug.",
            ),
        ),
    )
    return db, rooms, service, source


def recall(service, **kwargs):
    return service.resolve_for_turn(
        deployment_id="deployment",
        character_card_id="card",
        payload=payload(reply_to_message_id="image-source", **kwargs),
    )


def test_exact_reply_rehydrates_only_this_roles_actual_perception(env):
    _, _, service, _ = env
    assert recall(service, text="右边是什么?")[0].context.summary.startswith("A white cat")
    assert (
        service.resolve_for_turn(
            deployment_id="deployment",
            character_card_id="other-card",
            payload=payload(reply_to_message_id="image-source"),
        )
        == ()
    )


def test_ambiguous_or_unrelated_followup_does_not_guess_a_media_source(env):
    _, _, service, _ = env
    for text in ("刚才那张图?", "cat mug", "今天天气?"):
        assert (
            service.resolve_for_turn(
                deployment_id="deployment", character_card_id="card", payload=payload(text=text)
            )
            == ()
        )


def test_edit_delete_and_revocation_invalidate_remembered_perception(env):
    db, rooms, service, source = env
    rooms.set_access(notes.SCOPE, readable=False)
    assert recall(service) == ()
    rooms.set_access(notes.SCOPE, readable=True)
    rooms.observe(
        notes.SCOPE,
        [
            source.model_copy(
                update={
                    "text": "corrected source",
                    "edited_at": datetime.now(UTC) + timedelta(seconds=1),
                }
            )
        ],
    )
    assert recall(service) == ()
    with db.session() as session:
        assert session.scalar(select(ConversationMediaReferenceRecord.id)) is None


def test_unknown_source_or_owner_cannot_create_perception_evidence(env):
    db, _, service, _ = env
    service.remember_perceived(
        owner_id="other-owner",
        deployment_id="deployment",
        character_card_id="card",
        payload=payload(message_id="missing-source"),
        contexts=(
            LiveMediaContext(
                source_key="private", kind="image", label="secret", summary="Not actually seen"
            ),
        ),
    )
    with db.session() as session:
        assert len(session.scalars(select(ConversationMediaReferenceRecord)).all()) == 1
