import asyncio
from datetime import UTC, datetime, timedelta

from echo_masque.media_hashing import StreamingSHA256, sha256_async_chunks, sha256_chunks
from echo_masque.media_runtime import MediaAnalysis, MediaAsset, MediaUnderstandingService
from echo_masque.media_singleflight import MediaAnalysisSingleFlight
from echo_masque.persistence import Database, MediaAnalysisRepository


class FakeMediaProvider:
    provider_id = "fake-media"
    model = "vision-1"

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis:
        self.calls += 1
        return MediaAnalysis(
            summary=f"understood {asset.media_key}",
            visible_text="Build failed",
            objects=("cat", "laptop"),
            tone="humorous",
        )


class BlockingMediaProvider(FakeMediaProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return MediaAnalysis(summary=f"understood {asset.media_key}")


def test_streaming_sha256_matches_single_pass_digest() -> None:
    chunks = [b"hello", b" ", b"world"]
    digest = sha256_chunks(chunks)

    incremental = StreamingSHA256()
    for chunk in chunks:
        incremental.update(chunk)

    assert digest == incremental.result()
    assert digest.bytes_seen == 11
    assert digest.media_key.startswith("sha256:")
    assert len(digest.sha256) == 64


def test_async_streaming_sha256() -> None:
    async def chunks():
        for value in (b"a", b"b", b"c"):
            yield value

    sync = sha256_chunks((b"a", b"b", b"c"))
    async_digest = asyncio.run(sha256_async_chunks(chunks()))
    assert async_digest == sync


def test_media_analysis_is_shared_after_first_provider_call() -> None:
    database = Database("sqlite://")
    database.initialize()
    cache = MediaAnalysisRepository(database)
    provider = FakeMediaProvider()
    service = MediaUnderstandingService(cache, provider)
    asset = MediaAsset(
        media_key="sha256:abc",
        media_type="image",
        mime_type="image/png",
    )

    first, first_hit = asyncio.run(service.analyze(asset))
    second, second_hit = asyncio.run(service.analyze(asset))

    assert first_hit is False
    assert second_hit is True
    assert second == first
    assert provider.calls == 1
    assert cache.count() == 1


def test_concurrent_bots_join_the_same_in_flight_analysis() -> None:
    async def scenario() -> None:
        database = Database("sqlite://")
        database.initialize()
        cache = MediaAnalysisRepository(database)
        provider = BlockingMediaProvider()
        service = MediaUnderstandingService(cache, provider, poll_interval_seconds=0.1)
        asset = MediaAsset(media_key="sha256:shared", media_type="image")

        first_task = asyncio.create_task(service.analyze(asset))
        await provider.started.wait()
        second_task = asyncio.create_task(service.analyze(asset))
        await asyncio.sleep(0)

        assert provider.calls == 1
        provider.release.set()
        first, second = await asyncio.gather(first_task, second_task)

        assert first[0] == second[0]
        assert first[1] is False
        assert second[1] is True
        assert provider.calls == 1

    asyncio.run(scenario())


def test_processing_lease_prevents_duplicate_claim_and_can_be_reclaimed() -> None:
    database = Database("sqlite://")
    database.initialize()
    cache = MediaAnalysisRepository(database)
    singleflight = MediaAnalysisSingleFlight(
        cache,
        processing_lease=timedelta(minutes=3),
    )
    start = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)
    identity = {
        "media_key": "sha256:lease",
        "media_type": "video",
        "analysis_version": "general-v1",
        "provider": "fake",
        "model": "vision",
    }

    first = singleflight.claim(**identity, now=start)
    duplicate = singleflight.claim(**identity, now=start + timedelta(minutes=1))
    reclaimed = singleflight.claim(**identity, now=start + timedelta(minutes=4))

    assert first.status == "claimed"
    assert duplicate.status == "processing"
    assert reclaimed.status == "claimed"
    assert reclaimed.lease_token != first.lease_token


def test_media_cache_sliding_ttl_refreshes_sparingly_and_purges_expired() -> None:
    database = Database("sqlite://")
    database.initialize()
    cache = MediaAnalysisRepository(
        database,
        ttl=timedelta(days=30),
        access_refresh_after=timedelta(hours=6),
    )
    start = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)
    record = cache.put(
        media_key="sha256:ttl",
        media_type="image",
        analysis_version="general-v1",
        provider="fake",
        model="vision",
        result_json=MediaAnalysis(summary="cached").model_dump_json(),
        now=start,
    )
    original_expiry = record.expires_at

    early = cache.get(
        media_key="sha256:ttl",
        analysis_version="general-v1",
        provider="fake",
        model="vision",
        now=start + timedelta(hours=1),
    )
    assert early is not None
    assert early.expires_at == original_expiry

    refreshed = cache.get(
        media_key="sha256:ttl",
        analysis_version="general-v1",
        provider="fake",
        model="vision",
        now=start + timedelta(hours=7),
    )
    assert refreshed is not None
    assert refreshed.expires_at > original_expiry

    cache.put(
        media_key="sha256:expired",
        media_type="image",
        analysis_version="general-v1",
        provider="fake",
        model="vision",
        result_json=MediaAnalysis(summary="old").model_dump_json(),
        now=start - timedelta(days=60),
    )
    assert cache.purge_expired(now=start, limit=100) == 1
    assert cache.count() == 1
