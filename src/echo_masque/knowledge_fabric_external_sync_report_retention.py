"""Best-effort TTL cleanup for derived external sync reports."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from echo_masque.persistence.knowledge_fabric_external_sync_run_repository import (
    KnowledgeFabricExternalSyncRunRepository,
)

logger = logging.getLogger(__name__)


class KnowledgeFabricExternalSyncReportRetentionService:
    """Purge expired report batches without coupling cleanup to portal or sync work."""

    def __init__(
        self,
        repository: KnowledgeFabricExternalSyncRunRepository,
        *,
        interval_seconds: int = 3600,
        max_batches: int = 5,
    ) -> None:
        self.repository = repository
        self.interval_seconds = max(60, interval_seconds)
        self.max_batches = max(1, min(max_batches, 20))
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        await asyncio.to_thread(self.purge_once)
        self._task = asyncio.create_task(
            self._run(), name="knowledge-fabric-external-sync-report-retention"
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def purge_once(self) -> int:
        deleted = 0
        try:
            for _ in range(self.max_batches):
                count = self.repository.purge_expired(limit=500)
                deleted += count
                if count < 500:
                    break
        except Exception as exc:
            logger.warning("Knowledge Fabric sync-report retention cleanup failed: %s", exc)
        if deleted:
            logger.info("Purged %s expired Knowledge Fabric sync report(s).", deleted)
        return deleted

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval_seconds)
                await asyncio.to_thread(self.purge_once)
        except asyncio.CancelledError:
            raise


__all__ = ["KnowledgeFabricExternalSyncReportRetentionService"]
