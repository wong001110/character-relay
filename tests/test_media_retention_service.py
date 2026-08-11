import asyncio

from echo_masque.media_retention import MediaRetentionService


class FakeExpiringRepository:
    def __init__(self, counts: list[int], *, error: Exception | None = None) -> None:
        self.counts = list(counts)
        self.error = error
        self.limits: list[int] = []

    def purge_expired(self, *, limit: int = 500) -> int:
        self.limits.append(limit)
        if self.error is not None:
            raise self.error
        if not self.counts:
            return 0
        return self.counts.pop(0)


def test_media_retention_purges_bounded_batches_independently() -> None:
    analysis = FakeExpiringRepository([500, 2])
    conversation = FakeExpiringRepository([], error=RuntimeError("database busy"))
    generated = FakeExpiringRepository([200, 200, 200, 200])
    service = MediaRetentionService(
        analysis,  # type: ignore[arg-type]
        conversation,  # type: ignore[arg-type]
        generated,  # type: ignore[arg-type]
        max_batches_per_table=3,
    )

    result = service.purge_once()

    assert result.media_analysis == 502
    assert result.conversation_media == 0
    assert result.generated_media == 600
    assert analysis.limits == [500, 500]
    assert conversation.limits == [500]
    assert generated.limits == [200, 200, 200]


def test_media_retention_start_is_immediate_and_idempotent() -> None:
    analysis = FakeExpiringRepository([])
    conversation = FakeExpiringRepository([])
    generated = FakeExpiringRepository([])
    service = MediaRetentionService(
        analysis,  # type: ignore[arg-type]
        conversation,  # type: ignore[arg-type]
        generated,  # type: ignore[arg-type]
        interval_seconds=3600,
    )

    async def scenario() -> None:
        await service.start()
        await service.start()
        assert analysis.limits == [500]
        assert conversation.limits == [500]
        assert generated.limits == [200]
        await service.stop()
        await service.stop()

    asyncio.run(scenario())
