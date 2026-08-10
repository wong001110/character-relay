"""TTL-backed persistence for shared objective Media Analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.media_models import MediaAnalysisRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class MediaAnalysisRepository:
    """Small indexed SQL cache; Redis is intentionally unnecessary in V1."""

    def __init__(
        self,
        database: Database,
        *,
        ttl: timedelta = timedelta(days=30),
        access_refresh_after: timedelta = timedelta(hours=6),
    ) -> None:
        self.database = database
        self.ttl = ttl
        self.access_refresh_after = access_refresh_after

    def get(
        self,
        *,
        media_key: str,
        analysis_version: str,
        provider: str,
        model: str,
        now: datetime | None = None,
    ) -> MediaAnalysisRecord | None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(MediaAnalysisRecord).where(
                    MediaAnalysisRecord.media_key == media_key,
                    MediaAnalysisRecord.analysis_version == analysis_version,
                    MediaAnalysisRecord.provider == provider,
                    MediaAnalysisRecord.model == model,
                    MediaAnalysisRecord.status == "ready",
                    MediaAnalysisRecord.expires_at > current,
                )
            )
            if record is None:
                return None
            if current - _utc(record.last_accessed_at) >= self.access_refresh_after:
                record.last_accessed_at = current
                record.expires_at = current + self.ttl
                session.commit()
                session.refresh(record)
            return record

    def put(
        self,
        *,
        media_key: str,
        media_type: str,
        analysis_version: str,
        provider: str,
        model: str,
        result_json: str,
        now: datetime | None = None,
        ttl: timedelta | None = None,
    ) -> MediaAnalysisRecord:
        current = now or datetime.now(UTC)
        effective_ttl = ttl or self.ttl
        with self.database.session() as session:
            record = session.scalar(
                select(MediaAnalysisRecord).where(
                    MediaAnalysisRecord.media_key == media_key,
                    MediaAnalysisRecord.analysis_version == analysis_version,
                    MediaAnalysisRecord.provider == provider,
                    MediaAnalysisRecord.model == model,
                )
            )
            if record is None:
                record = MediaAnalysisRecord(
                    id=str(uuid4()),
                    media_key=media_key,
                    media_type=media_type,
                    analysis_version=analysis_version,
                    provider=provider,
                    model=model,
                    status="ready",
                    result_json=result_json,
                    lease_token=None,
                    lease_expires_at=None,
                    error=None,
                    created_at=current,
                    last_accessed_at=current,
                    expires_at=current + effective_ttl,
                )
                session.add(record)
            else:
                record.media_type = media_type
                record.status = "ready"
                record.result_json = result_json
                record.lease_token = None
                record.lease_expires_at = None
                record.error = None
                record.last_accessed_at = current
                record.expires_at = current + effective_ttl
            session.commit()
            session.refresh(record)
            return record

    def purge_expired(
        self,
        *,
        now: datetime | None = None,
        limit: int = 500,
    ) -> int:
        """Delete a bounded batch so cleanup never becomes a request-path table sweep."""

        current = now or datetime.now(UTC)
        bounded = max(1, min(limit, 5000))
        with self.database.session() as session:
            ids = list(
                session.scalars(
                    select(MediaAnalysisRecord.id)
                    .where(MediaAnalysisRecord.expires_at <= current)
                    .order_by(MediaAnalysisRecord.expires_at.asc())
                    .limit(bounded)
                )
            )
            if not ids:
                return 0
            session.execute(delete(MediaAnalysisRecord).where(MediaAnalysisRecord.id.in_(ids)))
            session.commit()
            return len(ids)

    def count(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count()).select_from(MediaAnalysisRecord)) or 0)
