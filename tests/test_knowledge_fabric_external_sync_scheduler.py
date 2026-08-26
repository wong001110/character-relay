from __future__ import annotations

import asyncio
from time import sleep

from echo_masque.knowledge_fabric_external_sync_scheduler import (
    KnowledgeFabricExternalSyncScheduler,
)
from echo_masque.knowledge_fabric_website_sync import WebsiteSyncResult
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    ExternalSourceScheduleClaim,
)


class _SlowScheduleRepository:
    def claim_due(self, *, limit: int, lease_seconds: int) -> list[object]:
        del limit, lease_seconds
        sleep(0.05)
        return []


def test_external_scheduler_moves_blocking_claim_work_off_the_event_loop() -> None:
    scheduler = KnowledgeFabricExternalSyncScheduler(
        schedule_repository=_SlowScheduleRepository(),  # type: ignore[arg-type]
        sync_by_source_type={},
    )

    async def run() -> None:
        task = asyncio.create_task(scheduler.run_once())
        await asyncio.sleep(0)
        assert not task.done()
        assert await task == 0

    asyncio.run(run())


class _ClaimingScheduleRepository:
    def __init__(self, claim: ExternalSourceScheduleClaim) -> None:
        self.claim: ExternalSourceScheduleClaim | None = claim
        self.marked: list[tuple[ExternalSourceScheduleClaim, bool, str | None]] = []

    def claim_due(
        self,
        *,
        limit: int,
        lease_seconds: int,
    ) -> list[ExternalSourceScheduleClaim]:
        assert (limit, lease_seconds) == (1, 120)
        claim, self.claim = self.claim, None
        return [claim] if claim is not None else []

    def mark_result(
        self,
        *,
        claim: ExternalSourceScheduleClaim,
        succeeded: bool,
        error_code: str | None,
    ) -> bool:
        self.marked.append((claim, succeeded, error_code))
        return True


def test_external_scheduler_passes_the_durable_claim_to_the_source_sync() -> None:
    claim = ExternalSourceScheduleClaim(
        source_id="source-1",
        source_type="website_public_https",
        hostname="example.test",
        lease_token="lease-1",
    )
    repository = _ClaimingScheduleRepository(claim)
    received: list[ExternalSourceScheduleClaim] = []

    async def sync(candidate: ExternalSourceScheduleClaim) -> WebsiteSyncResult:
        received.append(candidate)
        return WebsiteSyncResult(outcome="unchanged")

    scheduler = KnowledgeFabricExternalSyncScheduler(
        schedule_repository=repository,  # type: ignore[arg-type]
        sync_by_source_type={"website_public_https": sync},
    )

    assert asyncio.run(scheduler.run_once()) == 1
    assert received == [claim]
    assert repository.marked == [(claim, True, None)]
