"""Pure, fail-closed decisions for Knowledge Fabric query planning and fusion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

QUERY_MODE_OVERVIEW: Final = "overview"
QUERY_MODE_EXACT: Final = "exact"
QUERY_MODE_RELATIONAL: Final = "relational"
QUERY_MODE_CURRENT: Final = "current"
QUERY_MODE_CODE: Final = "code"
QUERY_MODES: Final = frozenset(
    {
        QUERY_MODE_OVERVIEW,
        QUERY_MODE_EXACT,
        QUERY_MODE_RELATIONAL,
        QUERY_MODE_CURRENT,
        QUERY_MODE_CODE,
    }
)

FRESHNESS_NOT_REQUESTED: Final = "not_requested"
FRESHNESS_INSUFFICIENT: Final = "insufficient"


def query_mode_is_valid(mode: str) -> bool:
    """Reject unknown modes rather than silently routing them to a broad search."""

    return mode in QUERY_MODES


def query_requires_source_aligned_evidence(mode: str) -> bool:
    """Exact answers must remain anchored to raw/source-aligned Evidence Units."""

    return mode == QUERY_MODE_EXACT


def query_requires_current_evidence(mode: str) -> bool:
    """Only the explicit current mode requires a freshness sufficiency decision."""

    return mode == QUERY_MODE_CURRENT


def candidate_may_enter_ranking(*, corpus_id: str, authorized_corpus_ids: frozenset[str]) -> bool:
    """Authorization is a pre-ranking admission gate, not a post-filter."""

    return bool(corpus_id and corpus_id in authorized_corpus_ids)


def interpretation_is_available_as_of(
    *,
    valid_from: datetime | None,
    valid_to: datetime | None,
    as_of: datetime | None,
) -> bool:
    """Use a documented half-open validity interval for corpus interpretations."""

    if as_of is None:
        return True
    comparable_as_of = _as_utc(as_of)
    if valid_from is not None and comparable_as_of < _as_utc(valid_from):
        return False
    return valid_to is None or comparable_as_of < _as_utc(valid_to)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns UTC persistence values without tzinfo; compare them as UTC."""

    return (
        value.replace(tzinfo=UTC)
        if value.tzinfo is None
        else datetime.fromtimestamp(value.timestamp(), tz=UTC)
    )


def freshness_status_for_mode(mode: str) -> str:
    """Report the deliberate Phase 5 freshness-policy gap without inventing a threshold."""

    if query_requires_current_evidence(mode):
        return FRESHNESS_INSUFFICIENT
    return FRESHNESS_NOT_REQUESTED


def stable_reciprocal_rank_fusion(channel_rankings: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    """Fuse bounded channel rankings deterministically while keeping one Evidence identity."""

    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for ranking in channel_rankings:
        for rank, candidate_id in enumerate(ranking, start=1):
            first_seen.setdefault(candidate_id, len(first_seen))
            scores[candidate_id] = scores.get(candidate_id, 0.0) + 1.0 / rank
    return tuple(
        sorted(
            scores,
            key=lambda candidate_id: (-scores[candidate_id], first_seen[candidate_id]),
        )
    )


__all__ = [
    "FRESHNESS_INSUFFICIENT",
    "FRESHNESS_NOT_REQUESTED",
    "QUERY_MODES",
    "QUERY_MODE_CODE",
    "QUERY_MODE_CURRENT",
    "QUERY_MODE_EXACT",
    "QUERY_MODE_OVERVIEW",
    "QUERY_MODE_RELATIONAL",
    "candidate_may_enter_ranking",
    "freshness_status_for_mode",
    "interpretation_is_available_as_of",
    "query_mode_is_valid",
    "query_requires_current_evidence",
    "query_requires_source_aligned_evidence",
    "stable_reciprocal_rank_fusion",
]
