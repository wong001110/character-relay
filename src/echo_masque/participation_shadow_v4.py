"""Pure Smart Participation V4 shadow scoring from Connector base evidence plus raw E5."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParticipationShadowCandidate:
    deployment_id: str
    eligible: bool
    deterministic_score: float
    minimum_score: float
    signals: dict[str, float]
    raw_e5_relevance: float
    profile_ready: bool


@dataclass(frozen=True, slots=True)
class ParticipationShadowScore:
    deployment_id: str
    semantic_points: float
    final_score: float
    selected: bool


@dataclass(frozen=True, slots=True)
class ParticipationShadowPlanItem:
    deployment_id: str
    turn_role: str
    reason: str


@dataclass(frozen=True, slots=True)
class ParticipationShadowResult:
    scores: tuple[ParticipationShadowScore, ...]
    plan: tuple[ParticipationShadowPlanItem, ...]


def semantic_participation_points(relevance: float, *, profile_ready: bool = True) -> float:
    """Mirror the Connector's bounded E5 signal: .75 -> 0 and .90 -> +6."""

    if not profile_ready:
        return 0.0
    bounded = min(1.0, max(0.0, (float(relevance) - 0.75) / 0.15))
    return round(bounded * 6.0, 3)


def _has_character_specific_reason(
    candidate: ParticipationShadowCandidate,
    semantic_points: float,
) -> bool:
    return (
        semantic_points > 0.0
        or candidate.signals.get("topic_match", 0.0) > 0.0
        or candidate.signals.get("keyword_match", 0.0) > 0.0
        or candidate.signals.get("trigger_phrase", 0.0) > 0.0
    )


def resolve_participation_shadow(
    candidates: list[ParticipationShadowCandidate],
    *,
    minimum_margin: float,
    max_participants: int,
) -> ParticipationShadowResult:
    """Build a non-authoritative speaker plan without changing Runtime eligibility."""

    bounded_margin = max(0.0, float(minimum_margin))
    bounded_participants = max(1, min(int(max_participants), 3))
    scored: list[tuple[ParticipationShadowCandidate, float, float]] = []
    for candidate in candidates:
        semantic_points = semantic_participation_points(
            candidate.raw_e5_relevance,
            profile_ready=candidate.profile_ready,
        )
        final_score = round(candidate.deterministic_score + semantic_points, 3)
        scored.append((candidate, semantic_points, final_score))

    scored.sort(
        key=lambda item: (
            not item[0].eligible,
            -item[2],
            item[0].deployment_id,
        )
    )
    top = next(
        (
            item
            for item in scored
            if item[0].eligible and item[2] >= item[0].minimum_score
        ),
        None,
    )
    selected_ids: list[str] = []
    if top is not None:
        selected_ids.append(top[0].deployment_id)
        for item in scored:
            if len(selected_ids) >= bounded_participants:
                break
            candidate, semantic_points, final_score = item
            if candidate.deployment_id == top[0].deployment_id:
                continue
            if not candidate.eligible or final_score < candidate.minimum_score:
                continue
            if not _has_character_specific_reason(candidate, semantic_points):
                continue
            if top[2] - final_score > bounded_margin:
                continue
            selected_ids.append(candidate.deployment_id)

    selected = set(selected_ids)
    score_views = tuple(
        ParticipationShadowScore(
            deployment_id=candidate.deployment_id,
            semantic_points=semantic_points,
            final_score=final_score,
            selected=candidate.deployment_id in selected,
        )
        for candidate, semantic_points, final_score in scored
    )
    plan = tuple(
        ParticipationShadowPlanItem(
            deployment_id=deployment_id,
            turn_role="primary" if index == 0 else "complement",
            reason="deterministic_e5_shadow",
        )
        for index, deployment_id in enumerate(selected_ids)
    )
    return ParticipationShadowResult(scores=score_views, plan=plan)


__all__ = [
    "ParticipationShadowCandidate",
    "ParticipationShadowPlanItem",
    "ParticipationShadowResult",
    "ParticipationShadowScore",
    "resolve_participation_shadow",
    "semantic_participation_points",
]
