"""Short-lived, redaction-safe reports for completed external Knowledge Fabric syncs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.knowledge_fabric_website_sync import WebsiteSyncResult
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import KnowledgeExternalSourceSyncRunRecord


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ExternalSyncRunReport:
    """Public-safe fields from a retained completed scheduler attempt."""

    id: str
    source_id: str
    outcome: str
    error_code: str | None
    started_at: datetime
    completed_at: datetime
    discovered_page_count: int
    changed_page_count: int
    unchanged_page_count: int
    failed_page_count: int
    removed_page_count: int
    admitted_image_count: int

    @classmethod
    def from_record(cls, record: KnowledgeExternalSourceSyncRunRecord) -> ExternalSyncRunReport:
        return cls(
            id=record.id,
            source_id=record.source_id,
            outcome=record.outcome,
            error_code=record.error_code,
            started_at=_utc(record.started_at),
            completed_at=_utc(record.completed_at),
            discovered_page_count=record.discovered_page_count,
            changed_page_count=record.changed_page_count,
            unchanged_page_count=record.unchanged_page_count,
            failed_page_count=record.failed_page_count,
            removed_page_count=record.removed_page_count,
            admitted_image_count=record.admitted_image_count,
        )


class KnowledgeFabricExternalSyncRunRepository:
    """Append-only terminal scheduler reports; no page locators or response data are retained."""

    def __init__(self, database: Database, *, retention_days: int = 7) -> None:
        self.database = database
        self.retention = timedelta(days=max(1, min(retention_days, 90)))

    def record_completed(
        self,
        *,
        source_id: str,
        result: WebsiteSyncResult,
        started_at: datetime,
        completed_at: datetime | None = None,
    ) -> ExternalSyncRunReport:
        """Persist only a finalized non-stale scheduler result and safe aggregate counters."""

        if result.outcome == "stale":
            raise ValueError("Stale sync attempts cannot produce a completed report.")
        started = _utc(started_at)
        completed = _utc(completed_at or datetime.now(UTC))
        with self.database.session() as session:
            record = KnowledgeExternalSourceSyncRunRecord(
                id=str(uuid4()),
                source_id=source_id,
                outcome=result.outcome,
                error_code=result.error_code,
                started_at=started,
                completed_at=completed,
                expires_at=completed + self.retention,
                discovered_page_count=result.discovered_page_count,
                changed_page_count=result.changed_page_count,
                unchanged_page_count=result.unchanged_page_count,
                failed_page_count=result.failed_page_count,
                removed_page_count=result.removed_page_count,
                admitted_image_count=result.admitted_image_count,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return ExternalSyncRunReport.from_record(record)

    def list_for_source_ids(
        self,
        source_ids: tuple[str, ...],
        *,
        limit_per_source: int = 5,
    ) -> dict[str, list[ExternalSyncRunReport]]:
        """Return a bounded most-recent report journal for each requested Source."""

        if not source_ids:
            return {}
        bounded = min(max(limit_per_source, 1), 20)
        reports: dict[str, list[ExternalSyncRunReport]] = {
            source_id: [] for source_id in source_ids
        }
        now = datetime.now(UTC)
        with self.database.session() as session:
            records = session.scalars(
                select(KnowledgeExternalSourceSyncRunRecord)
                .where(
                    KnowledgeExternalSourceSyncRunRecord.source_id.in_(source_ids),
                    KnowledgeExternalSourceSyncRunRecord.expires_at > now,
                )
                .order_by(
                    KnowledgeExternalSourceSyncRunRecord.completed_at.desc(),
                    KnowledgeExternalSourceSyncRunRecord.id.desc(),
                )
                .limit(min(500, len(source_ids) * bounded))
            )
            for record in records:
                bucket = reports[record.source_id]
                if len(bucket) < bounded:
                    bucket.append(ExternalSyncRunReport.from_record(record))
        return reports

    def purge_expired(self, *, now: datetime | None = None, limit: int = 500) -> int:
        """Delete one bounded expired batch outside request and worker paths."""

        at = _utc(now or datetime.now(UTC))
        bounded = min(max(limit, 1), 5000)
        with self.database.session() as session:
            ids = list(
                session.scalars(
                    select(KnowledgeExternalSourceSyncRunRecord.id)
                    .where(KnowledgeExternalSourceSyncRunRecord.expires_at <= at)
                    .order_by(KnowledgeExternalSourceSyncRunRecord.expires_at.asc())
                    .limit(bounded)
                )
            )
            if not ids:
                return 0
            session.execute(
                delete(KnowledgeExternalSourceSyncRunRecord).where(
                    KnowledgeExternalSourceSyncRunRecord.id.in_(ids)
                )
            )
            session.commit()
            return len(ids)


__all__ = ["ExternalSyncRunReport", "KnowledgeFabricExternalSyncRunRepository"]
