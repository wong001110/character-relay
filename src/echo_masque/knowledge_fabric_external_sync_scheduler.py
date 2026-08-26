"""Small durable worker loop for explicitly enabled external Fabric Sources."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress

from echo_masque.knowledge_fabric_website_sync import WebsiteSyncResult
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    ExternalSourceScheduleClaim,
    KnowledgeFabricExternalScheduleRepository,
)

type ExternalSourceSync = Callable[[ExternalSourceScheduleClaim], Awaitable[WebsiteSyncResult]]


class KnowledgeFabricExternalSyncScheduler:
    """Poll only persisted opt-in work; source registration alone never starts egress."""

    def __init__(
        self,
        *,
        schedule_repository: KnowledgeFabricExternalScheduleRepository,
        sync_by_source_type: Mapping[str, ExternalSourceSync],
        poll_seconds: float = 30,
        lease_seconds: int = 120,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("External sync poll interval must be positive.")
        if lease_seconds < 30:
            raise ValueError("External sync lease duration must be at least 30 seconds.")
        self.schedule_repository = schedule_repository
        self.sync_by_source_type = dict(sync_by_source_type)
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
        sync = self.sync_by_source_type.get(claim.source_type)
        if sync is None:
            await asyncio.to_thread(
                self.schedule_repository.mark_result,
                claim=claim, succeeded=False, error_code="source_rejected"
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
        await asyncio.to_thread(
            self.schedule_repository.mark_result,
            claim=claim,
            succeeded=result.outcome != "failed",
            error_code=result.error_code,
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
