from typing import Any, cast

from echo_masque.conversation_planner import (
    ConversationAdmissionPlanner,
    ConversationPlannerCandidate,
    ConversationPlannerEnvelope,
    ConversationPlannerParticipant,
    rollout_decision,
)


class FakeGateway:
    def __init__(self, envelope: ConversationPlannerEnvelope) -> None:
        self.envelope = envelope

    def invoke(self, *_: object, **__: object) -> tuple[ConversationPlannerEnvelope, None]:
        return self.envelope, None


def candidates() -> tuple[ConversationPlannerCandidate, ...]:
    return (
        ConversationPlannerCandidate(
            deployment_ref="ann",
            display_name="Ann",
            contextual_score=4.2,
        ),
        ConversationPlannerCandidate(
            deployment_ref="ning",
            display_name="Ning",
            contextual_score=3.9,
        ),
    )


def test_planner_accepts_only_supplied_refs_and_simple_admission() -> None:
    envelope = ConversationPlannerEnvelope(
        schema_version="conversation-plan.v1",
        participants=(
            ConversationPlannerParticipant(
                deployment_ref="ann",
                admitted=True,
                guidance="The current discussion is relevant to you; respond naturally.",
            ),
            ConversationPlannerParticipant(deployment_ref="ning", admitted=False),
        ),
    )
    planner = ConversationAdmissionPlanner(cast(Any, FakeGateway(envelope)))
    result = planner.resolve(
        burst_id="burst-1",
        current_burst="大家怎么看这个剧情？",
        candidates=candidates(),
        maximum_participants=2,
    )
    assert result.accepted is True
    assert result.admitted_refs == ("ann",)
    assert "respond naturally" in result.guidance_by_ref()["ann"]


def test_planner_rejects_invented_or_missing_refs() -> None:
    envelope = ConversationPlannerEnvelope(
        schema_version="conversation-plan.v1",
        participants=(
            ConversationPlannerParticipant(deployment_ref="ann", admitted=True),
            ConversationPlannerParticipant(deployment_ref="invented", admitted=True),
        ),
    )
    planner = ConversationAdmissionPlanner(cast(Any, FakeGateway(envelope)))
    result = planner.resolve(
        burst_id="burst-1",
        current_burst="hello",
        candidates=candidates(),
        maximum_participants=2,
    )
    assert result.accepted is False
    assert result.reason == "candidate_ref_mismatch"


def test_planner_rejects_admission_above_runtime_limit() -> None:
    envelope = ConversationPlannerEnvelope(
        schema_version="conversation-plan.v1",
        participants=(
            ConversationPlannerParticipant(deployment_ref="ann", admitted=True),
            ConversationPlannerParticipant(deployment_ref="ning", admitted=True),
        ),
    )
    planner = ConversationAdmissionPlanner(cast(Any, FakeGateway(envelope)))
    result = planner.resolve(
        burst_id="burst-1",
        current_burst="hello",
        candidates=candidates(),
        maximum_participants=1,
    )
    assert result.accepted is False
    assert result.reason == "participant_limit_exceeded"


def test_rollout_bucket_is_stable_and_percent_bounded() -> None:
    first = rollout_decision(identity="burst-123", mode="active", percent=25)
    second = rollout_decision(identity="burst-123", mode="active", percent=25)
    assert first == second
    assert 0 <= first.bucket <= 99
    assert first.percent == 25

    shadow = rollout_decision(identity="burst-123", mode="shadow", percent=100)
    assert shadow.authoritative is False

    full = rollout_decision(identity="burst-123", mode="active", percent=100)
    assert full.authoritative is True
