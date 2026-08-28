from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from echo_masque.browser_runtime import (
    RenderedCollectionPage,
    _is_admissible_rendered_collection_json_response,
)
from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_fabric_rendered_collection import (
    KnowledgeFabricRenderedCollectionAnalyzer,
    RenderedCollectionRejected,
    configured_rendered_collection_profile,
    extract_render_candidate_hosts,
    rendered_collection_profile,
)
from echo_masque.knowledge_fabric_website_collection_sync import (
    KnowledgeFabricWebsiteCollectionSyncService,
)
from echo_masque.knowledge_fabric_website_sync import WebsiteFetchResponse
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.network_safety import PublicUrlGuard
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.knowledge_fabric_site_collection_repository import (
    KnowledgeFabricSiteCollectionRepository,
)


@dataclass
class _Storage:
    objects: dict[str, bytes]

    def put_private(
        self, *, object_key: str, content: bytes, content_type: str, metadata: Mapping[str, str]
    ) -> StoredKnowledgeObject:
        del content_type, metadata
        self.objects.setdefault(object_key, content)
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="knowledge-private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type="application/octet-stream",
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


class _NoStaticFetcher:
    calls: list[str]

    def __init__(self) -> None:
        self.calls = []

    async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse:
        del headers
        self.calls.append(url)
        raise AssertionError("Rendered collection must not use the static fetcher.")


class _RenderedFetcher:
    def __init__(self, pages: Mapping[str, RenderedCollectionPage]) -> None:
        self.pages = dict(pages)
        self.calls: list[tuple[str, frozenset[str], int]] = []

    async def fetch_rendered_collection_page(
        self,
        *,
        url: str,
        allowed_hosts: frozenset[str],
        max_links: int,
    ) -> RenderedCollectionPage:
        self.calls.append((url, allowed_hosts, max_links))
        return self.pages[url]


