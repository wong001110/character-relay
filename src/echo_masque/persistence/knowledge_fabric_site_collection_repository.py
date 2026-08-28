"""Derived page discovery and conditional-request state for Site Collection Sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
    canonical_public_https_locator,
    normalized_website_validator,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeExternalSourceCollectionStateRecord,
    KnowledgeExternalSourcePageStateRecord,
    KnowledgeSourceRecord,
)


@dataclass(frozen=True, slots=True)
class SiteCollectionPageState:
    locator: str
    discovery_kind: str
    discovered_from_locator: str
    etag: str | None
    last_modified: str | None
    content_sha256: str | None
    status: str


@dataclass(frozen=True, slots=True)
class SiteCollectionSyncSummary:
    """Redaction-safe current state for one Site Collection Source."""

    source_id: str
    last_completed_at: datetime | None
    available_page_count: int
    removed_page_count: int
    checked_page_count: int
    failed_page_count: int


class KnowledgeFabricSiteCollectionRepository:
    """Keep page metadata separate from immutable source artifacts and Evidence."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def begin_generation(self, source_id: str) -> int:
        with self.database.session() as session:
            self._require_collection_source(session, source_id)
            state = session.get(KnowledgeExternalSourceCollectionStateRecord, source_id)
            if state is None:
                state = KnowledgeExternalSourceCollectionStateRecord(
                    source_id=source_id,
                    discovery_generation=0,
                )
                session.add(state)
            state.discovery_generation += 1
            session.commit()
            return state.discovery_generation

    def reconcile_discovered_pages(
        self,
        *,
        source_id: str,
        generation: int,
        pages: tuple[tuple[str, str, str], ...],
    ) -> list[SiteCollectionPageState]:
        """Record a complete admitted set; removal waits for ``complete_generation``."""

        with self.database.session() as session:
            self._require_collection_source(session, source_id)
            records: list[KnowledgeExternalSourcePageStateRecord] = []
            for locator, discovery_kind, discovered_from_locator in pages:
                canonical = canonical_public_https_locator(locator)
                record = session.scalar(
                    select(KnowledgeExternalSourcePageStateRecord).where(
                        KnowledgeExternalSourcePageStateRecord.source_id == source_id,
                        KnowledgeExternalSourcePageStateRecord.locator == canonical,
                    )
                )
                if record is None:
                    record = KnowledgeExternalSourcePageStateRecord(
                        id=str(uuid4()), source_id=source_id, locator=canonical
                    )
                    session.add(record)
                record.discovery_kind = discovery_kind
                record.discovered_from_locator = discovered_from_locator
                record.last_seen_generation = generation
                record.status = "available"
                records.append(record)
            session.commit()
            return [self._view(record) for record in records]

    def list_available_pages(self, source_id: str) -> list[SiteCollectionPageState]:
        with self.database.session() as session:
            return [
                self._view(record)
                for record in session.scalars(
                    select(KnowledgeExternalSourcePageStateRecord)
                    .where(
                        KnowledgeExternalSourcePageStateRecord.source_id == source_id,
                        KnowledgeExternalSourcePageStateRecord.status == "available",
                    )
                    .order_by(KnowledgeExternalSourcePageStateRecord.locator)
                )
            ]

    def summaries_for_source_ids(
        self,
        source_ids: tuple[str, ...],
    ) -> dict[str, SiteCollectionSyncSummary]:
        """Return only aggregate page-state facts; locators and validators stay internal."""

        if not source_ids:
            return {}
        with self.database.session() as session:
            collections = {
                record.source_id: record
                for record in session.scalars(
                    select(KnowledgeExternalSourceCollectionStateRecord).where(
                        KnowledgeExternalSourceCollectionStateRecord.source_id.in_(source_ids)
                    )
                )
            }
            pages_by_source: dict[str, list[KnowledgeExternalSourcePageStateRecord]] = {
                source_id: [] for source_id in source_ids
            }
            for record in session.scalars(
                select(KnowledgeExternalSourcePageStateRecord).where(
                    KnowledgeExternalSourcePageStateRecord.source_id.in_(source_ids)
                )
            ):
                pages_by_source.setdefault(record.source_id, []).append(record)
            return {
                source_id: SiteCollectionSyncSummary(
                    source_id=source_id,
                    last_completed_at=(
                        collections[source_id].last_completed_at
                        if source_id in collections
                        else None
                    ),
                    available_page_count=sum(page.status == "available" for page in pages),
                    removed_page_count=sum(page.status == "removed" for page in pages),
                    checked_page_count=sum(page.last_checked_at is not None for page in pages),
                    failed_page_count=sum(page.last_error_code is not None for page in pages),
                )
                for source_id, pages in pages_by_source.items()
            }

    def record_page_outcome(
        self,
        *,
        source_id: str,
        locator: str,
        outcome: str,
        content_sha256: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        error_code: str | None = None,
        checked_at: datetime | None = None,
    ) -> None:
        if outcome not in {"changed", "unchanged", "not_modified", "failed"}:
            raise ValueError("Site Collection page outcome is invalid.")
        with self.database.session() as session:
            canonical = canonical_public_https_locator(locator)
            record = session.scalar(
                select(KnowledgeExternalSourcePageStateRecord).where(
                    KnowledgeExternalSourcePageStateRecord.source_id == source_id,
                    KnowledgeExternalSourcePageStateRecord.locator == canonical,
                )
            )
            if record is None:
                raise KeyError("site_collection_page")
            record.last_checked_at = checked_at or datetime.now(UTC)
            record.last_error_code = error_code if outcome == "failed" else None
            if etag is not None:
                record.etag = normalized_website_validator(etag)
            if last_modified is not None:
                record.last_modified = normalized_website_validator(last_modified)
            if content_sha256 is not None:
                record.content_sha256 = content_sha256
            session.commit()

    def complete_generation(self, *, source_id: str, generation: int) -> tuple[str, ...]:
        """Mark only pages absent from a fully parsed manifest as removed."""

        with self.database.session() as session:
            state = session.get(KnowledgeExternalSourceCollectionStateRecord, source_id)
            if state is None or state.discovery_generation != generation:
                raise ValueError("Site Collection generation is stale.")
            removed = list(
                session.scalars(
                    select(KnowledgeExternalSourcePageStateRecord).where(
                        KnowledgeExternalSourcePageStateRecord.source_id == source_id,
                        KnowledgeExternalSourcePageStateRecord.status == "available",
                        KnowledgeExternalSourcePageStateRecord.last_seen_generation != generation,
                    )
                )
            )
            for record in removed:
                record.status = "removed"
            state.last_completed_at = datetime.now(UTC)
            session.commit()
            return tuple(sorted(record.locator for record in removed))

    @staticmethod
    def _require_collection_source(session: Session, source_id: str) -> KnowledgeSourceRecord:
        record = session.get(KnowledgeSourceRecord, source_id)
        if record is None:
            raise KeyError("source")
        if record.source_type != WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE:
            raise ValueError("Site Collection state requires a Site Collection Source.")
        return record

    @staticmethod
    def _view(record: KnowledgeExternalSourcePageStateRecord) -> SiteCollectionPageState:
        return SiteCollectionPageState(
            locator=record.locator,
            discovery_kind=record.discovery_kind,
            discovered_from_locator=record.discovered_from_locator,
            etag=record.etag,
            last_modified=record.last_modified,
            content_sha256=record.content_sha256,
            status=record.status,
        )


__all__ = [
    "KnowledgeFabricSiteCollectionRepository",
    "SiteCollectionPageState",
    "SiteCollectionSyncSummary",
]
