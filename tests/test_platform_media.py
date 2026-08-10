import asyncio

import httpx

from echo_masque.platform_media import YtDlpMediaResolver


class FakeYtDlpMediaResolver(YtDlpMediaResolver):
    @staticmethod
    def _extract_info(url: str):
        assert "youtube.com" in url
        return {
            "id": "abc123",
            "title": "Resolver demo",
            "uploader": "Example Channel",
            "description": "A demonstration of shared media understanding.",
            "duration": 95,
            "webpage_url": "https://www.youtube.com/watch?v=abc123",
            "extractor_key": "Youtube",
            "formats": [
                {
                    "url": "https://1.1.1.1/video.mp4",
                    "protocol": "https",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "ext": "mp4",
                    "height": 720,
                }
            ],
            "subtitles": {
                "en": [
                    {
                        "url": "https://8.8.8.8/subtitle.vtt",
                        "ext": "vtt",
                    }
                ]
            },
        }


def test_ytdlp_resolver_returns_direct_media_and_transcript_without_video_download() -> None:
    subtitle_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal subtitle_calls
        assert request.url.host == "8.8.8.8"
        subtitle_calls += 1
        return httpx.Response(
            200,
            content=(
                b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello from the transcript.\n\n"
                b"00:00:01.000 --> 00:00:02.000\nShared context avoids duplicate work.\n"
            ),
        )

    resolver = FakeYtDlpMediaResolver(http_transport=httpx.MockTransport(handler))
    result = asyncio.run(
        resolver.resolve(
            "https://www.youtube.com/watch?v=abc123",
            source_key="youtube:abc123",
        )
    )

    assert result is not None
    assert result.media_url == "https://1.1.1.1/video.mp4"
    assert result.title == "Resolver demo"
    assert result.uploader == "Example Channel"
    assert result.duration_seconds == 95
    assert result.transcript_language == "en"
    assert result.transcript_source == "manual"
    assert "duplicate work" in result.transcript
    assert subtitle_calls == 1


def test_ytdlp_resolver_reuses_one_hour_resolution_cache() -> None:
    class CountingResolver(FakeYtDlpMediaResolver):
        extraction_count = 0

        @staticmethod
        def _extract_info(url: str):
            CountingResolver.extraction_count += 1
            return FakeYtDlpMediaResolver._extract_info(url)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCached.\n")

    resolver = CountingResolver(http_transport=httpx.MockTransport(handler))

    async def run():
        first = await resolver.resolve(
            "https://www.youtube.com/watch?v=abc123",
            source_key="youtube:abc123",
        )
        second = await resolver.resolve(
            "https://youtu.be/abc123",
            source_key="youtube:abc123",
        )
        return first, second

    first, second = asyncio.run(run())

    assert first == second
    assert CountingResolver.extraction_count == 1
