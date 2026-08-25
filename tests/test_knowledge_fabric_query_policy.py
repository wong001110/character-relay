from datetime import UTC, datetime, timedelta, timezone

from echo_masque.knowledge_fabric_query_policy import (
    FRESHNESS_INSUFFICIENT,
    FRESHNESS_NOT_REQUESTED,
    candidate_may_enter_ranking,
    freshness_status_for_mode,
    interpretation_is_available_as_of,
    query_mode_is_valid,
    query_requires_source_aligned_evidence,
    stable_reciprocal_rank_fusion,
)


def test_query_modes_fail_closed_and_exact_requires_source_aligned_evidence() -> None:
    assert query_mode_is_valid("overview")
    assert query_mode_is_valid("exact")
    assert not query_mode_is_valid("summary")
    assert query_requires_source_aligned_evidence("exact")
    assert not query_requires_source_aligned_evidence("overview")


def test_candidate_cannot_enter_ranking_without_effective_corpus_authorization() -> None:
    authorized = frozenset({"corpus-a"})
    assert candidate_may_enter_ranking(corpus_id="corpus-a", authorized_corpus_ids=authorized)
    assert not candidate_may_enter_ranking(corpus_id="corpus-b", authorized_corpus_ids=authorized)
    assert not candidate_may_enter_ranking(corpus_id="", authorized_corpus_ids=authorized)


def test_temporal_interpretations_use_half_open_validity_interval() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 2, 1, tzinfo=UTC)
    assert not interpretation_is_available_as_of(
        valid_from=start,
        valid_to=end,
        as_of=datetime(2025, 12, 31, tzinfo=UTC),
    )
    assert interpretation_is_available_as_of(valid_from=start, valid_to=end, as_of=start)
    assert not interpretation_is_available_as_of(valid_from=start, valid_to=end, as_of=end)
    assert interpretation_is_available_as_of(
        valid_from=start,
        valid_to=None,
        as_of=datetime(2025, 12, 31, 19, tzinfo=UTC),
    ) is False
    assert interpretation_is_available_as_of(
        valid_from=None,
        valid_to=end,
        as_of=datetime(2025, 12, 31, 19, tzinfo=UTC),
    )
    assert interpretation_is_available_as_of(
        valid_from=start.replace(tzinfo=None),
        valid_to=end.replace(tzinfo=None),
        as_of=start,
    )
    assert interpretation_is_available_as_of(
        valid_from=start,
        valid_to=end,
        as_of=datetime(2025, 12, 31, 19, tzinfo=UTC),
    ) is False
    assert interpretation_is_available_as_of(
        valid_from=start,
        valid_to=end,
        as_of=datetime(2025, 12, 31, 19, tzinfo=timezone(timedelta(hours=-5))),
    )
    assert interpretation_is_available_as_of(
        valid_from=start,
        valid_to=end,
        as_of=None,
    )


def test_current_mode_reports_unconfigured_freshness_as_insufficient() -> None:
    assert freshness_status_for_mode("overview") == FRESHNESS_NOT_REQUESTED
    assert freshness_status_for_mode("current") == FRESHNESS_INSUFFICIENT


def test_fusion_deduplicates_evidence_and_keeps_ties_stable() -> None:
    assert stable_reciprocal_rank_fusion((("entry-b", "entry-a"), ("entry-a", "entry-c"))) == (
        "entry-a",
        "entry-b",
        "entry-c",
    )
    assert stable_reciprocal_rank_fusion((("entry-b",), ("entry-a",))) == (
        "entry-b",
        "entry-a",
    )
    assert stable_reciprocal_rank_fusion(
        (("entry-a", "entry-b", "entry-c"), ("entry-b", "entry-c", "entry-a"))
    ) == (
        "entry-b",
        "entry-a",
        "entry-c",
    )
    assert stable_reciprocal_rank_fusion((("entry-a", "entry-b"), ("entry-c", "entry-b"))) == (
        "entry-a",
        "entry-b",
        "entry-c",
    )
    assert stable_reciprocal_rank_fusion(()) == ()
