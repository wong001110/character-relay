"""Derived conditional-sync state for external Knowledge Fabric Sources."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
    normalized_website_validator,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeExternalSourceScheduleRecord,
    KnowledgeExternalSourceSyncStateRecord,
    KnowledgeSourceRecord,
)


class KnowledgeFabricExternalSyncRepository:
    """Persist only bounded validators/outcomes, never a response body or source credential."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def require_website_source(self, source_id: str) -> KnowledgeSourceRecord:
        return self.require_public_https_source(
            source_id, allowed_source_types=frozenset({WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE})
        )

    def require_public_https_source(
        self,
        source_id: str,
        *,
        allowed_source_types: frozenset[str],
    ) -> KnowledgeSourceRecord:
        with self.database.session() as session:
            source = session.get(KnowledgeSourceRecord, source_id)
            if source is None:
                raise KeyError("source")
            if source.source_type not in allowed_source_types:
                raise ValueError("External Website sync requires a public HTTPS Website Source.")
            return source

    def get_state(self, source_id: str) -> KnowledgeExternalSourceSyncStateRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeExternalSourceSyncStateRecord, source_id)

    def list_states_for_source_ids(
        self,
        source_ids: tuple[str, ...],
    ) -> list[KnowledgeExternalSourceSyncStateRecord]:
        """Return redaction-safe sync outcomes for an already-authorized Source set."""

        if not source_ids:
            return []
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeExternalSourceSyncStateRecord)
                    .where(KnowledgeExternalSourceSyncStateRecord.source_id.in_(source_ids))
                    .order_by(KnowledgeExternalSourceSyncStateRecord.source_id)
                )
            )

    def schedule_claim_is_current(
        self,
        *,
        source_id: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> bool:
        """Check the scheduler fence before a worker can publish or expose a sync result."""

        at = _utc(now or datetime.now(UTC))
        with self.database.session() as session:
            schedule = session.get(KnowledgeExternalSourceScheduleRecord, source_id)
            return _schedule_claim_is_current(schedule=schedule, lease_token=lease_token, now=at)

    def record_outcome(
        self,
        *,
        source_id: str,
        outcome: str,
        error_code: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        changed: bool = False,
        checked_at: datetime | None = None,
        schedule_lease_token: str | None = None,
        allowed_source_types: frozenset[str] = frozenset({WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE}),
    ) -> KnowledgeExternalSourceSyncStateRecord | None:
        """Atomically update a Source's visible timestamps and its derived validator state."""

        if outcome not in {"changed", "failed", "not_modified", "unchanged"}:
            raise ValueError("External Website sync outcome is invalid.")
        if error_code is not None and error_code not in {
            "authorization_failed",
            "content_size_rejected",
            "content_type_rejected",
            "fetch_failed",
            "http_failed",
            "invalid_feed",
            "invalid_encoding",
            "redirect_refused",
            "source_rejected",
            "validator_rejected",
        }:
            raise ValueError("External Website sync error code is invalid.")
        now = checked_at or datetime.now(UTC)
        with self.database.session() as session:
            source = session.get(KnowledgeSourceRecord, source_id)
            if source is None:
                raise KeyError("source")
            if source.source_type not in allowed_source_types:
                raise ValueError("External Website sync requires a public HTTPS Website Source.")
            if schedule_lease_token is not None:
                schedule = session.get(KnowledgeExternalSourceScheduleRecord, source_id)
                if not _schedule_claim_is_current(
                    schedule=schedule,
                    lease_token=schedule_lease_token,
                    now=_utc(now),
                ):
                    return None
            state = session.get(KnowledgeExternalSourceSyncStateRecord, source_id)
            if state is None:
                state = KnowledgeExternalSourceSyncStateRecord(source_id=source_id)
                session.add(state)
            if etag is not None:
                normalized_etag = normalized_website_validator(etag)
                if normalized_etag is not None:
                    state.etag = normalized_etag
            if last_modified is not None:
                normalized_last_modified = normalized_website_validator(last_modified)
                if normalized_last_modified is not None:
                    state.last_modified = normalized_last_modified
            state.last_outcome = outcome
            state.last_error_code = error_code
            source.last_checked_at = now
            if changed:
                source.last_changed_at = now
            session.commit()
            session.refresh(state)
            return state


def _schedule_claim_is_current(
    *,
    schedule: KnowledgeExternalSourceScheduleRecord | None,
    lease_token: str,
    now: datetime,
) -> bool:
    if not lease_token or schedule is None or not schedule.enabled:
        return False
    if schedule.lease_token != lease_token or schedule.lease_expires_at is None:
        return False
    return _utc(schedule.lease_expires_at) > now


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["KnowledgeFabricExternalSyncRepository"]
