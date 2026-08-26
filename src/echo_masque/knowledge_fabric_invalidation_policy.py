"""Pure, bounded lifecycle decisions for derived Knowledge Fabric invalidations."""

from __future__ import annotations

from datetime import datetime

INVALIDATION_PENDING = "pending"
INVALIDATION_RUNNING = "running"
INVALIDATION_COMPLETED = "completed"
INVALIDATION_FAILED = "failed"
MAX_INVALIDATION_ATTEMPTS = 3


def invalidation_is_claimable(
    *,
    status: str,
    lease_expires_at: datetime | None,
    next_attempt_at: datetime | None,
    now: datetime,
) -> bool:
    """Only pending work or an expired lease can be acquired by a worker."""

    if status == INVALIDATION_PENDING:
        return next_attempt_at is None or next_attempt_at <= now
    return (
        status == INVALIDATION_RUNNING
        and lease_expires_at is not None
        and lease_expires_at <= now
    )


def retry_delay_seconds(attempt_count: int) -> int:
    """Keep automatic retry bounded without treating a failed derived view as source failure."""

    delay = 60
    for _ in range(min(max(attempt_count - 1, 0), 9)):
        delay *= 2
    return min(6 * 60 * 60, delay)


def failure_status_for_attempt(attempt_count: int) -> str:
    """Terminal failure needs an explicit operator retry after the bounded automatic attempts."""

    return (
        INVALIDATION_FAILED
        if attempt_count >= MAX_INVALIDATION_ATTEMPTS
        else INVALIDATION_PENDING
    )


__all__ = [
    "INVALIDATION_COMPLETED",
    "INVALIDATION_FAILED",
    "INVALIDATION_PENDING",
    "INVALIDATION_RUNNING",
    "MAX_INVALIDATION_ATTEMPTS",
    "failure_status_for_attempt",
    "invalidation_is_claimable",
    "retry_delay_seconds",
]
