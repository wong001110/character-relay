"""Worker-only conditional sync orchestration for a public Website Source."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from echo_masque.knowledge_fabric_external_policy import (
    WebsiteSourceRejected,
    canonical_public_https_locator,
    conditional_request_headers,
    normalized_website_validator,
    website_response_error_code,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_fabric_website_adapter import (
    KnowledgeFabricWebsiteAdapter,
    WebsiteResponseInput,
    WebsiteResponseRejected,
)
from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)


@dataclass(frozen=True, slots=True)
class WebsiteFetchResponse:
    status_code: int
    content: bytes
    headers: Mapping[str, str]


class WebsiteFetcher(Protocol):
    """An approved worker transport; Phase 9a deliberately supplies no default implementation."""

    async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse: ...


@dataclass(frozen=True, slots=True)
class WebsiteSyncResult:
    outcome: str
    error_code: str | None = None
    source_version_id: str | None = None


class KnowledgeFabricWebsiteSyncService:
    """Apply a bounded Website fetch outcome without expanding runtime/web-client authority."""

    def __init__(
        self,
        *,
        sync_repository: KnowledgeFabricExternalSyncRepository,
        ingestion_service: KnowledgeFabricIngestionService,
        fetcher: WebsiteFetcher,
        url_guard: PublicUrlGuard | None = None,
        adapter: KnowledgeFabricWebsiteAdapter | None = None,
    ) -> None:
        self.sync_repository = sync_repository
        self.ingestion_service = ingestion_service
        self.fetcher = fetcher
        self.url_guard = url_guard or PublicUrlGuard()
        self.adapter = adapter or KnowledgeFabricWebsiteAdapter()

    async def sync(
        self,
        source_id: str,
        *,
        checked_at: datetime | None = None,
    ) -> WebsiteSyncResult:
        """Fetch exactly one registered locator and publish only a valid changed response."""

        now = checked_at or datetime.now(UTC)
        source = self.sync_repository.require_website_source(source_id)
        try:
            locator = canonical_public_https_locator(source.locator)
            if locator != source.locator:
                raise WebsiteSourceRejected("Website locator is not canonical.")
            await self.url_guard.validate(locator)
        except (PublicUrlRejected, WebsiteSourceRejected):
            return self._failure(source_id=source_id, error_code="source_rejected", checked_at=now)

        state = self.sync_repository.get_state(source_id)
        try:
            response = await self.fetcher.fetch(
                url=locator,
                headers=conditional_request_headers(
                    etag=state.etag if state is not None else None,
                    last_modified=state.last_modified if state is not None else None,
                ),
            )
        except Exception:
            return self._failure(source_id=source_id, error_code="fetch_failed", checked_at=now)

        content_type = response.headers.get("content-type", "")
        error_code = website_response_error_code(
            status_code=response.status_code,
            content_type=content_type,
            content_size=len(response.content),
        )
        if error_code == "not_modified":
            self.sync_repository.record_outcome(
                source_id=source_id,
                outcome="not_modified",
                checked_at=now,
            )
            return WebsiteSyncResult(outcome="not_modified")
        if error_code is not None:
            return self._failure(source_id=source_id, error_code=error_code, checked_at=now)

        try:
            etag = normalized_website_validator(response.headers.get("etag"))
            last_modified = normalized_website_validator(response.headers.get("last-modified"))
            snapshot = self.adapter.build_snapshot(
                WebsiteResponseInput(
                    source_id=source_id,
                    locator=locator,
                    content=response.content,
                    content_type=content_type,
                    fetched_at=now,
                )
            )
        except WebsiteSourceRejected:
            return self._failure(
                source_id=source_id,
                error_code="validator_rejected",
                checked_at=now,
            )
        except WebsiteResponseRejected:
            return self._failure(source_id=source_id, error_code="invalid_encoding", checked_at=now)
        existing = self.ingestion_service.repository.get_source_version_by_key(
            source_id=source_id,
            version_key=snapshot.version_key,
        )
        version = self.ingestion_service.ingest_snapshot(snapshot)
        outcome = "unchanged" if existing is not None else "changed"
        self.sync_repository.record_outcome(
            source_id=source_id,
            outcome=outcome,
            etag=etag,
            last_modified=last_modified,
            changed=outcome == "changed",
            checked_at=now,
        )
        return WebsiteSyncResult(outcome=outcome, source_version_id=version.id)

    def _failure(
        self,
        *,
        source_id: str,
        error_code: str,
        checked_at: datetime,
    ) -> WebsiteSyncResult:
        self.sync_repository.record_outcome(
            source_id=source_id,
            outcome="failed",
            error_code=error_code,
            checked_at=checked_at,
        )
        return WebsiteSyncResult(outcome="failed", error_code=error_code)


__all__ = [
    "KnowledgeFabricWebsiteSyncService",
    "WebsiteFetchResponse",
    "WebsiteFetcher",
    "WebsiteSyncResult",
]
