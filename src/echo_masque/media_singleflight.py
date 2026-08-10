"""Cross-worker single-flight coordination for expensive Media Understanding calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.media_models import MediaAnalysisRecord
from echo_masque.persistence.media_repository import MediaAnalysisRepository

MediaClaimStatus = Literal["claimed", "ready", "processing", "failed"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class MediaAnalysisClaim:
    status: MediaClaimStatus
    record: MediaAnalysisRecord
    lease_token: str = ""


class MediaAnalysisSingleFlight:
    """Coordinate one provider call for one global content-analysis identity."""

    def __init__(
        self,
        repository: MediaAnalysisRepository,
        *,
        processing_lease: timedelta = timedelta(minutes=3),
        failure_cooldown: timedelta = timedelta(seconds=30),
    ) -> None:
        self.repository = repository
        self.database = repository.database
        self.processing_lease = processing_lease
        self.failure_cooldown = failure_cooldown

    @staticmethod
    def _identity_query(
        *,
        media_key: str,
        analysis_version: str,
        provider: str,
        model: str,
    ):
        return select(MediaAnalysisRecord).where(
            MediaAnalysisRecord.media_key == media_key,
            MediaAnalysisRecord.analysis_version == analysis_version,
            MediaAnalysisRecord.provider == provider,
            MediaAnalysisRecord.model == model,
        )

    def state(
        self,
        *,
        media_key: str,
        analysis_version: str,
        provider: str,
        model: str,
    ) -> MediaAnalysisRecord | None:
        with self.database.session() as session:
            return session.scalar(
                self._identity_query(
                    media_key=media_key,
                    analysis_version=analysis_version,
                    provider=provider,
                    model=model,
                )
            )

    def claim(
        self,
        *,
        media_key: str,
        media_type: str,
        analysis_version: str,
        provider: str,
        model: str,
        now: datetime | None = None,
    ) -> MediaAnalysisClaim:
        """Claim the provider call, or report ready/in-flight/cooldown state."""

        current = now or datetime.now(UTC)
        lease_token = str(uuid4())
        with self.database.session() as session:
            created = MediaAnalysisRecord(
                id=str(uuid4()),
                media_key=media_key,
                media_type=media_type,
                analysis_version=analysis_version,
                provider=provider,
                model=model,
                status="processing",
                result_json="",
                lease_token=lease_token,
                lease_expires_at=current + self.processing_lease,
                error=None,
                created_at=current,
                last_accessed_at=current,
                expires_at=current + self.repository.ttl,
            )
            session.add(created)
            try:
                session.commit()
                session.refresh(created)
                return MediaAnalysisClaim("claimed", created, lease_token)
            except IntegrityError:
                session.rollback()

            existing = session.scalar(
                self._identity_query(
                    media_key=media_key,
                    analysis_version=analysis_version,
                    provider=provider,
                    model=model,
                )
            )
            if existing is None:
                raise RuntimeError("Media Analysis identity disappeared after claim conflict.")

            if existing.status == "ready" and _utc(existing.expires_at) > current:
                return MediaAnalysisClaim("ready", existing)

            lease_expires = (
                _utc(existing.lease_expires_at)
                if existing.lease_expires_at is not None
                else None
            )
            if existing.status == "processing" and lease_expires is not None and lease_expires > current:
                return MediaAnalysisClaim("processing", existing)
            if existing.status == "failed" and lease_expires is not None and lease_expires > current:
                return MediaAnalysisClaim("failed", existing)

            result = session.execute(
                update(MediaAnalysisRecord)
                .where(
                    MediaAnalysisRecord.id == existing.id,
                    or_(
                        MediaAnalysisRecord.status == "failed",
                        MediaAnalysisRecord.expires_at <= current,
                        MediaAnalysisRecord.lease_expires_at.is_(None),
                        MediaAnalysisRecord.lease_expires_at <= current,
                    ),
                )
                .values(
                    media_type=media_type,
                    status="processing",
                    result_json="",
                    lease_token=lease_token,
                    lease_expires_at=current + self.processing_lease,
                    error=None,
                    last_accessed_at=current,
                    expires_at=current + self.repository.ttl,
                )
            )
            if int(getattr(result, "rowcount", 0) or 0) == 1:
                session.commit()
                refreshed = session.get(MediaAnalysisRecord, existing.id)
                if refreshed is None:
                    raise RuntimeError("Claimed Media Analysis record could not be reloaded.")
                return MediaAnalysisClaim("claimed", refreshed, lease_token)

            session.rollback()
            refreshed = session.scalar(
                self._identity_query(
                    media_key=media_key,
                    analysis_version=analysis_version,
                    provider=provider,
                    model=model,
                )
            )
            if refreshed is None:
                raise RuntimeError("Media Analysis claim was lost during contention.")
            if refreshed.status == "ready" and _utc(refreshed.expires_at) > current:
                return MediaAnalysisClaim("ready", refreshed)
            if refreshed.status == "failed":
                return MediaAnalysisClaim("failed", refreshed)
            return MediaAnalysisClaim("processing", refreshed)

    def complete(
        self,
        *,
        record_id: str,
        lease_token: str,
        result_json: str,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            result = session.execute(
                update(MediaAnalysisRecord)
                .where(
                    MediaAnalysisRecord.id == record_id,
                    MediaAnalysisRecord.status == "processing",
                    MediaAnalysisRecord.lease_token == lease_token,
                )
                .values(
                    status="ready",
                    result_json=result_json,
                    lease_token=None,
                    lease_expires_at=None,
                    error=None,
                    last_accessed_at=current,
                    expires_at=current + self.repository.ttl,
                )
            )
            if int(getattr(result, "rowcount", 0) or 0) != 1:
                session.rollback()
                return False
            session.commit()
            return True

    def fail(
        self,
        *,
        record_id: str,
        lease_token: str,
        error: str,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            session.execute(
                update(MediaAnalysisRecord)
                .where(
                    MediaAnalysisRecord.id == record_id,
                    MediaAnalysisRecord.status == "processing",
                    MediaAnalysisRecord.lease_token == lease_token,
                )
                .values(
                    status="failed",
                    result_json="",
                    lease_token=None,
                    lease_expires_at=current + self.failure_cooldown,
                    error=error[:1000],
                    last_accessed_at=current,
                    expires_at=current + self.repository.ttl,
                )
            )
            session.commit()

    def invalidate(self, record_id: str) -> None:
        with self.database.session() as session:
            record = session.get(MediaAnalysisRecord, record_id)
            if record is not None:
                session.delete(record)
                session.commit()
