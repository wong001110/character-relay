"""Small durable worker loop for explicitly enabled external Fabric Sources."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime

from echo_masque.knowledge_fabric_website_sync import WebsiteSyncResult
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    ExternalSourceScheduleClaim,
    KnowledgeFabricExternalScheduleRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_run_repository import (
    KnowledgeFabricExternalSyncRunRepository,
)

type ExternalSourceSync = Callable[[ExternalSourceScheduleClaim], Awaitable[WebsiteSyncResult]]


class KnowledgeFabricExternalSyncScheduler:
    """Poll only persisted opt-in work; source registration alone never starts egress."""

    def __init__(
        self,
        *,
        schedule_repository: KnowledgeFabricExternalScheduleRepository,
        sync_by_source_type: Mapping[str, ExternalSourceSync],
        sync_run_repository: KnowledgeFabricExternalSyncRunRepository | None = None,
        poll_seconds: float = 30,
        lease_seconds: int = 120,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("External sync poll interval must be positive.")
        if lease_seconds < 30:
            raise ValueError("External sync lease duration must be at least 30 seconds.")
        self.schedule_repository = schedule_repository
        self.sync_by_source_type = dict(sync_by_source_type)
        self.sync_run_repository = sync_run_repository
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            await asyncio.to_thread(self.schedule_repository.recover_expired)
            self._task = asyncio.create_task(self._run(), name="knowledge-fabric-external-sync")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def run_once(self) -> int:
        # Claim one Source at a time.  A single scheduler must never consume a batch serially
        # under one short lease, nor hold rows another replica could process.
        claims = await asyncio.to_thread(
            self.schedule_repository.claim_due,
            limit=1,
            lease_seconds=self.lease_seconds,
        )
        for claim in claims:
            await self._run_claim(claim)
        return len(claims)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            await self.run_once()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_seconds)

    async def _run_claim(self, claim: ExternalSourceScheduleClaim) -> None:
        started_at = datetime.now(UTC)
        sync = self.sync_by_source_type.get(claim.source_type)
        if sync is None:
            marked = await asyncio.to_thread(
                self.schedule_repository.mark_result,
                claim=claim, succeeded=False, error_code="source_rejected"
            )
            if marked:
                await self._record_completed_report(
                    claim,
                    WebsiteSyncResult(outcome="failed", error_code="source_rejected"),
                    started_at,
                )
            return
        renewal = asyncio.create_task(
            self._renew_claim_until_complete(claim),
            name=f"knowledge-fabric-external-sync-lease:{claim.source_id}",
        )
        try:
            result = await sync(claim)
        except Exception:
            result = WebsiteSyncResult(outcome="failed", error_code="sync_failed")
        finally:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
        marked = await asyncio.to_thread(
            self.schedule_repository.mark_result,
            claim=claim,
            succeeded=result.outcome != "failed",
            error_code=result.error_code,
        )
        if marked:
            await self._record_completed_report(claim, result, started_at)

    async def _record_completed_report(
        self,
        claim: ExternalSourceScheduleClaim,
        result: WebsiteSyncResult,
        started_at: datetime,
    ) -> None:
        """Persist final worker facts only after the schedule accepted its matching lease."""

        if self.sync_run_repository is None or result.outcome == "stale":
            return
        await asyncio.to_thread(
            self.sync_run_repository.record_completed,
            source_id=claim.source_id,
            result=result,
            started_at=started_at,
        )

    async def _renew_claim_until_complete(self, claim: ExternalSourceScheduleClaim) -> None:
        """Keep a valid Source fence alive while a bounded fetch/publish operation runs."""

        interval = min(30.0, self.lease_seconds / 2)
        while True:
            await asyncio.sleep(interval)
            current = await asyncio.to_thread(
                self.schedule_repository.renew_claim,
                claim=claim,
                lease_seconds=self.lease_seconds,
            )
            if not current:
                return


__all__ = ["ExternalSourceSync", "KnowledgeFabricExternalSyncScheduler"]
