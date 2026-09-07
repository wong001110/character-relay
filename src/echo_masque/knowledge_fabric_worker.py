"""Dedicated process entry point for Knowledge Fabric maintenance."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from echo_masque.browser_runtime import BrowserCapabilityManager, BrowserRuntimeSettings
from echo_masque.config import Settings, get_settings
from echo_masque.knowledge_fabric_atom_sync import KnowledgeFabricAtomSyncService
from echo_masque.knowledge_fabric_background_runtime import KnowledgeFabricBackgroundRuntime
from echo_masque.knowledge_fabric_external_policy import (
    ATOM_PUBLIC_HTTPS_SOURCE_TYPE,
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
    WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
)
from echo_masque.knowledge_fabric_external_sync_report_retention import (
    KnowledgeFabricExternalSyncReportRetentionService,
)
from echo_masque.knowledge_fabric_external_sync_scheduler import (
    KnowledgeFabricExternalSyncScheduler,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_fabric_invalidation_worker import KnowledgeFabricInvalidationWorker
from echo_masque.knowledge_fabric_pinned_fetcher import (
    AsyncioPinnedHttpsDialTransport,
    PinnedPublicHttpsFetcher,
)
from echo_masque.knowledge_fabric_website_collection_sync import (
    KnowledgeFabricWebsiteCollectionSyncService,
)
from echo_masque.knowledge_fabric_website_sync import KnowledgeFabricWebsiteSyncService
from echo_masque.knowledge_object_storage import (
    KnowledgeObjectStorage,
    object_storage_from_settings,
)
from echo_masque.persistence import Database, inspect_storage
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    KnowledgeFabricExternalScheduleRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_run_repository import (
    KnowledgeFabricExternalSyncRunRepository,
)
from echo_masque.persistence.knowledge_fabric_index_repository import KnowledgeFabricIndexRepository
from echo_masque.persistence.knowledge_fabric_invalidation_repository import (
    KnowledgeFabricInvalidationRepository,
)
from echo_masque.persistence.knowledge_fabric_projection_repository import (
    KnowledgeFabricProjectionRepository,
)
from echo_masque.persistence.knowledge_fabric_site_collection_repository import (
    KnowledgeFabricSiteCollectionRepository,
)


@dataclass(slots=True)
class KnowledgeFabricWorkerRuntime:
    """The only services a dedicated Fabric process owns."""

    database: Database
    object_storage: KnowledgeObjectStorage
    browser_runtime: BrowserCapabilityManager
    background_runtime: KnowledgeFabricBackgroundRuntime


def compose_worker_runtime(settings: Settings) -> KnowledgeFabricWorkerRuntime:
    """Build Fabric maintenance without composing the HTTP API or running global recovery.

    ``Database.initialize`` provides schema setup only. Recovery is an explicit offline operation
    because this process shares durable records with API and connector processes.
    """

    # Match the HTTP service's fail-closed production topology guard before an engine, schema,
    # browser, or object-storage client can be created.
    inspect_storage(settings)
    database = Database(settings.database_url)
    database.initialize()
    object_storage = object_storage_from_settings(settings)
    browser_runtime = BrowserCapabilityManager(
        BrowserRuntimeSettings(
            enabled=settings.browser_tools_enabled,
            page_idle_seconds=settings.browser_page_idle_seconds,
            context_idle_seconds=settings.browser_context_idle_seconds,
            browser_idle_seconds=settings.browser_idle_seconds,
            browser_max_lifetime_seconds=settings.browser_max_lifetime_seconds,
            browser_max_operations=settings.browser_max_operations,
            max_concurrent_contexts=settings.browser_max_concurrent_contexts,
            navigation_timeout_ms=settings.browser_navigation_timeout_ms,
        )
    )
    content = KnowledgeFabricContentRepository(database, object_storage=object_storage)
    ingestion = KnowledgeFabricIngestionService(
        content,
        object_storage,
        object_key_prefix=settings.knowledge_object_storage_prefix,
    )
    external_sync = KnowledgeFabricExternalSyncRepository(database)
    schedules = KnowledgeFabricExternalScheduleRepository(database)
    sync_runs = KnowledgeFabricExternalSyncRunRepository(
        database,
        retention_days=settings.knowledge_external_sync_report_retention_days,
    )
    site_collections = KnowledgeFabricSiteCollectionRepository(database)

    async def resolve_public_host(hostname: str) -> tuple[str, ...]:
        records = await asyncio.get_running_loop().getaddrinfo(hostname, 443, type=0)
        return tuple(dict.fromkeys(str(record[4][0]) for record in records))

    fetcher = PinnedPublicHttpsFetcher(
        resolver=resolve_public_host,
        dial_transport=AsyncioPinnedHttpsDialTransport(timeout_seconds=15),
    )
    website_sync = KnowledgeFabricWebsiteSyncService(
        sync_repository=external_sync,
        ingestion_service=ingestion,
        fetcher=fetcher,
    )
    atom_sync = KnowledgeFabricAtomSyncService(
        sync_repository=external_sync,
        ingestion_service=ingestion,
        fetcher=fetcher,
    )
    collection_sync = KnowledgeFabricWebsiteCollectionSyncService(
        sync_repository=external_sync,
        collection_repository=site_collections,
        ingestion_service=ingestion,
        fetcher=fetcher,
        rendered_fetcher=browser_runtime,
    )
    scheduler = KnowledgeFabricExternalSyncScheduler(
        schedule_repository=schedules,
        sync_run_repository=sync_runs,
        sync_by_source_type={
            WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE: website_sync.sync_claim,
            ATOM_PUBLIC_HTTPS_SOURCE_TYPE: atom_sync.sync_claim,
            WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE: collection_sync.sync_claim,
        },
    )
    derived_work = KnowledgeFabricInvalidationWorker(
        invalidations=KnowledgeFabricInvalidationRepository(database),
        indexes=KnowledgeFabricIndexRepository(database),
        projections=KnowledgeFabricProjectionRepository(database),
    )
    retention = KnowledgeFabricExternalSyncReportRetentionService(sync_runs)
    background_runtime = KnowledgeFabricBackgroundRuntime(
        start_report_retention=retention.start,
        stop_report_retention=retention.stop,
        start_external_sync=scheduler.start,
        stop_external_sync=scheduler.stop,
        start_derived_work=derived_work.start,
        stop_derived_work=derived_work.stop,
        failure_waiters=(scheduler.wait_for_failure, derived_work.wait_for_failure),
    )
    return KnowledgeFabricWorkerRuntime(
        database=database,
        object_storage=object_storage,
        browser_runtime=browser_runtime,
        background_runtime=background_runtime,
    )


async def serve(
    settings: Settings | None = None,
    *,
    wait_for_shutdown: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Run Fabric maintenance until shutdown or a supervised loop reaches its retry limit."""

    runtime = compose_worker_runtime(settings or get_settings())
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    if wait_for_shutdown is None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):  # pragma: no cover - Windows lacks asyncio signals.
                loop.add_signal_handler(signum, shutdown.set)

        async def wait_for_signal() -> None:
            await shutdown.wait()

        wait_for_shutdown = wait_for_signal

    shutdown_task: asyncio.Task[None] | None = None
    failure_task: asyncio.Task[None] | None = None
    try:
        await runtime.browser_runtime.start()
        await runtime.background_runtime.start()
        async def wait_for_requested_shutdown() -> None:
            await wait_for_shutdown()

        shutdown_task = asyncio.create_task(
            wait_for_requested_shutdown(), name="knowledge-fabric-shutdown"
        )
        failure_task = asyncio.create_task(
            runtime.background_runtime.wait_for_failure(),
            name="knowledge-fabric-supervisor",
        )
        done, pending = await asyncio.wait(
            {shutdown_task, failure_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            await task
        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    finally:
        waiters = [task for task in (shutdown_task, failure_task) if task is not None]
        for task in waiters:
            if not task.done():
                task.cancel()
        if waiters:
            await asyncio.gather(*waiters, return_exceptions=True)
        try:
            await runtime.background_runtime.stop()
        finally:
            try:
                await runtime.browser_runtime.stop()
            finally:
                _close_object_storage(runtime.object_storage)
                runtime.database.engine.dispose()


def _close_object_storage(storage: KnowledgeObjectStorage) -> None:
    """Release an optional S3 client pool; pinned fetches close each connection per request."""

    client = getattr(storage, "client", None)
    close = getattr(client, "close", None)
    if callable(close):
        with suppress(Exception):
            close()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
