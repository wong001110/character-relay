"""Durable, default-disabled scheduling state for approved external Fabric sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from echo_masque.knowledge_fabric_external_policy import (
    ATOM_PUBLIC_HTTPS_SOURCE_TYPE,
    WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
    canonical_public_https_locator,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeExternalHostRateRecord,
    KnowledgeExternalSourceScheduleRecord,
    KnowledgeSourceRecord,
)

_MIN_INTERVAL_SECONDS = 15 * 60
_MAX_INTERVAL_SECONDS = 7 * 24 * 60 * 60
_HOST_COOLDOWN_SECONDS = 60


@dataclass(frozen=True, slots=True)
class ExternalSourceScheduleClaim:
    """One lease that grants a scheduler worker permission to synchronize one Source."""

    source_id: str
    source_type: str
    hostname: str
    lease_token: str


class KnowledgeFabricExternalScheduleRepository:
    """Persist opt-in sync cadence without treating Source registration as egress consent."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, source_id: str) -> KnowledgeExternalSourceScheduleRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeExternalSourceScheduleRecord, source_id)

    def configure(
        self,
        *,
        source_id: str,
        enabled: bool,
        interval_seconds: int,
        now: datetime | None = None,
    ) -> KnowledgeExternalSourceScheduleRecord:
        interval = _validated_interval(interval_seconds)
        at = _utc(now or datetime.now(UTC))
        with self.database.session() as session:
            source = session.get(KnowledgeSourceRecord, source_id)
            hostname = _approved_source_hostname(source)
            del hostname
            record = session.get(KnowledgeExternalSourceScheduleRecord, source_id)
            if record is None:
                record = KnowledgeExternalSourceScheduleRecord(source_id=source_id)
                session.add(record)
            record.enabled = enabled
            record.interval_seconds = interval
            record.attempt_count = 0
            record.last_error_code = None
            record.lease_token = ""
            record.lease_expires_at = None
            record.next_run_at = at if enabled else None
            session.commit()
            session.refresh(record)
            return record

    def list_for_source_ids(
        self,
        source_ids: tuple[str, ...],
    ) -> list[KnowledgeExternalSourceScheduleRecord]:
        if not source_ids:
            return []
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeExternalSourceScheduleRecord)
                    .where(KnowledgeExternalSourceScheduleRecord.source_id.in_(source_ids))
                    .order_by(KnowledgeExternalSourceScheduleRecord.source_id)
                )
            )

    def claim_due(
        self,
        *,
        limit: int = 20,
        lease_seconds: int = 120,
        now: datetime | None = None,
    ) -> list[ExternalSourceScheduleClaim]:
        """Lease due Sources while enforcing one global cooldown per resolved hostname."""

        at = _utc(now or datetime.now(UTC))
        capped_limit = min(max(limit, 1), 50)
        lease_until = at + timedelta(seconds=max(30, lease_seconds))
        with self.database.session() as session:
            statement = (
                select(KnowledgeExternalSourceScheduleRecord, KnowledgeSourceRecord)
                .join(
                    KnowledgeSourceRecord,
                    KnowledgeSourceRecord.id == KnowledgeExternalSourceScheduleRecord.source_id,
                )
                .where(
                    KnowledgeExternalSourceScheduleRecord.enabled.is_(True),
                    KnowledgeExternalSourceScheduleRecord.next_run_at.is_not(None),
                    KnowledgeExternalSourceScheduleRecord.next_run_at <= at,
                )
                .order_by(
                    KnowledgeExternalSourceScheduleRecord.next_run_at,
                    KnowledgeExternalSourceScheduleRecord.source_id,
                )
                .limit(capped_limit)
            )
            if self.database.engine.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            claimed: list[ExternalSourceScheduleClaim] = []
            for schedule, source in session.execute(statement):
                if (
                    schedule.lease_expires_at is not None
                    and _utc(schedule.lease_expires_at) > at
                ):
                    continue
                hostname = _approved_source_hostname(source)
                host_rate = session.get(KnowledgeExternalHostRateRecord, hostname)
                if host_rate is not None and _utc(host_rate.next_allowed_at) > at:
                    schedule.next_run_at = host_rate.next_allowed_at
                    continue
                if host_rate is None:
                    host_rate = KnowledgeExternalHostRateRecord(
                        hostname=hostname,
                        next_allowed_at=at + timedelta(seconds=_HOST_COOLDOWN_SECONDS),
                    )
                    session.add(host_rate)
                else:
                    host_rate.next_allowed_at = at + timedelta(seconds=_HOST_COOLDOWN_SECONDS)
                token = str(uuid4())
                schedule.lease_token = token
                schedule.lease_expires_at = lease_until
                schedule.attempt_count += 1
                claimed.append(
                    ExternalSourceScheduleClaim(
                        source_id=source.id,
                        source_type=source.source_type,
                        hostname=hostname,
                        lease_token=token,
                    )
                )
            session.commit()
            return claimed

    def mark_result(
        self,
        *,
        claim: ExternalSourceScheduleClaim,
        succeeded: bool,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Release only the matching lease and schedule a bounded normal/retry interval."""

        at = _utc(now or datetime.now(UTC))
        safe_error = _safe_error_code(error_code)
        with self.database.session() as session:
            schedule = session.get(KnowledgeExternalSourceScheduleRecord, claim.source_id)
            if schedule is None or schedule.lease_token != claim.lease_token:
                return False
            schedule.lease_token = ""
            schedule.lease_expires_at = None
            if succeeded:
                schedule.attempt_count = 0
                schedule.last_error_code = None
                schedule.next_run_at = at + timedelta(seconds=schedule.interval_seconds)
            else:
                schedule.last_error_code = safe_error or "sync_failed"
                retry_seconds = max(
                    schedule.interval_seconds,
                    min(6 * 60 * 60, 60 * (2 ** min(schedule.attempt_count - 1, 8))),
                )
                schedule.next_run_at = at + timedelta(seconds=retry_seconds)
            session.commit()
            return True

    def recover_expired(self, *, now: datetime | None = None) -> int:
        """Clear stale worker leases without changing the current due time or retry history."""

        at = _utc(now or datetime.now(UTC))
        recovered = 0
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(KnowledgeExternalSourceScheduleRecord).where(
                        KnowledgeExternalSourceScheduleRecord.lease_expires_at.is_not(None),
                        KnowledgeExternalSourceScheduleRecord.lease_expires_at <= at,
                    )
                )
            )
            for record in records:
                record.lease_token = ""
                record.lease_expires_at = None
                recovered += 1
            session.commit()
        return recovered


def _approved_source_hostname(source: KnowledgeSourceRecord | None) -> str:
    if source is None:
        raise KeyError("source")
    if source.source_type not in {
        WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
        ATOM_PUBLIC_HTTPS_SOURCE_TYPE,
    }:
        raise ValueError("External schedule requires a supported public HTTPS Source.")
    locator = canonical_public_https_locator(source.locator)
    if locator != source.locator:
        raise ValueError("External schedule requires a canonical Source locator.")
    hostname = locator.split("/", maxsplit=3)[2]
    return hostname


def _validated_interval(value: int) -> int:
    if value < _MIN_INTERVAL_SECONDS or value > _MAX_INTERVAL_SECONDS:
        raise ValueError("External sync interval is outside the approved range.")
    return value


def _safe_error_code(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 80 or not candidate.replace("_", "").isalnum():
        raise ValueError("External sync error code is invalid.")
    return candidate


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "ExternalSourceScheduleClaim",
    "KnowledgeFabricExternalScheduleRepository",
]
