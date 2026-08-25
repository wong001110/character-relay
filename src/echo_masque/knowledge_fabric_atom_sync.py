"""Conditional, worker-only Atom 1.0 sync orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from echo_masque.knowledge_fabric_atom_adapter import (
    AtomResponseInput,
    AtomResponseRejected,
    KnowledgeFabricAtomAdapter,
)
from echo_masque.knowledge_fabric_atom_policy import atom_response_error_code
from echo_masque.knowledge_fabric_external_policy import (
    ATOM_PUBLIC_HTTPS_SOURCE_TYPE,
    WebsiteSourceRejected,
    canonical_public_https_locator,
    conditional_request_headers,
    normalized_website_validator,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_fabric_website_sync import WebsiteFetcher, WebsiteSyncResult
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)

_ATOM_SOURCE_TYPES = frozenset({ATOM_PUBLIC_HTTPS_SOURCE_TYPE})


class KnowledgeFabricAtomSyncService:
    def __init__(
        self,
        *,
        sync_repository: KnowledgeFabricExternalSyncRepository,
        ingestion_service: KnowledgeFabricIngestionService,
        fetcher: WebsiteFetcher,
        adapter: KnowledgeFabricAtomAdapter | None = None,
    ) -> None:
        self.sync_repository = sync_repository
        self.ingestion_service = ingestion_service
        self.fetcher = fetcher
        self.adapter = adapter or KnowledgeFabricAtomAdapter()

    async def sync(
        self, source_id: str, *, checked_at: datetime | None = None
    ) -> WebsiteSyncResult:
        now = checked_at or datetime.now(UTC)
        source = self.sync_repository.require_public_https_source(
            source_id,
            allowed_source_types=_ATOM_SOURCE_TYPES,
        )
        try:
            locator = canonical_public_https_locator(source.locator)
            if locator != source.locator:
                raise WebsiteSourceRejected("Atom locator is not canonical.")
        except WebsiteSourceRejected:
            return self._failure(source_id, "source_rejected", now)
        state = self.sync_repository.get_state(source_id)
        headers = conditional_request_headers(
            etag=state.etag if state else None,
            last_modified=state.last_modified if state else None,
        )
        headers["Accept"] = "application/atom+xml,application/xml,text/xml;q=0.9"
        try:
            response = await self.fetcher.fetch(url=locator, headers=headers)
        except Exception:
            return self._failure(source_id, "fetch_failed", now)
        content_type = response.headers.get("content-type", "")
        error = atom_response_error_code(
            status_code=response.status_code,
            content_type=content_type,
            content_size=len(response.content),
        )
        if error == "not_modified":
            self.sync_repository.record_outcome(
                source_id=source_id,
                outcome="not_modified",
                checked_at=now,
                allowed_source_types=_ATOM_SOURCE_TYPES,
            )
            return WebsiteSyncResult(outcome="not_modified")
        if error is not None:
            return self._failure(source_id, error, now)
        try:
            snapshot = self.adapter.build_snapshot(
                AtomResponseInput(
                    source_id=source_id,
                    locator=locator,
                    content=response.content,
                    content_type=content_type,
                    fetched_at=now,
                )
            )
            etag = normalized_website_validator(response.headers.get("etag"))
            modified = normalized_website_validator(response.headers.get("last-modified"))
        except (AtomResponseRejected, WebsiteSourceRejected):
            return self._failure(source_id, "invalid_feed", now)
        existing = self.ingestion_service.repository.get_source_version_by_key(
            source_id=source_id,
            version_key=snapshot.version_key,
        )
        version = self.ingestion_service.ingest_snapshot(snapshot)
        outcome = "unchanged" if existing else "changed"
        self.sync_repository.record_outcome(
            source_id=source_id,
            outcome=outcome,
            etag=etag,
            last_modified=modified,
            changed=outcome == "changed",
            checked_at=now,
            allowed_source_types=_ATOM_SOURCE_TYPES,
        )
        return WebsiteSyncResult(outcome=outcome, source_version_id=version.id)

    def _failure(
        self, source_id: str, error_code: str, checked_at: datetime
    ) -> WebsiteSyncResult:
        self.sync_repository.record_outcome(
            source_id=source_id,
            outcome="failed",
            error_code=error_code,
            checked_at=checked_at,
            allowed_source_types=_ATOM_SOURCE_TYPES,
        )
        return WebsiteSyncResult(outcome="failed", error_code=error_code)


__all__ = ["KnowledgeFabricAtomSyncService"]
