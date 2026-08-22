from __future__ import annotations

from datetime import UTC, datetime

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)


def _payload(
    message: SmartParticipationBurstMessage,
    *,
    burst_id: str,
) -> SmartParticipationResolveRequest:
    return SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        burst_id=burst_id,
        message=message.text,
        message_id=message.message_id,
        author_id=message.author_id,
        reply_to_message_id=message.reply_to_message_id,
        burst_messages=[message],
        candidates=[SmartParticipationResolveCandidate(deployment_id="deployment-1")],
    )


def _resolver() -> ConversationStructureResolver:
    database = Database("sqlite://")
    database.initialize()
    return ConversationStructureResolver(
        ConversationStructureRepository(database),
        Settings(semantic_embedding_enabled=False),
        None,
    )


def test_semantic_similarity_alone_cannot_attach_thread() -> None:
    resolver = _resolver()
    now = datetime.now(UTC)
    first = resolver.resolve(
        payload=_payload(
            SmartParticipationBurstMessage(
                message_id="m1",
                author_id="u1",
                text="recording upload permissions status",
            ),
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    assert first.segments[0].thread_id

    second = resolver.resolve(
        payload=_payload(
            SmartParticipationBurstMessage(
                message_id="m2",
                author_id="u2",
                text="recording upload permissions status",
            ),
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )

    assert second.utility_used is False
    assert second.segments[0].thread_id == ""
    assert second.segments[0].membership_relation == "unresolved"


def test_immediate_same_participant_continuity_can_attach_with_semantic_support() -> None:
    resolver = _resolver()
    now = datetime.now(UTC)
    first = resolver.resolve(
        payload=_payload(
            SmartParticipationBurstMessage(
                message_id="m1",
                author_id="u1",
                text="recording upload permissions status",
            ),
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    thread_id = first.segments[0].thread_id

    second = resolver.resolve(
        payload=_payload(
            SmartParticipationBurstMessage(
                message_id="m2",
                author_id="u1",
                text="recording upload permissions are still pending",
            ),
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )

    assert second.segments[0].thread_id == thread_id
    assert second.segments[0].membership_relation == "belongs_to"


def test_explicit_reply_remains_stronger_than_participant_or_semantic_candidates() -> None:
    resolver = _resolver()
    now = datetime.now(UTC)
    recording = resolver.resolve(
        payload=_payload(
            SmartParticipationBurstMessage(
                message_id="recording-1",
                author_id="u1",
                text="recording upload channel",
            ),
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    other = resolver.resolve(
        payload=_payload(
            SmartParticipationBurstMessage(
                message_id="other-1",
                author_id="u1",
                text="database migration indexes",
            ),
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )
    assert other.segments[0].thread_id != recording.segments[0].thread_id

    reply = resolver.resolve(
        payload=_payload(
            SmartParticipationBurstMessage(
                message_id="reply-1",
                author_id="u1",
                text="this one",
                reply_to_message_id="recording-1",
            ),
            burst_id="b3",
        ),
        owner_id="owner-1",
        now=now,
    )

    assert reply.segments[0].thread_id == recording.segments[0].thread_id
    assert reply.segments[0].membership_relation == "belongs_to"
