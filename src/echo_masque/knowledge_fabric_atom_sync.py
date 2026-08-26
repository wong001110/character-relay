"""Conditional, worker-only Atom 1.0 sync orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import replace
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
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeExternalScheduleClaimLost,
)
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    ExternalSourceScheduleClaim,
)
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
        self,
        source_id: str,
        *,
        checked_at: datetime | None = None,
        external_schedule_lease_token: str | None = None,
    ) -> WebsiteSyncResult:
        now = checked_at or datetime.now(UTC)
        if not await self._schedule_claim_is_current(
            source_id=source_id,
            lease_token=external_schedule_lease_token,
            checked_at=now,
        ):
            return WebsiteSyncResult(outcome="stale")
        source = await asyncio.to_thread(
            self.sync_repository.require_public_https_source,
            source_id,
            allowed_source_types=_ATOM_SOURCE_TYPES,
        )
        try:
            locator = canonical_public_https_locator(source.locator)
            if locator != source.locator:
                raise WebsiteSourceRejected("Atom locator is not canonical.")
        except WebsiteSourceRejected:
            return await self._failure(
                source_id,
                "source_rejected",
                now,
                external_schedule_lease_token=external_schedule_lease_token,
            )
        state = await asyncio.to_thread(self.sync_repository.get_state, source_id)
        headers = conditional_request_headers(
            etag=state.etag if state else None,
            last_modified=state.last_modified if state else None,
        )
        headers["Accept"] = "application/atom+xml,application/xml,text/xml;q=0.9"
        try:
            response = await self.fetcher.fetch(url=locator, headers=headers)
        except Exception:
            return await self._failure(
                source_id,
                "fetch_failed",
                now,
                external_schedule_lease_token=external_schedule_lease_token,
            )
        content_type = response.headers.get("content-type", "")
        error = atom_response_error_code(
            status_code=response.status_code,
            content_type=content_type,
            content_size=len(response.content),
        )
        if error == "not_modified":
            recorded = await asyncio.to_thread(
                self.sync_repository.record_outcome,
                source_id=source_id,
                outcome="not_modified",
                checked_at=now,
                schedule_lease_token=external_schedule_lease_token,
                allowed_source_types=_ATOM_SOURCE_TYPES,
            )
            if recorded is None:
                return WebsiteSyncResult(outcome="stale")
            return WebsiteSyncResult(outcome="not_modified")
        if error is not None:
            return await self._failure(
                source_id,
                error,
                now,
                external_schedule_lease_token=external_schedule_lease_token,
            )
        try:
            snapshot = await asyncio.to_thread(
                self.adapter.build_snapshot,
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
            return await self._failure(
                source_id,
                "invalid_feed",
                now,
                external_schedule_lease_token=external_schedule_lease_token,
            )
        if not await self._schedule_claim_is_current(
            source_id=source_id,
            lease_token=external_schedule_lease_token,
            checked_at=now,
        ):
            return WebsiteSyncResult(outcome="stale")
        existing = await asyncio.to_thread(
            self.ingestion_service.repository.get_source_version_by_key,
            source_id=source_id,
            version_key=snapshot.version_key,
        )
        if external_schedule_lease_token is not None:
            snapshot = replace(
                snapshot,
                external_schedule_lease_token=external_schedule_lease_token,
            )
        try:
            version = await asyncio.to_thread(self.ingestion_service.ingest_snapshot, snapshot)
        except KnowledgeExternalScheduleClaimLost:
            return WebsiteSyncResult(outcome="stale")
        outcome = "unchanged" if existing else "changed"
        recorded = await asyncio.to_thread(
            self.sync_repository.record_outcome,
            source_id=source_id,
            outcome=outcome,
            etag=etag,
            last_modified=modified,
            changed=outcome == "changed",
            checked_at=now,
            schedule_lease_token=external_schedule_lease_token,
            allowed_source_types=_ATOM_SOURCE_TYPES,
        )
        if recorded is None:
            return WebsiteSyncResult(outcome="stale")
        return WebsiteSyncResult(outcome=outcome, source_version_id=version.id)

    async def sync_claim(self, claim: ExternalSourceScheduleClaim) -> WebsiteSyncResult:
        return await self.sync(
            claim.source_id,
            external_schedule_lease_token=claim.lease_token,
        )

    async def _failure(
        self,
        source_id: str,
        error_code: str,
        checked_at: datetime,
        *,
        external_schedule_lease_token: str | None,
    ) -> WebsiteSyncResult:
        recorded = await asyncio.to_thread(
            self.sync_repository.record_outcome,
            source_id=source_id,
            outcome="failed",
            error_code=error_code,
            checked_at=checked_at,
            schedule_lease_token=external_schedule_lease_token,
            allowed_source_types=_ATOM_SOURCE_TYPES,
        )
        if recorded is None:
            return WebsiteSyncResult(outcome="stale")
        return WebsiteSyncResult(outcome="failed", error_code=error_code)

    async def _schedule_claim_is_current(
        self,
        *,
        source_id: str,
        lease_token: str | None,
        checked_at: datetime,
    ) -> bool:
        if lease_token is None:
            return True
        return await asyncio.to_thread(
            self.sync_repository.schedule_claim_is_current,
            source_id=source_id,
            lease_token=lease_token,
            now=checked_at,
        )


__all__ = ["KnowledgeFabricAtomSyncService"]
