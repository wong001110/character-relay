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

type ExternalSourceSync = Callable[[str], Awaitable[WebsiteSyncResult]]


class KnowledgeFabricExternalSyncScheduler:
    """Poll only persisted opt-in work; source registration alone never starts egress."""

    def __init__(
        self,
        *,
        schedule_repository: KnowledgeFabricExternalScheduleRepository,
        sync_by_source_type: Mapping[str, ExternalSourceSync],
        poll_seconds: float = 30,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("External sync poll interval must be positive.")
        self.schedule_repository = schedule_repository
        self.sync_by_source_type = dict(sync_by_source_type)
        self.poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self.schedule_repository.recover_expired()
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
        claims = self.schedule_repository.claim_due()
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
            self.schedule_repository.mark_result(
                claim=claim, succeeded=False, error_code="source_rejected"
            )
            return
        try:
            result = await sync(claim.source_id)
        except Exception:
            self.schedule_repository.mark_result(
                claim=claim, succeeded=False, error_code="sync_failed"
            )
            return
        self.schedule_repository.mark_result(
            claim=claim,
            succeeded=result.outcome != "failed",
            error_code=result.error_code,
        )


__all__ = ["ExternalSourceSync", "KnowledgeFabricExternalSyncScheduler"]
