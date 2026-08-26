"""Durable claim/lease lifecycle for derived Knowledge Fabric invalidation work."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from echo_masque.knowledge_fabric_invalidation_policy import (
    INVALIDATION_COMPLETED,
    INVALIDATION_FAILED,
    INVALIDATION_PENDING,
    INVALIDATION_RUNNING,
    failure_status_for_attempt,
    invalidation_is_claimable,
    retry_delay_seconds,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeDependencyInvalidationRecord,
    KnowledgeSourceVersionRecord,
)

_WORKER_STATE_KEY = "_derived_work"
_SAFE_ERROR_CODES = frozenset({"derived_work_failed", "unsupported_dependency"})


@dataclass(frozen=True, slots=True)
class KnowledgeDerivedWorkClaim:
    invalidation_id: str
    source_version_id: str
    dependency_type: str
    lease_token: str


@dataclass(frozen=True, slots=True)
class KnowledgeDerivedWorkSummary:
    pending: int
    running: int
    failed: int


class KnowledgeFabricInvalidationRepository:
    """Own derived-work retries without exposing private Source metadata to a worker API."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def claim_due(
        self,
        *,
        limit: int = 20,
        lease_seconds: int = 120,
        now: datetime | None = None,
    ) -> list[KnowledgeDerivedWorkClaim]:
        at = _utc(now or datetime.now(UTC))
        lease_until = at + timedelta(seconds=max(30, lease_seconds))
        capped_limit = min(max(limit, 1), 50)
        with self.database.session() as session:
            statement = (
                select(KnowledgeDependencyInvalidationRecord)
                .where(
                    KnowledgeDependencyInvalidationRecord.status.in_(
                        (INVALIDATION_PENDING, INVALIDATION_RUNNING)
                    )
                )
                .order_by(
                    KnowledgeDependencyInvalidationRecord.created_at,
                    KnowledgeDependencyInvalidationRecord.id,
                )
                .limit(capped_limit)
            )
            if self.database.engine.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            claims: list[KnowledgeDerivedWorkClaim] = []
            for record in session.scalars(statement):
                metadata = _decode(record.metadata_json)
                state = _worker_state(metadata)
                if not invalidation_is_claimable(
                    status=record.status,
                    lease_expires_at=_parse_time(state.get("lease_expires_at")),
                    next_attempt_at=_parse_time(state.get("next_attempt_at")),
                    now=at,
                ):
                    continue
                attempt_count = _attempt_count(state) + 1
                lease_token = str(uuid4())
                state.update(
                    {
                        "attempt_count": attempt_count,
                        "lease_token": lease_token,
                        "lease_expires_at": lease_until.isoformat(),
                        "next_attempt_at": None,
                        "last_error_code": None,
                    }
                )
                metadata[_WORKER_STATE_KEY] = state
                record.metadata_json = _encode(metadata)
                record.status = INVALIDATION_RUNNING
                claims.append(
                    KnowledgeDerivedWorkClaim(
                        invalidation_id=record.id,
                        source_version_id=record.source_version_id,
                        dependency_type=record.dependency_type,
                        lease_token=lease_token,
                    )
                )
            session.commit()
            return claims

    def complete(self, *, claim: KnowledgeDerivedWorkClaim, now: datetime | None = None) -> bool:
        at = _utc(now or datetime.now(UTC))
        with self.database.session() as session:
            record = session.get(KnowledgeDependencyInvalidationRecord, claim.invalidation_id)
            if record is None or not _claim_is_current(record, claim):
                return False
            metadata = _decode(record.metadata_json)
            state = _worker_state(metadata)
            state.update({"lease_token": "", "lease_expires_at": None, "next_attempt_at": None})
            metadata[_WORKER_STATE_KEY] = state
            record.metadata_json = _encode(metadata)
            record.status = INVALIDATION_COMPLETED
            record.processed_at = at
            session.commit()
            return True

    def fail(
        self,
        *,
        claim: KnowledgeDerivedWorkClaim,
        error_code: str,
        now: datetime | None = None,
    ) -> bool:
        if error_code not in _SAFE_ERROR_CODES:
            raise ValueError("Derived work error code is invalid.")
        at = _utc(now or datetime.now(UTC))
        with self.database.session() as session:
            record = session.get(KnowledgeDependencyInvalidationRecord, claim.invalidation_id)
            if record is None or not _claim_is_current(record, claim):
                return False
            metadata = _decode(record.metadata_json)
            state = _worker_state(metadata)
            attempt_count = _attempt_count(state)
            status = failure_status_for_attempt(attempt_count)
            state.update(
                {
                    "lease_token": "",
                    "lease_expires_at": None,
                    "last_error_code": error_code,
                    "next_attempt_at": (
                        None
                        if status == INVALIDATION_FAILED
                        else (
                            at + timedelta(seconds=retry_delay_seconds(attempt_count))
                        ).isoformat()
                    ),
                }
            )
            metadata[_WORKER_STATE_KEY] = state
            record.metadata_json = _encode(metadata)
            record.status = status
            record.processed_at = at if status == INVALIDATION_FAILED else None
            session.commit()
            return True

    def recover_expired(self, *, now: datetime | None = None) -> int:
        at = _utc(now or datetime.now(UTC))
        recovered = 0
        with self.database.session() as session:
            records = session.scalars(
                select(KnowledgeDependencyInvalidationRecord).where(
                    KnowledgeDependencyInvalidationRecord.status == INVALIDATION_RUNNING
                )
            )
            for record in records:
                metadata = _decode(record.metadata_json)
                state = _worker_state(metadata)
                lease_expires_at = _parse_time(state.get("lease_expires_at"))
                if lease_expires_at is None or lease_expires_at > at:
                    continue
                state.update(
                    {
                        "lease_token": "",
                        "lease_expires_at": None,
                        "next_attempt_at": at.isoformat(),
                    }
                )
                metadata[_WORKER_STATE_KEY] = state
                record.metadata_json = _encode(metadata)
                record.status = INVALIDATION_PENDING
                record.processed_at = None
                recovered += 1
            session.commit()
        return recovered

    def retry_failed_for_source(self, source_id: str, *, now: datetime | None = None) -> int:
        """Explicitly requeue only terminal derived work for one existing Source."""

        at = _utc(now or datetime.now(UTC))
        with self.database.session() as session:
            records = session.scalars(
                select(KnowledgeDependencyInvalidationRecord)
                .join(
                    KnowledgeSourceVersionRecord,
                    KnowledgeSourceVersionRecord.id
                    == KnowledgeDependencyInvalidationRecord.source_version_id,
                )
                .where(
                    KnowledgeSourceVersionRecord.source_id == source_id,
                    KnowledgeDependencyInvalidationRecord.status == INVALIDATION_FAILED,
                )
            )
            requeued = 0
            for record in records:
                metadata = _decode(record.metadata_json)
                state = _worker_state(metadata)
                state.update(
                    {
                        "lease_token": "",
                        "lease_expires_at": None,
                        "next_attempt_at": at.isoformat(),
                        "last_error_code": None,
                    }
                )
                metadata[_WORKER_STATE_KEY] = state
                record.metadata_json = _encode(metadata)
                record.status = INVALIDATION_PENDING
                record.processed_at = None
                requeued += 1
            session.commit()
            return requeued

    def summary_for_source_ids(
        self, source_ids: tuple[str, ...]
    ) -> dict[str, KnowledgeDerivedWorkSummary]:
        if not source_ids:
            return {}
        counts = {source_id: {"pending": 0, "running": 0, "failed": 0} for source_id in source_ids}
        with self.database.session() as session:
            rows = session.execute(
                select(
                    KnowledgeSourceVersionRecord.source_id,
                    KnowledgeDependencyInvalidationRecord.status,
                )
                .join(
                    KnowledgeDependencyInvalidationRecord,
                    KnowledgeDependencyInvalidationRecord.source_version_id
                    == KnowledgeSourceVersionRecord.id,
                )
                .where(KnowledgeSourceVersionRecord.source_id.in_(source_ids))
            )
            for source_id, status in rows:
                if status in counts[source_id]:
                    counts[source_id][status] += 1
        return {
            source_id: KnowledgeDerivedWorkSummary(**values)
            for source_id, values in counts.items()
        }


def _claim_is_current(
    record: KnowledgeDependencyInvalidationRecord | None,
    claim: KnowledgeDerivedWorkClaim,
) -> bool:
    if record is None or record.status != INVALIDATION_RUNNING:
        return False
    return _worker_state(_decode(record.metadata_json)).get("lease_token") == claim.lease_token


def _worker_state(metadata: dict[str, object]) -> dict[str, object]:
    value = metadata.get(_WORKER_STATE_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _attempt_count(state: dict[str, object]) -> int:
    value = state.get("attempt_count", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _utc(parsed)


def _decode(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _encode(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "KnowledgeDerivedWorkClaim",
    "KnowledgeDerivedWorkSummary",
    "KnowledgeFabricInvalidationRepository",
]