class _BootstrapFetcher:
    def __init__(self, response: WebsiteFetchResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse:
        del headers
        self.calls.append(url)
        return self.response


def _page(
    title: str,
    text: str,
    hrefs: tuple[str, ...] = (),
    public_json: tuple[str, ...] = (),
) -> RenderedCollectionPage:
    anchors = "".join(f'<a href="{href}">Link</a>' for href in hrefs)
    return RenderedCollectionPage(
        html=f"<html><head><title>{title}</title></head><body><main>{anchors}<p>{text}</p></main></body></html>",
        hrefs=hrefs,
        public_json=public_json,
    )


def _guard() -> PublicUrlGuard:
    async def resolver(hostname: str) -> tuple[str, ...]:
        assert hostname == "example.test"
        return ("93.184.216.34",)

    return PublicUrlGuard(resolver)


def test_profile_requires_bounded_hostname_only_configuration() -> None:
    configured = configured_rendered_collection_profile(
        current_profile_json='{"other":"preserved"}',
        enabled=True,
        allowed_hosts=("Api.Example.Test.",),
        page_limit=12,
        max_depth=2,
    )
    profile = rendered_collection_profile(
        locator="https://example.test/wiki",
        parser_profile_json=configured,
    )
    assert profile.enabled is True
    assert profile.allowed_hosts == frozenset({"example.test", "api.example.test"})
    assert (profile.page_limit, profile.max_depth) == (12, 2)
    with pytest.raises(RenderedCollectionRejected, match="host"):
        configured_rendered_collection_profile(
            current_profile_json="{}",
            enabled=True,
            allowed_hosts=("api.example.test/path",),
            page_limit=12,
            max_depth=1,
        )


def test_analyzer_returns_only_public_preconnect_and_dns_prefetch_hosts() -> None:
    bootstrap = (
        b"<html><head>"
        b'<link rel="preconnect" href="https://api.example.test">'
        b'<link rel="dns-prefetch" href="https://cdn.example.test">'
        b'<link rel="stylesheet" href="https://ignored.example.test">'
        b"</head><body>Bootstrap</body></html>"
    )
    fetcher = _BootstrapFetcher(
        WebsiteFetchResponse(200, bootstrap, {"content-type": "text/html; charset=utf-8"})
    )
    analysis = asyncio.run(
        KnowledgeFabricRenderedCollectionAnalyzer(fetcher).analyze(
            source_id="source-1",
            locator="https://example.test/wiki",
        )
    )
    assert analysis.candidate_hosts == ("api.example.test", "cdn.example.test")
    assert fetcher.calls == ["https://example.test/wiki"]
    assert extract_render_candidate_hosts(
        root_locator="https://example.test/wiki",
        content=bootstrap,
    ) == ("api.example.test", "cdn.example.test")


def test_rendered_collection_sync_keeps_browser_egress_bounded_and_ingests_dom(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rendered-collection.db'}")
    database.initialize()
    storage = _Storage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Wiki", description="", default_authority_profile="standard", status="active"
    )
    parser_profile_json = configured_rendered_collection_profile(
        current_profile_json="{}",
        enabled=True,
        allowed_hosts=("api.example.test",),
        page_limit=3,
        max_depth=1,
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type=WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
        locator="https://example.test/wiki",
        access_profile_json="{}",
        parser_profile_json=parser_profile_json,
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    renderer = _RenderedFetcher(
        {
            "https://example.test/wiki": _page(
                "Wiki",
                "Welcome to Teyvat",
                ("/amber", "https://outside.test/no"),
                ('{"entries":["Amber","Lisa"],"web_path":"/lisa"}',),
            ),
            "https://example.test/amber": _page("Amber", "Pyro outrider"),
            "https://example.test/lisa": _page("Lisa", "Electro librarian"),
        }
    )
    static_fetcher = _NoStaticFetcher()
    service = KnowledgeFabricWebsiteCollectionSyncService(
        sync_repository=KnowledgeFabricExternalSyncRepository(database),
        collection_repository=KnowledgeFabricSiteCollectionRepository(database),
        ingestion_service=KnowledgeFabricIngestionService(
            KnowledgeFabricContentRepository(database, object_storage=storage),
            storage,
            object_key_prefix="knowledge",
        ),
        fetcher=static_fetcher,
        url_guard=_guard(),
        rendered_fetcher=renderer,
    )
    result = asyncio.run(service.sync(source.id, checked_at=datetime(2026, 8, 28, tzinfo=UTC)))
    assert (result.outcome, result.discovered_page_count, result.changed_page_count) == (
        "changed",
        3,
        3,
    )
    assert static_fetcher.calls == []
    assert [call[0] for call in renderer.calls] == [
        "https://example.test/wiki",
        "https://example.test/amber",
        "https://example.test/lisa",
    ]
    approved_hosts = frozenset({"example.test", "api.example.test"})
    assert all(call[1] == approved_hosts for call in renderer.calls)
    available_pages = KnowledgeFabricSiteCollectionRepository(database).list_available_pages(
        source.id
    )
    assert {page.locator for page in available_pages} == {
        "https://example.test/wiki",
        "https://example.test/amber",
        "https://example.test/lisa",
    }
    assert {
        page.locator: page.discovery_kind for page in available_pages
    }["https://example.test/lisa"] == "rendered_json_link"
    stored_artifacts = [
        json.loads(content)
        for content in storage.objects.values()
        if b'"root_locator":"https://example.test/wiki"' in content
    ]
    root_artifact = next(
        item for item in stored_artifacts if len(item["pages"]) == 1
    )
    root_html = base64.b64decode(root_artifact["pages"][0]["content_base64"]).decode("utf-8")
    assert "Public data loaded by rendered page" in root_html
    assert "Amber" in root_html


def test_rendered_collection_json_capture_accepts_only_bounded_public_get_json() -> None:
    allowed = frozenset({"example.test", "api.example.test"})
    assert _is_admissible_rendered_collection_json_response(
        url="https://api.example.test/public/entries",
        request_method="GET",
        resource_type="xhr",
        status_code=200,
        content_type="application/json; charset=utf-8",
        allowed_hosts=allowed,
    )
    assert not _is_admissible_rendered_collection_json_response(
        url="https://api.example.test/public/entries",
        request_method="POST",
        resource_type="xhr",
        status_code=200,
        content_type="application/json",
        allowed_hosts=allowed,
    )
    assert not _is_admissible_rendered_collection_json_response(
        url="https://unapproved.example.test/public/entries",
        request_method="GET",
        resource_type="fetch",
        status_code=200,
        content_type="application/json",
        allowed_hosts=allowed,
    )
    assert not _is_admissible_rendered_collection_json_response(
        url="https://api.example.test/public/entries",
        request_method="GET",
        resource_type="document",
        status_code=200,
        content_type="application/json",
        allowed_hosts=allowed,
    )


def test_rendered_collection_json_route_discovery_requires_semantic_relative_or_https_fields(
) -> None:
    assert KnowledgeFabricWebsiteCollectionSyncService._rendered_collection_json_route_hrefs(
        (
            json.dumps(
                {
                    "web_path": "/articles/amber",
                    "url": "https://example.test/articles/lisa",
                    "label": "/not-a-route",
                    "unsafe_path": "/not-a-route-either",
                    "query_path": "/articles/nope?preview=1",
                    "nested": [{"href": "/articles/kaeya"}],
                }
            ),
        )
    ) == (
        "/articles/amber",
        "/articles/kaeya",
        "https://example.test/articles/lisa",
    )
