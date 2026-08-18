from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.conversation_segmentation import ConversationSegmentationService
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_segment_repository import ConversationSegmentRepository
from echo_masque.utility_gateway_contracts import UtilityGatewayUnavailable


class NoUtility:
    runtime = SimpleNamespace(
        config=lambda: SimpleNamespace(
            utility_gateway=SimpleNamespace(enabled=False, members=())
        )
    )

    def invoke(self, *args: object, **kwargs: object):
        raise UtilityGatewayUnavailable("disabled")


def payload(messages: list[SmartParticipationBurstMessage], *, burst_id: str = "burst-1"):
    return SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        burst_id=burst_id,
        message=messages[-1].text if messages else "",
        message_id=messages[-1].message_id if messages else "",
        author_id=messages[-1].author_id if messages else "",
        burst_messages=messages,
        candidates=[SmartParticipationResolveCandidate(deployment_id="deployment-1")],
    )


def service() -> ConversationSegmentationService:
    database = Database("sqlite://")
    database.initialize()
    settings = Settings(semantic_embedding_runtime_enabled=False)
    return ConversationSegmentationService(
        ConversationSegmentRepository(database),
        settings,
        NoUtility(),  # type: ignore[arg-type]
    )


def test_interleaved_reply_chains_become_multiple_segments_without_switch_churn() -> None:
    resolver = service()
    request = payload(
        [
            SmartParticipationBurstMessage(
                message_id="m1",
                author_id="u1",
                author_display_name="A",
                text="这个视频后面真的很好笑",
            ),
            SmartParticipationBurstMessage(
                message_id="m2",
                author_id="u2",
                author_display_name="B",
                text="确实",
                reply_to_message_id="m1",
            ),
            SmartParticipationBurstMessage(
                message_id="m3",
                author_id="u3",
                author_display_name="C",
                text="Character Relay 的 Topic 判断有结构问题",
            ),
            SmartParticipationBurstMessage(
                message_id="m4",
                author_id="u4",
                author_display_name="D",
                text="是不是 single active topic 导致的",
                reply_to_message_id="m3",
            ),
            SmartParticipationBurstMessage(
                message_id="m5",
                author_id="u1",
                author_display_name="A",
                text="2:30 那段最明显",
                reply_to_message_id="m1",
            ),
        ]
    )
    result = resolver.resolve(payload=request, owner_id="owner-1", now=datetime.now(UTC))
    assert len(result.segments) == 2
    grouped = {frozenset(item.message_ids) for item in result.segments}
    assert frozenset({"m1", "m2", "m5"}) in grouped
    assert frozenset({"m3", "m4"}) in grouped
    assert len({item.semantic_thread_id for item in result.segments}) == 2


def test_reaction_can_attach_without_becoming_thread_identity_evidence() -> None:
    resolver = service()
    first = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m1",
                    author_id="u1",
                    text="我们继续讨论 Character Relay 的 conversation segmentation",
                )
            ],
            burst_id="burst-a",
        ),
        owner_id="owner-1",
        now=datetime.now(UTC),
    )
    thread_id = first.segments[0].semantic_thread_id
    second = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m2",
                    author_id="u2",
                    text="哈哈",
                    reply_to_message_id="m1",
                )
            ],
            burst_id="burst-b",
        ),
        owner_id="owner-1",
        now=datetime.now(UTC),
    )
    assert second.segments[0].kind == "reaction"
    assert second.segments[0].thread_evidence is False
    # A reply to a message outside the current Burst cannot hard-link locally; it may remain
    # context-only and unassigned rather than corrupting an unrelated thread identity.
    assert second.segments[0].semantic_thread_id in {"", thread_id}


def test_multiple_new_subjects_do_not_force_prior_thread_into_cooling() -> None:
    resolver = service()
    now = datetime.now(UTC)
    first = resolver.resolve(
        payload=payload(
            [SmartParticipationBurstMessage(message_id="a", author_id="u1", text="讨论游戏角色设计")],
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    second = resolver.resolve(
        payload=payload(
            [SmartParticipationBurstMessage(message_id="b", author_id="u2", text="讨论 SQL RAG 架构")],
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )
    repo = resolver.repository
    threads = repo.recent_threads(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        now=now,
    )
    assert first.segments[0].semantic_thread_id != second.segments[0].semantic_thread_id
    assert len(threads) == 2
    assert all(item.status == "hot" for item in threads)
