from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.knowledge_fabric_invalidation_policy import (
    INVALIDATION_FAILED,
    INVALIDATION_PENDING,
    INVALIDATION_RUNNING,
    failure_status_for_attempt,
    invalidation_is_claimable,
    retry_delay_seconds,
)


def test_only_pending_or_expired_running_work_is_claimable() -> None:
    now = datetime(2026, 8, 26, tzinfo=UTC)

    assert invalidation_is_claimable(
        status=INVALIDATION_PENDING,
        lease_expires_at=None,
        next_attempt_at=None,
        now=now,
    )
    assert invalidation_is_claimable(
        status=INVALIDATION_PENDING,
        lease_expires_at=None,
        next_attempt_at=now,
        now=now,
    )
    assert not invalidation_is_claimable(
        status=INVALIDATION_PENDING,
        lease_expires_at=None,
        next_attempt_at=now + timedelta(seconds=1),
        now=now,
    )
    assert invalidation_is_claimable(
        status=INVALIDATION_RUNNING,
        lease_expires_at=now,
        next_attempt_at=None,
        now=now,
    )
    assert not invalidation_is_claimable(
        status=INVALIDATION_RUNNING,
        lease_expires_at=None,
        next_attempt_at=None,
        now=now,
    )
    assert not invalidation_is_claimable(
        status=INVALIDATION_RUNNING,
        lease_expires_at=now + timedelta(seconds=1),
        next_attempt_at=None,
        now=now,
    )
    assert not invalidation_is_claimable(
        status="completed",
        lease_expires_at=now - timedelta(seconds=1),
        next_attempt_at=now - timedelta(seconds=1),
        now=now,
    )


def test_derived_work_retry_is_bounded_then_requires_explicit_retry() -> None:
    assert retry_delay_seconds(1) == 60
    assert retry_delay_seconds(2) == 120
    assert retry_delay_seconds(100) == 6 * 60 * 60
    assert failure_status_for_attempt(2) == INVALIDATION_PENDING
    assert failure_status_for_attempt(3) == INVALIDATION_FAILED
