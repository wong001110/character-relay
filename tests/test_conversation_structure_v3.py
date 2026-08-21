from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from echo_masque.conversation_segmentation import (
    ConversationJudgeResult,
    ConversationJudgeSegment,
    ConversationSegmentationService,
)

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)


def payload(
    messages: list[SmartParticipationBurstMessage], *, burst_id: str
) -> SmartParticipationResolveRequest:
    return SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        burst_id=burst_id,
        message=messages[-1].text if messages else "",
        message_id=messages[-1].message_id if messages else "",
        author_id=messages[-1].author_id if messages else "",
        reply_to_message_id=messages[-1].reply_to_message_id if messages else "",
        burst_messages=messages,
        candidates=[SmartParticipationResolveCandidate(deployment_id="deployment-1")],
    )


def repository() -> ConversationStructureRepository:
    database = Database("sqlite://")
    database.initialize()
    return ConversationStructureRepository(database)


def service(
    repo: ConversationStructureRepository,
    gateway: object | None = None,
) -> ConversationSegmentationService:
    return ConversationSegmentationService(
        repo,
        Settings(semantic_embedding_enabled=False),
        gateway,  # type: ignore[arg-type]
    )


class AmbiguousUtility:
    def __init__(self) -> None:
        self.thread_id = ""
        self.calls = 0
        self.runtime = SimpleNamespace(
            config=lambda: SimpleNamespace(
                utility_gateway=SimpleNamespace(
                    enabled=True,
                    members=(
                        SimpleNamespace(
                            enabled=True,
                            capabilities=("semantic_judge",),
                        ),
                    ),
                )
            )
        )

    def invoke(self, capability: str, *_: object, **__: object):
        assert capability == "semantic_judge"
        self.calls += 1
        return (
            ConversationJudgeResult(
                segments=(
                    ConversationJudgeSegment(
                        message_ids=("m2",),
                        kind="discussion",
                        summary="upload permissions status",
                        thread_action="attach",
                        thread_id=self.thread_id,
                        thread_evidence=True,
                        confidence=0.91,
                        reason="utility_continuity",
                    ),
                )
            ),
            None,
        )


def test_cross_burst_reply_is_structural_thread_authority() -> None:
    repo = repository()
    resolver = service(repo)
    now = datetime.now(UTC)
    first = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m1",
                    author_id="u1",
                    text="recording upload channel",
                )
            ],
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    thread_id = first.segments[0].thread_id
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
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )
    assert thread_id
    assert second.segments[0].thread_id == thread_id
    assert second.segments[0].membership_relation == "reaction_to"
    relations = repo.recent_relations(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
    )
    assert any(
        item.source_message_id == "m2"
        and item.relation_type == "REPLY_TO"
        and item.target_ref == "m1"
        for item in relations
    )


def test_thread_anchor_stays_stable_while_working_summary_moves_forward() -> None:
    repo = repository()
    resolver = service(repo)
    now = datetime.now(UTC)
    first = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m1",
                    author_id="u1",
                    text="recording and large file upload planning",
                )
            ],
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    thread_id = first.segments[0].thread_id
    before = repo.recent_threads(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        now=now,
    )[0]
    resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m2",
                    author_id="u1",
                    text="Google Drive access permissions are the remaining step",
                    reply_to_message_id="m1",
                )
            ],
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )
    after = next(
        item
        for item in repo.recent_threads(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="general",
            discord_thread_id="",
            now=now,
        )
        if item.id == thread_id
    )
    assert after.anchor_summary == before.anchor_summary
    assert "Google Drive" in after.working_summary
    assert after.working_summary != after.anchor_summary


def test_membership_reassignment_preserves_history() -> None:
    repo = repository()
    resolver = service(repo)
    now = datetime.now(UTC)
    first = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="a", author_id="u1", text="recording files"
                )
            ],
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    second = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="b", author_id="u2", text="database indexes"
                )
            ],
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )
    segment = second.segments[0]
    assert segment.thread_id != first.segments[0].thread_id
    repo.assign_membership(
        owner_id="owner-1",
        segment_id=segment.id,
        thread_id=first.segments[0].thread_id,
        relation="belongs_to",
        confidence=0.99,
        source="manual_correction",
        reason="later clarification connected the discussions",
        now=now,
    )
    history = repo.membership_history(owner_id="owner-1", segment_id=segment.id)
    assert len(history) == 2
    assert history[0].status == "superseded"
    assert history[1].status == "active"
    assert history[1].thread_id == first.segments[0].thread_id
    assert history[1].version == history[0].version + 1


def test_ambiguous_single_message_can_use_semantic_utility_judge() -> None:
    repo = repository()
    utility = AmbiguousUtility()
    resolver = service(repo, utility)
    now = datetime.now(UTC)
    first = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m1",
                    author_id="u1",
                    text="recording upload permissions",
                )
            ],
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    utility.thread_id = first.segments[0].thread_id
    second = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m2",
                    author_id="u1",
                    text="upload permissions status",
                )
            ],
            burst_id="b2",
        ),
        owner_id="owner-1",
        now=now,
    )
    assert utility.calls == 1
    assert second.utility_used is True
    assert second.segments[0].thread_id == utility.thread_id


def test_split_and_merge_keep_membership_revision_provenance() -> None:
    repo = repository()
    resolver = service(repo)
    now = datetime.now(UTC)
    result = resolver.resolve(
        payload=payload(
            [
                SmartParticipationBurstMessage(
                    message_id="m1",
                    author_id="u1",
                    text="recording files",
                ),
                SmartParticipationBurstMessage(
                    message_id="m2",
                    author_id="u1",
                    text="recording upload",
                    reply_to_message_id="m1",
                ),
            ],
            burst_id="b1",
        ),
        owner_id="owner-1",
        now=now,
    )
    original = result.segments[0]
    split = repo.split_thread(
        owner_id="owner-1",
        source_thread_id=original.thread_id,
        segment_ids=(original.id,),
        canonical_label="split recording discussion",
        anchor_summary="split recording discussion",
        reason="operator split",
        now=now,
    )
    split_membership = repo.current_membership(owner_id="owner-1", segment_id=original.id)
    assert split_membership is not None
    assert split_membership.thread_id == split.id
    moved = repo.merge_threads(
        owner_id="owner-1",
        source_thread_id=split.id,
        target_thread_id=original.thread_id,
        reason="operator merge",
        now=now,
    )
    assert moved == 1
    current = repo.current_membership(owner_id="owner-1", segment_id=original.id)
    assert current is not None
    assert current.thread_id == original.thread_id
    history = repo.membership_history(owner_id="owner-1", segment_id=original.id)
    assert len(history) == 3
    assert [item.version for item in history] == [1, 2, 3]
