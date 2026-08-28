import asyncio

from echo_masque.knowledge_fabric_external_sync_report_retention import (
    KnowledgeFabricExternalSyncReportRetentionService,
)


class _Repository:
    def __init__(self, counts: list[int]) -> None:
        self.counts = counts
        self.limits: list[int] = []

    def purge_expired(self, *, limit: int) -> int:
        self.limits.append(limit)
        return self.counts.pop(0) if self.counts else 0


def test_sync_report_retention_purges_bounded_batches_and_starts_once() -> None:
    repository = _Repository([500, 3])
    service = KnowledgeFabricExternalSyncReportRetentionService(
        repository,  # type: ignore[arg-type]
        interval_seconds=3600,
    )

    assert service.purge_once() == 503
    assert repository.limits == [500, 500]

    async def scenario() -> None:
        await service.start()
        await service.start()
        await service.stop()

    asyncio.run(scenario())
