from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.participation_admission_policy import resolve_admission_limit


def _burst(*texts: str) -> list[SmartParticipationBurstMessage]:
    return [
        SmartParticipationBurstMessage(
            message_id=f"m{index}",
            author_id=f"u{index}",
            text=text,
        )
        for index, text in enumerate(texts, start=1)
    ]


def _candidates(count: int) -> list[SmartParticipationResolveCandidate]:
    return [
        SmartParticipationResolveCandidate(deployment_id=f"d{index}")
        for index in range(1, count + 1)
    ]


def test_normal_conversation_keeps_small_soft_cap() -> None:
    decision = resolve_admission_limit(
        message="这个剧情感觉有点奇怪",
        burst_messages=[],
        eligible_candidate_count=8,
        requested_max=2,
    )

    assert decision.limit == 2
    assert decision.reason == "normal_conversation"
    assert decision.group_invitation is False


def test_active_burst_expands_soft_cap_without_becoming_unbounded() -> None:
    decision = resolve_admission_limit(
        message="",
        burst_messages=_burst(
            "我觉得这里逻辑不太对" * 20,
            "但前面的伏笔又能解释" * 20,
            "你们有没有注意到另外一个角色" * 20,
        ),
        eligible_candidate_count=9,
        requested_max=2,
    )

    assert decision.limit == 4
    assert decision.reason == "active_conversation"


def test_explicit_group_invitation_relaxes_soft_cap_to_all_available() -> None:
    decision = resolve_admission_limit(
        message="大家怎么看这段剧情？",
        burst_messages=[],
        eligible_candidate_count=7,
        requested_max=2,
    )

    assert decision.limit == 7
    assert decision.reason == "explicit_group_invitation"
    assert decision.group_invitation is True


def test_emergency_hard_cap_still_limits_group_invitation() -> None:
    decision = resolve_admission_limit(
        message="What do you all think?",
        burst_messages=[],
        eligible_candidate_count=24,
        requested_max=2,
    )

    assert decision.limit == 10
    assert decision.group_invitation is True


def test_request_contract_applies_dynamic_limit_before_runtime_resolution() -> None:
    request = SmartParticipationResolveRequest(
        connection_id="conn",
        message="你们都觉得谁最可疑？",
        max_participants=2,
        candidates=_candidates(6),
    )

    assert request.max_participants == 6
    assert request.admission_limit_reason == "explicit_group_invitation"
    assert request.admission_group_invitation is True


def test_request_contract_counts_only_eligible_candidates() -> None:
    candidates = _candidates(5)
    candidates[3].eligible = False
    candidates[4].eligible = False
    request = SmartParticipationResolveRequest(
        connection_id="conn",
        message="大家都说说",
        max_participants=2,
        candidates=candidates,
    )

    assert request.max_participants == 3


def test_request_contract_never_expands_above_emergency_cap() -> None:
    request = SmartParticipationResolveRequest(
        connection_id="conn",
        message="Everybody jump in on this one.",
        max_participants=10,
        candidates=_candidates(24),
    )

    assert request.max_participants == 10
    assert request.admission_limit_reason == "explicit_group_invitation"
