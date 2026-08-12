import asyncio

from echo_masque.platform_keyframes import PlatformKeyframeExtractor
from echo_masque.platform_media import PlatformMediaResolution


class FakeKeyframeExtractor(PlatformKeyframeExtractor):
    def __init__(self) -> None:
        super().__init__(ffmpeg_path="ffmpeg", max_frames=3)
        self.calls: list[float] = []

    async def _extract_frame(
        self,
        resolution: PlatformMediaResolution,
        timestamp: float,
    ) -> bytes | None:
        assert resolution.media_headers == (("Referer", "https://www.bilibili.com/"),)
        self.calls.append(timestamp)
        return b"jpeg-frame-" + str(timestamp).encode()


def _resolution() -> PlatformMediaResolution:
    return PlatformMediaResolution(
        source_key="url:https://www.bilibili.com/video/BV1test",
        canonical_url="https://www.bilibili.com/video/BV1test",
        platform="bilibili",
        media_id="BV1test",
        duration_seconds=100,
        media_url="https://upos.example.test/video.m4s?token=secret",
        media_ext="mp4",
        media_headers=(("Referer", "https://www.bilibili.com/"),),
    )


def test_keyframe_extractor_samples_chronologically_and_reuses_cache() -> None:
    extractor = FakeKeyframeExtractor()

    async def run():
        first = await extractor.extract(_resolution())
        second = await extractor.extract(_resolution())
        return first, second

    first, second = asyncio.run(run())

    assert first is not None
    assert second == first
    assert first.timestamps_seconds == (10.0, 30.0, 50.0)
    assert len(first.frame_data_uris) == 3
    assert all(value.startswith("data:image/jpeg;base64,") for value in first.frame_data_uris)
    assert extractor.calls == [10.0, 30.0, 50.0]


def test_ffmpeg_header_builder_strips_line_breaks() -> None:
    assert PlatformKeyframeExtractor._ffmpeg_headers(
        (("Referer\r\n", "https://example.test/\r\nInjected: no"),)
    ) == "Referer: https://example.test/Injected: no\r\n"
