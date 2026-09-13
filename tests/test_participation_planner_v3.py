from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationResolveCandidate,
    SmartParticipationResolveCandidateView,
    SmartParticipationResolveRequest,
)
from echo_masque.participation_planner_v3 import ParticipationPlannerV3
from echo_masque.persistence.conversation_structure_repository import ConversationSegmentView
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.semantic_participation import CharacterParticipationSemanticService


class _Semantic:
    enabled = True

    def __init__(self, relevance: float) -> None:
        self.relevance = relevance

    def score(self, **_: object) -> tuple[str, int, list[object]]:
        return (
            "test",
            1,
            [SimpleNamespace(profile_ready=True, relevance=self.relevance)],
        )


def _deployment() -> CharacterDeploymentRecord:
    return CharacterDeploymentRecord(
        id="deployment-1",
        owner_id="owner-1",
        character_card_id="card-1",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-1",
        workspace_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        thread_id="",
        thread_name="",
        participation_mode="smart",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="active",
    )


def _segment() -> ConversationSegmentView:
    return ConversationSegmentView(
        id="segment-1",
        burst_id="burst-1",
        message_ids=("message-1",),
        participant_ids=("user-1",),
        kind="discussion",
        summary="A discussion that may or may not be relevant to this character.",
        thread_id="thread-1",
        membership_relation="belongs_to",
        membership_confidence=1.0,
        confidence=1.0,
        source="test",
        created_at=datetime.now(UTC),
    )


def _candidate_view(*, final_score: float = 1.0) -> SmartParticipationResolveCandidateView:
    return SmartParticipationResolveCandidateView(
        deployment_id="deployment-1",
        character_card_id="card-1",
        eligible=True,
        deterministic_score=final_score,
        minimum_score=0.0,
        deterministic_signals={},
        raw_e5_relevance=0.0,
        profile_ready=True,
        semantic_points=0.0,
        final_evidence_score=final_score,
    )


def _payload(*, signals: dict[str, float] | None = None) -> SmartParticipationResolveRequest:
    return SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id="message-1",
        author_id="user-1",
        message="What do you think?",
        burst_id="burst-1",
        candidates=[
            SmartParticipationResolveCandidate(
                deployment_id="deployment-1",
                eligible=True,
                deterministic_score=1.0,
                minimum_score=0.0,
                signals=signals or {},
            )
        ],
    )


def _planner(relevance: float) -> ParticipationPlannerV3:
    return ParticipationPlannerV3(
        cast(CharacterParticipationSemanticService, _Semantic(relevance))
    )


def test_relationship_signal_does_not_promote_candidate_or_segment() -> None:
    planner = _planner(0.2)
    payload = _payload(signals={"relationship": 1.0})

    plan = planner.plan(
        payload=payload,
        deployments=(_deployment(),),
        candidate_views=(_candidate_view(),),
        segments=(_segment(),),
    )

    assert plan.speakers == ()
    assert plan.reason == "no_candidate_met_threshold"


def test_proactive_candidate_requires_strong_segment_relevance() -> None:
    plan = _planner(0.9).plan(
        payload=_payload(),
        deployments=(_deployment(),),
        candidate_views=(_candidate_view(),),
        segments=(_segment(),),
    )

    assert len(plan.speakers) == 1
    assert plan.speakers[0].segment_id == "segment-1"
    assert plan.speakers[0].conversation_thread_id == "thread-1"


def test_direct_conversation_pressure_can_select_current_segment_without_semantic_match() -> None:
    plan = _planner(0.0).plan(
        payload=_payload(signals={"name_match": 1.0}),
        deployments=(_deployment(),),
        candidate_views=(_candidate_view(),),
        segments=(_segment(),),
    )

    assert len(plan.speakers) == 1
    assert plan.speakers[0].segment_id == "segment-1"


def test_relationship_does_not_change_candidate_score() -> None:
    view = _candidate_view(final_score=0.5)
    without_relationship = SmartParticipationResolveCandidate(
        deployment_id="deployment-1",
        signals={},
    )
    with_relationship = SmartParticipationResolveCandidate(
        deployment_id="deployment-1",
        signals={"relationship": 1.0},
    )

    assert ParticipationPlannerV3._score(
        view,
        without_relationship,
    ) == ParticipationPlannerV3._score(
        view,
        with_relationship,
    )
