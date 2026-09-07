from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from echo_masque.browser_runtime import (
    _MAX_RENDERED_COLLECTION_DOM_BYTES,
    BrowserCapabilityManager,
    BrowserToolUnavailable,
)
from echo_masque.knowledge_fabric_website_collection_sync import (
    KnowledgeFabricWebsiteCollectionSyncService,
)
from echo_masque.network_safety import PublicUrlGuard


class _Response:
    def __init__(
        self,
        content_length: str,
        body: bytes = b'{"safe":true}',
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.url = "https://api.example.test/public/entries"
        self.request = SimpleNamespace(method="GET", resource_type="fetch")
        self.status = 200
        self.headers = {
            "content-type": "application/json",
            **({"content-length": content_length} if content_length else {}),
            **(extra_headers or {}),
        }
        self._body = body
        self.body_called = False

    async def body(self) -> bytes:
        self.body_called = True
        return self._body


class _Anchor:
    async def get_attribute(self, name: str) -> str | None:
        assert name == "href"
        return None


class _Anchors:
    async def count(self) -> int:
        return 0

    def nth(self, index: int) -> _Anchor:
        raise AssertionError(f"no anchors, requested {index}")


class _Page:
    def __init__(self, response: _Response, *, estimated_bytes: int = 10) -> None:
        self.response = response
        self.estimated_bytes = estimated_bytes
        self.listeners: dict[str, Any] = {}
        self.content_called = False

    def on(self, event: str, callback: Any) -> None:
        self.listeners[event] = callback

    def remove_listener(self, event: str, callback: Any) -> None:
        assert self.listeners.get(event) is callback
        self.listeners.pop(event)

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        assert state == "networkidle"
        assert timeout == 4_000

    async def wait_for_timeout(self, timeout: int) -> None:
        assert timeout == 250

    async def evaluate(self, expression: str, maximum: int) -> int:
        assert "createTreeWalker" in expression
        assert maximum == _MAX_RENDERED_COLLECTION_DOM_BYTES
        return self.estimated_bytes

    async def content(self) -> str:
        self.content_called = True
        return "<html><body>safe</body></html>"

    def locator(self, selector: str) -> _Anchors:
        assert selector == "a"
        return _Anchors()


def _public_guard() -> PublicUrlGuard:
    async def resolver(hostname: str) -> tuple[str, ...]:
        assert hostname in {"example.test", "api.example.test"}
        return ("93.184.216.34",)

    return PublicUrlGuard(resolver)


async def _capture_with_page(page: _Page) -> tuple[bool, tuple[str, ...]]:
    manager = BrowserCapabilityManager(url_guard=_public_guard())

    @asynccontextmanager
    async def fake_collection_page(allowed_hosts: frozenset[str]):
        assert allowed_hosts == frozenset({"example.test", "api.example.test"})
        yield page

    async def fake_navigate(target: _Page, url: str) -> None:
        assert target is page
        assert url == "https://example.test/wiki"
        target.listeners["response"](target.response)

    manager._public_collection_page = fake_collection_page  # type: ignore[method-assign]
    manager._navigate = fake_navigate  # type: ignore[method-assign]
    captured = await manager.fetch_rendered_collection_page(
        url="https://example.test/wiki",
        allowed_hosts=frozenset({"example.test", "api.example.test"}),
        max_links=1,
    )
    return page.response.body_called, captured.public_json


@pytest.mark.parametrize(
    ("content_length", "extra_headers"),
    (
        ("", {}),
        ("131073", {}),
        ("invalid", {}),
        ("-1", {}),
        ("13", {"transfer-encoding": "chunked"}),
        ("13", {"content-encoding": "br"}),
    ),
)
def test_rendered_json_capture_never_reads_unknown_or_giant_response_bodies(
    content_length: str,
    extra_headers: dict[str, str],
) -> None:
    page = _Page(_Response(content_length, extra_headers=extra_headers))

    body_called, captured_json = asyncio.run(_capture_with_page(page))

    assert body_called is False
    assert captured_json == ()


def test_rendered_json_capture_reads_only_declared_small_response() -> None:
    page = _Page(_Response("13"))

    body_called, captured_json = asyncio.run(_capture_with_page(page))

    assert body_called is True
    assert captured_json == ('{"safe":true}',)


def test_rendered_dom_cap_is_checked_before_page_content_is_materialized() -> None:
    page = _Page(_Response("13"), estimated_bytes=_MAX_RENDERED_COLLECTION_DOM_BYTES + 1)

    with pytest.raises(BrowserToolUnavailable, match="DOM exceeded"):
        asyncio.run(_capture_with_page(page))

    assert page.content_called is False


class _SlowRenderedFetcher:
    cancelled = False

    async def fetch_rendered_collection_page(self, **_: object) -> object:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("the acquisition deadline did not fire")


class _SyncRepository:
    def __init__(self) -> None:
        self.source = SimpleNamespace(
            locator="https://example.test/wiki",
            parser_profile_json=(
                '{"collection_renderer":"browser","collection_render_page_limit":"1",'
                '"collection_render_max_depth":"0"}'
            ),
        )
        self.outcomes: list[str] = []

    def require_public_https_source(self, source_id: str, **_: object) -> object:
        assert source_id == "source-1"
        return self.source

    def record_outcome(self, *, outcome: str, **_: object) -> object:
        self.outcomes.append(outcome)
        return object()


class _CollectionRepository:
    def __init__(self) -> None:
        self.begin_generation_calls = 0
        self.previously_published = {"https://example.test/previous"}

    def begin_generation(self, source_id: str) -> int:
        assert source_id == "source-1"
        self.begin_generation_calls += 1
        return 1


def test_rendered_deadline_fails_before_generation_and_preserves_current_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_repository = _SyncRepository()
    collection_repository = _CollectionRepository()
    rendered_fetcher = _SlowRenderedFetcher()
    service = KnowledgeFabricWebsiteCollectionSyncService(
        sync_repository=sync_repository,  # type: ignore[arg-type]
        collection_repository=collection_repository,  # type: ignore[arg-type]
        ingestion_service=None,  # type: ignore[arg-type]
        fetcher=None,  # type: ignore[arg-type]
        url_guard=_public_guard(),
        rendered_fetcher=rendered_fetcher,
    )
    monkeypatch.setattr(
        "echo_masque.knowledge_fabric_website_collection_sync."
        "_RENDERED_COLLECTION_DISCOVERY_TIMEOUT_SECONDS",
        0.01,
    )

    result = asyncio.run(service.sync("source-1"))

    assert (result.outcome, result.error_code) == ("failed", "discovery_rejected")
    assert sync_repository.outcomes == ["failed"]
    assert rendered_fetcher.cancelled is True
    assert collection_repository.begin_generation_calls == 0
    assert collection_repository.previously_published == {"https://example.test/previous"}
