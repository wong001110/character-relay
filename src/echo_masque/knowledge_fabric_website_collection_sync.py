"""Worker-only bounded synchronization for a public Website Collection Source."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256

from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
    WebsiteSourceRejected,
    canonical_public_https_locator,
    conditional_request_headers,
    normalized_website_validator,
    website_response_error_code,
)
from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotAssetInput,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_fabric_website_collection_adapter import (
    KnowledgeFabricWebsiteCollectionAdapter,
    WebsiteCollectionPageInput,
    WebsiteCollectionResponseRejected,
)
from echo_masque.knowledge_fabric_website_collection_policy import (
    WebsiteCollectionRejected,
    discover_collection_page_locators,
)
from echo_masque.knowledge_fabric_website_image_policy import (
    WebsiteCollectionImageRejected,
    discover_collection_image_candidates,
    website_collection_image_response_error_code,
)
from echo_masque.knowledge_fabric_website_sitemap_policy import (
    MAX_SITEMAP_DOCUMENTS,
    MAX_SITEMAP_PAGES,
    WebsiteSitemapRejected,
    default_sitemap_locator,
    parse_sitemap,
    sitemap_response_error_code,
)
from echo_masque.knowledge_fabric_website_sync import (
    WebsiteFetcher,
    WebsiteFetchResponse,
    WebsiteSyncResult,
)
from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeExternalScheduleClaimLost,
)
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    ExternalSourceScheduleClaim,
)
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)
from echo_masque.persistence.knowledge_fabric_site_collection_repository import (
    KnowledgeFabricSiteCollectionRepository,
    SiteCollectionPageState,
)

_COLLECTION_SOURCE_TYPES = frozenset({WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE})


@dataclass(frozen=True, slots=True)
class _DiscoveredPage:
    locator: str
    discovery_kind: str
    discovered_from_locator: str


@dataclass(frozen=True, slots=True)
class KnowledgeFabricWebsiteCollectionSyncService:
    """Synchronize a complete admitted manifest as independent page deltas.

    Immutable Source Versions retain content provenance. This worker persists only discovery and
    HTTP validators, so an incomplete generation cannot retract current source evidence.
    """

    sync_repository: KnowledgeFabricExternalSyncRepository
    collection_repository: KnowledgeFabricSiteCollectionRepository
    ingestion_service: KnowledgeFabricIngestionService
    fetcher: WebsiteFetcher
    url_guard: PublicUrlGuard | None = None
    adapter: KnowledgeFabricWebsiteCollectionAdapter | None = None

    def __post_init__(self) -> None:
        if self.adapter is None:
            object.__setattr__(self, "adapter", KnowledgeFabricWebsiteCollectionAdapter())

    async def sync(
        self,
        source_id: str,
        *,
        checked_at: datetime | None = None,
        external_schedule_lease_token: str | None = None,
    ) -> WebsiteSyncResult:
        now = checked_at or datetime.now(UTC)
        if not await self._schedule_claim_is_current(source_id, external_schedule_lease_token, now):
            return WebsiteSyncResult(outcome="stale")
        source = await asyncio.to_thread(
            self.sync_repository.require_public_https_source,
            source_id,
            allowed_source_types=_COLLECTION_SOURCE_TYPES,
        )
        try:
            root = canonical_public_https_locator(source.locator)
            if root != source.locator:
                raise WebsiteSourceRejected("Website collection locator is not canonical.")
            await self._validate_url(root)
        except (PublicUrlRejected, WebsiteSourceRejected):
            return await self._failure(
                source_id, "source_rejected", now, external_schedule_lease_token
            )
        root_response = await self._fetch_root(root, source_id, now, external_schedule_lease_token)
        if isinstance(root_response, WebsiteSyncResult):
            return root_response
        try:
            discovered = await self._discover_pages(root, root_response)
        except (PublicUrlRejected, WebsiteCollectionRejected, WebsiteSitemapRejected):
            return await self._failure(
                source_id, "discovery_rejected", now, external_schedule_lease_token
            )
        if not await self._schedule_claim_is_current(source_id, external_schedule_lease_token, now):
            return WebsiteSyncResult(outcome="stale")
        generation = await asyncio.to_thread(self.collection_repository.begin_generation, source_id)
        pages = await asyncio.to_thread(
            self.collection_repository.reconcile_discovered_pages,
            source_id=source_id,
            generation=generation,
            pages=tuple(
                (item.locator, item.discovery_kind, item.discovered_from_locator)
                for item in discovered
            ),
        )
        changed = False
        checked_changed = False
        latest_version_id: str | None = None
        changed_page_count = 0
        unchanged_page_count = 0
        admitted_image_count = 0
        for page in pages:
            result = await self._sync_page(
                source_id=source_id,
                page=page,
                checked_at=now,
                external_schedule_lease_token=external_schedule_lease_token,
            )
            if result.outcome in {"failed", "stale"}:
                return replace(
                    result,
                    discovered_page_count=len(pages),
                    changed_page_count=changed_page_count,
                    unchanged_page_count=unchanged_page_count,
                    failed_page_count=1 if result.outcome == "failed" else 0,
                    admitted_image_count=admitted_image_count,
                )
            changed = changed or result.outcome == "changed"
            checked_changed = checked_changed or result.outcome == "unchanged"
            changed_page_count += result.changed_page_count
            unchanged_page_count += result.unchanged_page_count
            admitted_image_count += result.admitted_image_count
            latest_version_id = result.source_version_id or latest_version_id
        if not await self._schedule_claim_is_current(source_id, external_schedule_lease_token, now):
            return WebsiteSyncResult(
                outcome="stale",
                discovered_page_count=len(pages),
                changed_page_count=changed_page_count,
                unchanged_page_count=unchanged_page_count,
                admitted_image_count=admitted_image_count,
            )
        removed = await asyncio.to_thread(
            self.collection_repository.complete_generation,
            source_id=source_id,
            generation=generation,
        )
        if removed:
            try:
                assert self.adapter is not None
                removal = self.adapter.build_removal_snapshot(
                    source_id=source_id,
                    root_locator=root,
                    removed_entry_locators=removed,
                    fetched_at=now,
                )
                version = await asyncio.to_thread(
                    self.ingestion_service.ingest_snapshot,
                    self._with_lease(removal, external_schedule_lease_token),
                )
            except KnowledgeExternalScheduleClaimLost:
                return WebsiteSyncResult(
                    outcome="stale",
                    discovered_page_count=len(pages),
                    changed_page_count=changed_page_count,
                    unchanged_page_count=unchanged_page_count,
                    admitted_image_count=admitted_image_count,
                )
            latest_version_id = version.id
            changed = True
        outcome = "changed" if changed else "unchanged" if checked_changed else "not_modified"
        recorded = await asyncio.to_thread(
            self.sync_repository.record_outcome,
            source_id=source_id,
            outcome=outcome,
            etag=normalized_website_validator(root_response.headers.get("etag")),
            last_modified=normalized_website_validator(root_response.headers.get("last-modified")),
            changed=changed,
            checked_at=now,
            schedule_lease_token=external_schedule_lease_token,
            allowed_source_types=_COLLECTION_SOURCE_TYPES,
        )
        if recorded is None:
            return WebsiteSyncResult(
                outcome="stale",
                discovered_page_count=len(pages),
                changed_page_count=changed_page_count,
                unchanged_page_count=unchanged_page_count,
                admitted_image_count=admitted_image_count,
            )
        return WebsiteSyncResult(
            outcome=outcome,
            source_version_id=latest_version_id,
            discovered_page_count=len(pages),
            changed_page_count=changed_page_count,
            unchanged_page_count=unchanged_page_count,
            removed_page_count=len(removed),
            admitted_image_count=admitted_image_count,
        )

    async def sync_claim(self, claim: ExternalSourceScheduleClaim) -> WebsiteSyncResult:
        return await self.sync(claim.source_id, external_schedule_lease_token=claim.lease_token)

    async def _fetch_root(
        self, root: str, source_id: str, checked_at: datetime, lease_token: str | None
    ) -> WebsiteFetchResponse | WebsiteSyncResult:
        state = await asyncio.to_thread(self.sync_repository.get_state, source_id)
        try:
            response = await self.fetcher.fetch(
                url=root,
                headers=conditional_request_headers(
                    etag=state.etag if state is not None else None,
                    last_modified=state.last_modified if state is not None else None,
                ),
            )
        except Exception:
            return await self._failure(source_id, "fetch_failed", checked_at, lease_token)
        error = website_response_error_code(
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            content_size=len(response.content),
        )
        if error not in {None, "not_modified"}:
            assert error is not None
            return await self._failure(source_id, error, checked_at, lease_token)
        return response

    async def _discover_pages(
        self, root: str, root_response: WebsiteFetchResponse
    ) -> tuple[_DiscoveredPage, ...]:
        """Prefer a complete same-origin sitemap, retaining a bounded root-link fallback."""

        sitemap = default_sitemap_locator(root)
        try:
            sitemap_pages = await self._discover_sitemap_pages(root, sitemap)
        except _SitemapUnavailable:
            root_for_links = root_response
            if root_response.status_code == 304:
                root_for_links = await self.fetcher.fetch(
                    url=root,
                    headers=conditional_request_headers(etag=None, last_modified=None),
                )
            error = website_response_error_code(
                status_code=root_for_links.status_code,
                content_type=root_for_links.headers.get("content-type", ""),
                content_size=len(root_for_links.content),
            )
            content_type = root_for_links.headers.get("content-type", "").casefold()
            if error is not None or not content_type.startswith("text/html"):
                raise WebsiteCollectionRejected(
                    "Root link discovery requires a valid HTML response."
                ) from None
            return tuple(
                _DiscoveredPage(item, "root_link", root)
                for item in discover_collection_page_locators(
                    root_locator=root, content=root_for_links.content
                )
            )
        return tuple(
            _DiscoveredPage(item, "sitemap", sitemap) for item in sorted({root, *sitemap_pages})
        )

    async def _discover_sitemap_pages(self, root: str, sitemap: str) -> tuple[str, ...]:
        pending = [sitemap]
        documents_seen: set[str] = set()
        pages: set[str] = set()
        while pending:
            locator = pending.pop(0)
            if locator in documents_seen:
                continue
            if len(documents_seen) >= MAX_SITEMAP_DOCUMENTS:
                raise WebsiteSitemapRejected("Sitemap index exceeds the document limit.")
            await self._validate_url(locator)
            response = await self.fetcher.fetch(
                url=locator,
                headers={"Accept": "application/xml,text/xml;q=0.9"},
            )
            if response.status_code in {404, 410} and not documents_seen:
                raise _SitemapUnavailable()
            error = sitemap_response_error_code(
                status_code=response.status_code,
                content_type=response.headers.get("content-type", ""),
                content_size=len(response.content),
            )
            if error is not None:
                raise WebsiteSitemapRejected("Sitemap response is not admissible.")
            manifest = parse_sitemap(
                sitemap_locator=locator,
                content=response.content,
                root_locator=root,
            )
            documents_seen.add(locator)
            pages.update(manifest.pages)
            if len(pages) > MAX_SITEMAP_PAGES:
                raise WebsiteSitemapRejected("Sitemap exceeds the page limit.")
            pending.extend(item for item in manifest.child_sitemaps if item not in documents_seen)
        return tuple(sorted(pages))

    async def _sync_page(
        self,
        *,
        source_id: str,
        page: SiteCollectionPageState,
        checked_at: datetime,
        external_schedule_lease_token: str | None,
    ) -> WebsiteSyncResult:
        try:
            await self._validate_url(page.locator)
            response = await self.fetcher.fetch(
                url=page.locator,
                headers=conditional_request_headers(
                    etag=page.etag,
                    last_modified=page.last_modified,
                ),
            )
        except (Exception, PublicUrlRejected):
            await asyncio.to_thread(
                self.collection_repository.record_page_outcome,
                source_id=source_id,
                locator=page.locator,
                outcome="failed",
                error_code="fetch_failed",
                checked_at=checked_at,
            )
            result = await self._failure(
                source_id, "page_failed", checked_at, external_schedule_lease_token
            )
            return replace(result, failed_page_count=1)
        error = website_response_error_code(
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            content_size=len(response.content),
        )
        if error == "not_modified":
            await asyncio.to_thread(
                self.collection_repository.record_page_outcome,
                source_id=source_id,
                locator=page.locator,
                outcome="not_modified",
                checked_at=checked_at,
            )
            return WebsiteSyncResult(outcome="not_modified")
        if error is not None:
            await asyncio.to_thread(
                self.collection_repository.record_page_outcome,
                source_id=source_id,
                locator=page.locator,
                outcome="failed",
                error_code=error,
                checked_at=checked_at,
            )
            result = await self._failure(
                source_id, "page_failed", checked_at, external_schedule_lease_token
            )
            return replace(result, failed_page_count=1)
        try:
            assert self.adapter is not None
            snapshot = self.adapter.build_page_snapshot(
                source_id=source_id,
                page=WebsiteCollectionPageInput(
                    locator=page.locator,
                    content=response.content,
                    content_type=response.headers.get("content-type", ""),
                ),
                fetched_at=checked_at,
            )
            assets = await self._fetch_page_images(
                page_locator=page.locator,
                content=response.content,
            )
            snapshot = replace(snapshot, assets=assets)
        except (WebsiteCollectionResponseRejected, WebsiteSourceRejected):
            result = await self._failure(
                source_id, "collection_rejected", checked_at, external_schedule_lease_token
            )
            return replace(result, failed_page_count=1)
        existing = await asyncio.to_thread(
            self.ingestion_service.repository.get_source_version_by_key,
            source_id=source_id,
            version_key=snapshot.version_key,
        )
        outcome = "unchanged" if existing is not None else "changed"
        version_id: str | None = None
        if existing is None:
            if not await self._schedule_claim_is_current(
                source_id, external_schedule_lease_token, checked_at
            ):
                return WebsiteSyncResult(outcome="stale")
            try:
                version = await asyncio.to_thread(
                    self.ingestion_service.ingest_snapshot,
                    self._with_lease(snapshot, external_schedule_lease_token),
                )
            except KnowledgeExternalScheduleClaimLost:
                return WebsiteSyncResult(outcome="stale")
            version_id = version.id
        await asyncio.to_thread(
            self.collection_repository.record_page_outcome,
            source_id=source_id,
            locator=page.locator,
            outcome=outcome,
            content_sha256=sha256(response.content).hexdigest(),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            checked_at=checked_at,
        )
        return WebsiteSyncResult(
            outcome=outcome,
            source_version_id=version_id,
            changed_page_count=1 if outcome == "changed" else 0,
            unchanged_page_count=1 if outcome == "unchanged" else 0,
            admitted_image_count=len(assets),
        )

    async def _fetch_page_images(
        self,
        *,
        page_locator: str,
        content: bytes,
    ) -> tuple[SourceSnapshotAssetInput, ...]:
        """Fetch admitted raster candidates only as private provenance assets."""

        try:
            candidates = discover_collection_image_candidates(
                page_locator=page_locator,
                content=content,
            )
        except WebsiteCollectionImageRejected:
            return ()
        assets: list[SourceSnapshotAssetInput] = []
        for candidate in candidates:
            try:
                await self._validate_url(candidate.locator)
                response = await self.fetcher.fetch(
                    url=candidate.locator,
                    headers={"Accept": "image/png,image/jpeg,image/gif,image/webp"},
                )
            except (Exception, PublicUrlRejected):
                continue
            content_type = response.headers.get("content-type", "")
            if website_collection_image_response_error_code(
                status_code=response.status_code,
                content_type=content_type,
                content=response.content,
            ) is not None:
                continue
            assets.append(
                SourceSnapshotAssetInput(
                    document_locator=page_locator,
                    structural_path=candidate.structural_path,
                    asset_type="image",
                    artifact_content=response.content,
                    artifact_content_type=content_type,
                    evidence_locator=f"{page_locator}#{candidate.structural_path}",
                    evidence_type="image",
                    text_content=candidate.alt_text,
                    coordinates={"image_locator": candidate.locator, "alt": candidate.alt_text},
                )
            )
        return tuple(assets)

    async def _validate_url(self, locator: str) -> None:
        if self.url_guard is not None:
            await self.url_guard.validate(locator)

    @staticmethod
    def _with_lease(
        snapshot: SourceSnapshotIngestionRequest, lease_token: str | None
    ) -> SourceSnapshotIngestionRequest:
        if lease_token is None:
            return snapshot
        return replace(snapshot, external_schedule_lease_token=lease_token)

    async def _record_not_modified(
        self, source_id: str, checked_at: datetime, lease_token: str | None
    ) -> WebsiteSyncResult:
        recorded = await asyncio.to_thread(
            self.sync_repository.record_outcome,
            source_id=source_id,
            outcome="not_modified",
            checked_at=checked_at,
            schedule_lease_token=lease_token,
            allowed_source_types=_COLLECTION_SOURCE_TYPES,
        )
        return WebsiteSyncResult(outcome="not_modified" if recorded is not None else "stale")

    async def _failure(
        self, source_id: str, error_code: str, checked_at: datetime, lease_token: str | None
    ) -> WebsiteSyncResult:
        recorded = await asyncio.to_thread(
            self.sync_repository.record_outcome,
            source_id=source_id,
            outcome="failed",
            error_code=error_code,
            checked_at=checked_at,
            schedule_lease_token=lease_token,
            allowed_source_types=_COLLECTION_SOURCE_TYPES,
        )
        if recorded is None:
            return WebsiteSyncResult(outcome="stale")
        return WebsiteSyncResult(outcome="failed", error_code=error_code)

    async def _schedule_claim_is_current(
        self, source_id: str, lease_token: str | None, checked_at: datetime
    ) -> bool:
        if lease_token is None:
            return True
        return await asyncio.to_thread(
            self.sync_repository.schedule_claim_is_current,
            source_id=source_id,
            lease_token=lease_token,
            now=checked_at,
        )


class _SitemapUnavailable(Exception):
    """The conventional sitemap endpoint is absent, so bounded root-link discovery may run."""


__all__ = ["KnowledgeFabricWebsiteCollectionSyncService"]
