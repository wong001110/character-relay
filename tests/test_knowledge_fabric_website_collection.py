from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import select

from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_fabric_website_collection_adapter import (
    KnowledgeFabricWebsiteCollectionAdapter,
    WebsiteCollectionPageInput,
    WebsiteCollectionResponseInput,
    WebsiteCollectionResponseRejected,
)
from echo_masque.knowledge_fabric_website_collection_policy import (
    WebsiteCollectionRejected,
    discover_collection_page_locators,
)
from echo_masque.knowledge_fabric_website_collection_sync import (
    KnowledgeFabricWebsiteCollectionSyncService,
)
from echo_masque.knowledge_fabric_website_sitemap_policy import (
    WebsiteSitemapRejected,
    parse_sitemap,
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
from echo_masque.persistence.knowledge_fabric_index_repository import (
    KnowledgeFabricIndexRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeAssetReferenceRecord,
    KnowledgeExternalSourcePageStateRecord,
    KnowledgeSourceCurrentEntryRecord,
    KnowledgeSourceVersionRecord,
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
        del metadata
        self.objects.setdefault(object_key, content)
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="knowledge-private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


class _QueueFetcher:
    def __init__(self, responses: list[WebsiteFetchResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse:
        del headers
        self.calls.append(url)
        return self.responses.pop(0)


def _html(title: str, text: str, links: tuple[str, ...] = ()) -> bytes:
    anchors = "".join(f'<a href="{link}">Page</a>' for link in links)
    markup = (
        f"<html><head><title>{title}</title></head><body><main>{anchors}"
        f"<p>{text}</p></main></body></html>"
    )
    return markup.encode()


def _guard() -> PublicUrlGuard:
    async def resolver(hostname: str) -> tuple[str, ...]:
        assert hostname == "example.test"
        return ("93.184.216.34",)

    return PublicUrlGuard(resolver)


def test_collection_discovery_is_same_origin_canonical_and_bounded() -> None:
    pages = discover_collection_page_locators(
        root_locator="https://example.test/wiki",
        content=_html(
            "Guide",
            "Root",
            ("/a", "https://example.test/b", "https://elsewhere.test/no", "/a?secret=no", "#about"),
        ),
    )
    assert pages == (
        "https://example.test/a",
        "https://example.test/b",
        "https://example.test/wiki",
    )
    many = tuple(f"/{index}" for index in range(50))
    with pytest.raises(WebsiteCollectionRejected, match="too many"):
        discover_collection_page_locators(
            root_locator="https://example.test/wiki", content=_html("Guide", "Root", many)
        )


def test_sitemap_discovery_accepts_only_same_origin_dtd_free_page_locators() -> None:
    manifest = parse_sitemap(
        sitemap_locator="https://example.test/sitemap.xml",
        root_locator="https://example.test/wiki",
        content=(
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>https://example.test/a</loc></url>"
            b"<url><loc>https://example.test/b</loc></url></urlset>"
        ),
    )
    assert manifest.pages == ("https://example.test/a", "https://example.test/b")
    with pytest.raises(WebsiteSitemapRejected, match="DTD"):
        parse_sitemap(
            sitemap_locator="https://example.test/sitemap.xml",
            root_locator="https://example.test/wiki",
            content=b"<!DOCTYPE urlset><urlset />",
        )
    with pytest.raises(WebsiteSitemapRejected, match="same-origin"):
        parse_sitemap(
            sitemap_locator="https://example.test/sitemap.xml",
            root_locator="https://example.test/wiki",
            content=b"<urlset><url><loc>https://elsewhere.test/a</loc></url></urlset>",
        )


def test_collection_adapter_preserves_private_raw_pages_and_one_current_evidence_per_page() -> None:
    request = KnowledgeFabricWebsiteCollectionAdapter().build_snapshot(
        WebsiteCollectionResponseInput(
            source_id="source-1",
            root_locator="https://example.test/wiki",
            pages=(
                WebsiteCollectionPageInput(
                    locator="https://example.test/wiki",
                    content=_html("Guide", "Root evidence."),
                    content_type="text/html; charset=utf-8",
                ),
                WebsiteCollectionPageInput(
                    locator="https://example.test/a",
                    content=_html("A", "Character evidence."),
                    content_type="text/html",
                ),
            ),
            fetched_at=datetime(2026, 8, 27, tzinfo=UTC),
        )
    )
    assert request.version_key.startswith("website_collection:")
    assert request.artifact_content_type == "application/json"
    assert [document.canonical_locator for document in request.documents] == [
        "https://example.test/a",
        "https://example.test/wiki",
    ]
    assert all(len(document.blocks) == 1 for document in request.documents)
    with pytest.raises(WebsiteCollectionResponseRejected, match="unique"):
        KnowledgeFabricWebsiteCollectionAdapter().build_snapshot(
            WebsiteCollectionResponseInput(
                source_id="source-1",
                root_locator="https://example.test/wiki",
                pages=(
                    WebsiteCollectionPageInput("https://example.test/wiki", b"root", "text/plain"),
                    WebsiteCollectionPageInput("https://example.test/a", b"one", "text/plain"),
                    WebsiteCollectionPageInput("https://example.test/a", b"two", "text/plain"),
                ),
                fetched_at=datetime(2026, 8, 27, tzinfo=UTC),
            )
        )

    with pytest.raises(WebsiteCollectionResponseRejected, match="same-origin"):
        KnowledgeFabricWebsiteCollectionAdapter().build_snapshot(
            WebsiteCollectionResponseInput(
                source_id="source-1",
                root_locator="https://example.test/wiki",
                pages=(
                    WebsiteCollectionPageInput("https://example.test/wiki", b"root", "text/plain"),
                    WebsiteCollectionPageInput("https://elsewhere.test/a", b"no", "text/plain"),
                ),
                fetched_at=datetime(2026, 8, 27, tzinfo=UTC),
            )
        )


def test_collection_sync_updates_current_pages_without_retaining_removed_page_search_results(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'collection.db'}")
    database.initialize()
    storage = _Storage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Wiki", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type=WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
        locator="https://example.test/wiki",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    root_one = _html("Wiki", "Welcome", ("/a", "/b", "https://outside.test/rejected"))
    root_two = _html("Wiki", "Welcome revised", ("/a", "/c"))
    fetcher = _QueueFetcher(
        [
            WebsiteFetchResponse(200, root_one, {"content-type": "text/html", "etag": '"one"'}),
            WebsiteFetchResponse(404, b"", {"content-type": "text/xml"}),
            WebsiteFetchResponse(200, _html("A", "Amber first"), {"content-type": "text/html"}),
            WebsiteFetchResponse(200, _html("B", "Removed later"), {"content-type": "text/html"}),
            WebsiteFetchResponse(200, root_one, {"content-type": "text/html", "etag": '"one"'}),
            WebsiteFetchResponse(200, root_two, {"content-type": "text/html", "etag": '"two"'}),
            WebsiteFetchResponse(404, b"", {"content-type": "text/xml"}),
            WebsiteFetchResponse(200, _html("A", "Amber revised"), {"content-type": "text/html"}),
            WebsiteFetchResponse(200, _html("C", "New character"), {"content-type": "text/html"}),
            WebsiteFetchResponse(200, root_two, {"content-type": "text/html", "etag": '"two"'}),
        ]
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    service = KnowledgeFabricWebsiteCollectionSyncService(
        sync_repository=KnowledgeFabricExternalSyncRepository(database),
        collection_repository=KnowledgeFabricSiteCollectionRepository(database),
        ingestion_service=KnowledgeFabricIngestionService(
            content, storage, object_key_prefix="knowledge"
        ),
        fetcher=fetcher,
        url_guard=_guard(),
    )
    first = asyncio.run(service.sync(source.id, checked_at=datetime(2026, 8, 27, tzinfo=UTC)))
    index = KnowledgeFabricIndexRepository(database)
    second = asyncio.run(service.sync(source.id, checked_at=datetime(2026, 8, 27, 1, tzinfo=UTC)))
    assert (first.outcome, second.outcome) == ("changed", "changed")
    assert fetcher.calls == [
        "https://example.test/wiki",
        "https://example.test/sitemap.xml",
        "https://example.test/a",
        "https://example.test/b",
        "https://example.test/wiki",
        "https://example.test/wiki",
        "https://example.test/sitemap.xml",
        "https://example.test/a",
        "https://example.test/c",
        "https://example.test/wiki",
    ]
    with database.session() as session:
        current_version_ids = tuple(
            session.scalars(
                select(KnowledgeSourceCurrentEntryRecord.current_source_version_id).where(
                    KnowledgeSourceCurrentEntryRecord.source_id == source.id,
                    KnowledgeSourceCurrentEntryRecord.status == "available",
                )
            )
        )
    for version_id in current_version_ids:
        assert version_id is not None
        index.rebuild_entries_for_source_version(version_id)
    candidates = index.search_sparse(
        authorized_corpus_ids=frozenset({corpus.id}), query="Amber Removed New", candidate_limit=10
    )
    assert {candidate.text_content for candidate in candidates} == {
        "Amber revised",
        "New character",
    }
    with database.session() as session:
        removed = session.scalar(
            select(KnowledgeSourceCurrentEntryRecord).where(
                KnowledgeSourceCurrentEntryRecord.source_id == source.id,
                KnowledgeSourceCurrentEntryRecord.entry_locator == "https://example.test/b",
            )
        )
    assert removed is not None and removed.status == "removed"


def test_sitemap_index_and_page_validators_preserve_current_pages_on_304(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'sitemap.db'}")
    database.initialize()
    storage = _Storage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Wiki", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type=WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
        locator="https://example.test/wiki",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    sitemap_index = (
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<sitemap><loc>https://example.test/characters.xml</loc></sitemap>"
        b"</sitemapindex>"
    )
    character_sitemap = (
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<url><loc>https://example.test/amber</loc></url></urlset>"
    )
    fetcher = _QueueFetcher(
        [
            WebsiteFetchResponse(
                200,
                _html("Wiki", "Root"),
                {"content-type": "text/html", "etag": '"root-v1"'},
            ),
            WebsiteFetchResponse(200, sitemap_index, {"content-type": "application/xml"}),
            WebsiteFetchResponse(200, character_sitemap, {"content-type": "application/xml"}),
            WebsiteFetchResponse(
                200,
                _html("Amber", "Pyro archer"),
                {"content-type": "text/html", "etag": '"amber-v1"'},
            ),
            WebsiteFetchResponse(
                200,
                _html("Wiki", "Root"),
                {"content-type": "text/html", "etag": '"root-v1"'},
            ),
            WebsiteFetchResponse(304, b"", {"content-type": "text/html"}),
            WebsiteFetchResponse(200, sitemap_index, {"content-type": "application/xml"}),
            WebsiteFetchResponse(200, character_sitemap, {"content-type": "application/xml"}),
            WebsiteFetchResponse(304, b"", {"content-type": "text/html"}),
            WebsiteFetchResponse(304, b"", {"content-type": "text/html"}),
        ]
    )
    service = KnowledgeFabricWebsiteCollectionSyncService(
        sync_repository=KnowledgeFabricExternalSyncRepository(database),
        collection_repository=KnowledgeFabricSiteCollectionRepository(database),
        ingestion_service=KnowledgeFabricIngestionService(
            KnowledgeFabricContentRepository(database, object_storage=storage),
            storage,
            object_key_prefix="knowledge",
        ),
        fetcher=fetcher,
        url_guard=_guard(),
    )
    first = asyncio.run(service.sync(source.id, checked_at=datetime(2026, 8, 27, tzinfo=UTC)))
    second = asyncio.run(service.sync(source.id, checked_at=datetime(2026, 8, 27, 1, tzinfo=UTC)))
    assert (first.outcome, second.outcome, second.source_version_id) == (
        "changed",
        "not_modified",
        None,
    )
    with database.session() as session:
        version_count = len(
            session.scalars(
                select(KnowledgeSourceVersionRecord).where(
                    KnowledgeSourceVersionRecord.source_id == source.id
                )
            ).all()
        )
        assert version_count == 2
        pages = list(
            session.scalars(
                select(KnowledgeExternalSourcePageStateRecord)
                .where(KnowledgeExternalSourcePageStateRecord.source_id == source.id)
                .order_by(KnowledgeExternalSourcePageStateRecord.locator)
            )
        )
    assert [(page.locator, page.status, page.etag) for page in pages] == [
        ("https://example.test/amber", "available", '"amber-v1"'),
        ("https://example.test/wiki", "available", '"root-v1"'),
    ]


def test_collection_imports_admitted_page_images_as_private_assets(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'image-assets.db'}")
    database.initialize()
    storage = _Storage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Wiki", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type=WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
        locator="https://example.test/wiki",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    page = (
        b"<html><head><title>Amber</title></head><body><main>"
        b"<p>Outrider</p><img src=\"/amber.png\" alt=\"Amber portrait\">"
        b"</main></body></html>"
    )
    png = b"\x89PNG\r\n\x1a\nportrait"
    service = KnowledgeFabricWebsiteCollectionSyncService(
        sync_repository=KnowledgeFabricExternalSyncRepository(database),
        collection_repository=KnowledgeFabricSiteCollectionRepository(database),
        ingestion_service=KnowledgeFabricIngestionService(
            KnowledgeFabricContentRepository(database, object_storage=storage),
            storage,
            object_key_prefix="knowledge",
        ),
        fetcher=_QueueFetcher(
            [
                WebsiteFetchResponse(200, page, {"content-type": "text/html"}),
                WebsiteFetchResponse(404, b"", {"content-type": "text/xml"}),
                WebsiteFetchResponse(200, page, {"content-type": "text/html"}),
                WebsiteFetchResponse(200, png, {"content-type": "image/png"}),
            ]
        ),
        url_guard=_guard(),
    )
    result = asyncio.run(service.sync(source.id, checked_at=datetime(2026, 8, 27, tzinfo=UTC)))
    assert result.outcome == "changed"
    with database.session() as session:
        asset = session.scalar(select(KnowledgeAssetReferenceRecord))
    assert asset is not None
    assert png in storage.objects.values()
