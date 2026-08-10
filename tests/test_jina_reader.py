import asyncio
import json

import httpx

from echo_masque.jina_reader import JinaReaderClient


def test_jina_reader_prefers_structured_summary_and_clean_content() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.host == "r.jina.ai"
        assert request.headers.get("x-respond-with") == "readerlm-v2"
        payload = {
            "title": "Example article",
            "summary": (
                "The article explains the new media resolver and why shared context matters."
            ),
            "content": "The resolver now uses clean article content and reusable media context.",
            "published_time": "2026-08-10T12:00:00Z",
        }
        return httpx.Response(
            200,
            json={
                "data": {
                    "url": "https://9.9.9.9/article",
                    "title": "Envelope title",
                    "content": json.dumps(payload),
                }
            },
        )

    reader = JinaReaderClient(http_transport=httpx.MockTransport(handler))
    article = asyncio.run(reader.read("https://9.9.9.9/article"))

    assert calls == 1
    assert article.structured is True
    assert article.title == "Example article"
    assert article.summary.startswith("The article explains")
    assert "reusable media context" in article.content
    assert article.published_time == "2026-08-10T12:00:00Z"


def test_jina_reader_falls_back_to_normal_reader_content() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.headers.get("x-respond-with") == "readerlm-v2":
            return httpx.Response(422, text="structured extraction unavailable")
        return httpx.Response(
            200,
            json={
                "data": {
                    "title": "Fallback title",
                    "content": (
                        "A long article paragraph that contains enough factual context for the "
                        "character to understand what the linked page is discussing. " * 5
                    ),
                }
            },
        )

    reader = JinaReaderClient(http_transport=httpx.MockTransport(handler))
    article = asyncio.run(reader.read("https://9.9.9.9/fallback"))

    assert calls == 2
    assert article.structured is False
    assert article.title == "Fallback title"
    assert article.summary
    assert "factual context" in article.content
