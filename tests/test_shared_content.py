import asyncio

import httpx

from echo_masque.content_resolver import resolve_static_url
from echo_masque.network_safety import PublicUrlGuard
from echo_masque.shared_content import (
    FxTwitterSharedContentEnricher,
    SharedContentManifest,
    SharedContentResolver,
)


async def public_resolver(_: str) -> tuple[str, ...]:
    return ("8.8.8.8",)


def test_fxtwitter_enrichment_returns_complete_ordered_photo_manifest() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url) == "https://api.fxtwitter.com/2/status/2091682495720722697"
        return httpx.Response(
            200,
            json={
                "code": 200,
                "status": {
                    "type": "status",
                    "id": "2091682495720722697",
                    "text": "Mejor me ahorro lo que pienso",
                    "author": {"name": "Makalister", "screen_name": "__Makalister__"},
                    "media": {
                        "all": [
                            {
                                "id": f"photo-{index}",
                                "type": "photo",
                                "url": f"https://pbs.twimg.com/media/photo-{index}.jpg",
                                "width": 1200,
                                "height": 1600,
                            }
                            for index in range(1, 5)
                        ],
                        "mosaic": {
                            "type": "mosaic_photo",
                            "formats": {"jpeg": "https://mosaic.fxtwitter.com/composite.jpg"},
                        },
                    },
                },
            },
        )

    source = resolve_static_url(
        "https://fixupx.com/__makalister__/status/2091682495720722697?s=46"
    )
    resolver = SharedContentResolver(
        (
            FxTwitterSharedContentEnricher(
                url_guard=PublicUrlGuard(resolver=public_resolver),
                http_transport=httpx.MockTransport(handler),
            ),
        )
    )

    async def resolve_twice() -> tuple[SharedContentManifest, SharedContentManifest]:
        first = await resolver.resolve(source)
        second = await resolver.resolve(source)
        return first, second

    first, second = asyncio.run(resolve_twice())

    assert first.source_key == "x:2091682495720722697"
    assert first.inventory_state == "complete"
    assert first.expected_asset_count == 4
    assert first.discovered_asset_count == 4
    assert first.author == "Makalister (@__Makalister__)"
    assert [item.ordinal for item in first.assets] == [1, 2, 3, 4]
    assert [item.kind for item in first.assets] == ["image"] * 4
    assert "mosaic" not in " ".join(item.url for item in first.assets)
    assert second == first
    assert calls == 1


def test_shared_content_resolver_falls_back_to_unknown_manifest() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="temporarily unavailable")

    source = resolve_static_url("https://x.com/example/status/123456789")
    resolver = SharedContentResolver(
        (
            FxTwitterSharedContentEnricher(
                url_guard=PublicUrlGuard(resolver=public_resolver),
                http_transport=httpx.MockTransport(handler),
            ),
        )
    )

    manifest = asyncio.run(resolver.resolve(source))

    assert manifest.source_key == "x:123456789"
    assert manifest.inventory_state == "unknown"
    assert manifest.assets == ()
    assert manifest.text == ""
