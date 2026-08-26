from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
    WebsiteSourceRejected,
    canonical_public_https_locator,
    conditional_request_headers,
    normalized_website_validator,
    website_response_error_code,
    website_response_idempotency_key,
    website_response_version_key,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_fabric_website_adapter import (
    KnowledgeFabricWebsiteAdapter,
    WebsiteResponseInput,
)
from echo_masque.knowledge_fabric_website_sync import (
    KnowledgeFabricWebsiteSyncService,
    WebsiteFetchResponse,
)
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.network_safety import PublicUrlGuard
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    KnowledgeFabricExternalScheduleRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)
from echo_masque.persistence.knowledge_fabric_index_repository import (
    KnowledgeFabricIndexRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord
from echo_masque.persistence.schema_migrations import KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION


@dataclass
class FakeObjectStorage:
    objects: dict[str, tuple[bytes, str, dict[str, str]]]
    put_calls: int = 0

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        self.put_calls += 1
        self.objects.setdefault(object_key, (content, content_type, dict(metadata)))
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="knowledge-private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key][0]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


class QueueFetcher:
    def __init__(self, responses: list[WebsiteFetchResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse:
        self.calls.append((url, dict(headers)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _guard() -> PublicUrlGuard:
    async def resolver(hostname: str) -> tuple[str, ...]:
        assert hostname == "example.test"
        return ("93.184.216.34",)

    return PublicUrlGuard(resolver)


def _service(
    tmp_path: Path,
    fetcher: QueueFetcher,
    *,
    locator: str = "https://example.test/guide",
    source_type: str = WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
) -> tuple[
    FakeObjectStorage,
    KnowledgeFabricContentRepository,
    KnowledgeFabricExternalSyncRepository,
    KnowledgeFabricWebsiteSyncService,
    str,
    Database,
]:
    database = Database(f"sqlite:///{tmp_path / 'website-sync.db'}")
    database.initialize()
    storage = FakeObjectStorage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Website Fabric",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type=source_type,
        locator=locator,
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    sync = KnowledgeFabricExternalSyncRepository(database)
    service = KnowledgeFabricWebsiteSyncService(
        sync_repository=sync,
        ingestion_service=KnowledgeFabricIngestionService(
            content,
            storage,
            object_key_prefix="knowledge-fabric",
        ),
        fetcher=fetcher,
        url_guard=_guard(),
    )
    return storage, content, sync, service, source.id, database


def test_website_policy_and_adapter_keep_one_canonical_public_text_contract() -> None:
    assert canonical_public_https_locator("https://EXAMPLE.test:443/guide") == "https://example.test/guide"
    assert canonical_public_https_locator("https://example.test") == "https://example.test/"
    assert canonical_public_https_locator("https://EXAMPLE.test./guide") == "https://example.test/guide"
    assert canonical_public_https_locator("https://docs.x/guide") == "https://docs.x/guide"
    rejected_locators = {
        "https://example.test:not-a-port/guide": r"^Website locator is invalid\.$",
        "https://./guide": r"^Website locator is invalid\.$",
        "http://example.test/guide": r"^Website locator must use HTTPS\.$",
        "https:///guide": r"^Website locator must use HTTPS\.$",
        "https://user@example.test/guide": (
            r"^Website locator contains unsupported authority or state\.$"
        ),
        "https://user:password@example.test/guide": (
            r"^Website locator contains unsupported authority or state\.$"
        ),
        "https://example.test/guide?token=secret": (
            r"^Website locator contains unsupported authority or state\.$"
        ),
        "https://example.test/guide#section": (
            r"^Website locator contains unsupported authority or state\.$"
        ),
        "https://example.test:8443/guide": r"^Website locator uses an unsupported port\.$",
    }
    for locator, message in rejected_locators.items():
        with pytest.raises(WebsiteSourceRejected, match=message):
            canonical_public_https_locator(locator)
    assert conditional_request_headers(etag=None, last_modified=None) == {
        "Accept": "text/html,text/markdown,text/plain;q=0.9"
    }
    assert conditional_request_headers(etag="", last_modified="") == {
        "Accept": "text/html,text/markdown,text/plain;q=0.9"
    }
    assert conditional_request_headers(etag='"revision-1"', last_modified="Tue, 25 Aug 2026") == {
        "Accept": "text/html,text/markdown,text/plain;q=0.9",
        "If-None-Match": '"revision-1"',
        "If-Modified-Since": "Tue, 25 Aug 2026",
    }
    assert normalized_website_validator('  "revision-1"  ') == '"revision-1"'
    assert normalized_website_validator(None) is None
    assert normalized_website_validator("x" * 512) == "x" * 512
    response_cases = (
        (304, "", 0, "not_modified"),
        (401, "text/html", 1, "authorization_failed"),
        (403, "text/html", 1, "authorization_failed"),
        (300, "text/html", 1, "redirect_refused"),
        (399, "text/html", 1, "redirect_refused"),
        (400, "text/html", 1, "http_failed"),
        (201, "text/html", 1, "http_failed"),
        (200, "text/html", 0, "content_size_rejected"),
        (200, "text/html", 1_048_577, "content_size_rejected"),
        (200, "application/json", 1, "content_type_rejected"),
        (200, "TEXT/HTML; charset=utf-8", 1, None),
        (200, "text/html; charset=utf-8; revision=1", 1, None),
        (200, " text/markdown ; charset=utf-8", 1, None),
        (200, "text/plain", 1_048_576, None),
    )
    for status_code, content_type, content_size, expected in response_cases:
        assert website_response_error_code(
            status_code=status_code,
            content_type=content_type,
            content_size=content_size,
        ) == expected
    body = b"exact source identity"
    assert website_response_version_key(body) == f"website:{sha256(body).hexdigest()}"
    scoped_body = b"source-1\0" + body
    assert website_response_idempotency_key(source_id="source-1", content=body) == (
        f"website:{sha256(scoped_body).hexdigest()}"
    )
    with pytest.raises(WebsiteSourceRejected, match=r"^Website Source identity is required\.$"):
        website_response_idempotency_key(source_id=" ", content=body)

    request = KnowledgeFabricWebsiteAdapter().build_snapshot(
        WebsiteResponseInput(
            source_id="source-1",
            locator="https://example.test/guide",
            content=(
                b"<html><head><title>Guide</title></head><body><nav>ignore</nav><main>"
                b"<h1>Overview</h1><p>Current public evidence.</p><li>First item</li>"
                b"</main><footer>ignore</footer></body></html>"
            ),
            content_type="text/html; charset=utf-8",
            fetched_at=datetime(2026, 8, 25, tzinfo=UTC),
        )
    )
    document = request.documents[0]
    assert document.title == "Guide"
    assert [item.heading for item in document.sections] == ["Overview"]
    assert [(item.block_type, item.text_content) for item in document.blocks] == [
        ("paragraph", "Current public evidence."),
        ("list_item", "First item"),
    ]


def test_website_sync_publishes_changed_content_and_handles_conditional_no_change(
    tmp_path: Path,
) -> None:
    body_one = b"<html><body><main><h1>Guide</h1><p>First version.</p></main></body></html>"
    body_two = b"<html><body><main><h1>Guide</h1><p>Second version.</p></main></body></html>"
    fetcher = QueueFetcher(
        [
            WebsiteFetchResponse(200, body_one, {"content-type": "text/html", "etag": '"v1"'}),
            WebsiteFetchResponse(304, b"", {}),
            WebsiteFetchResponse(200, body_one, {"content-type": "text/html", "etag": '"v1"'}),
            WebsiteFetchResponse(
                200,
                body_two,
                {"content-type": "text/html", "etag": '"v2"', "last-modified": "Tue, 25 Aug 2026"},
            ),
        ]
    )
    storage, content, sync, service, source_id, database = _service(tmp_path, fetcher)
    first_time = datetime(2026, 8, 25, tzinfo=UTC)

    first = asyncio.run(service.sync(source_id, checked_at=first_time))
    second = asyncio.run(service.sync(source_id, checked_at=first_time + timedelta(minutes=1)))
    third = asyncio.run(service.sync(source_id, checked_at=first_time + timedelta(minutes=2)))
    fourth = asyncio.run(service.sync(source_id, checked_at=first_time + timedelta(minutes=3)))

    assert [item.outcome for item in (first, second, third, fourth)] == [
        "changed",
        "not_modified",
        "unchanged",
        "changed",
    ]
    assert storage.put_calls == 2
    assert fetcher.calls[1][1]["If-None-Match"] == '"v1"'
    assert fetcher.calls[2][1]["If-None-Match"] == '"v1"'
    state = sync.get_state(source_id)
    assert state is not None
    assert (state.etag, state.last_modified, state.last_outcome, state.last_error_code) == (
        '"v2"',
        "Tue, 25 Aug 2026",
        "changed",
        None,
    )
    source = content.get_source(source_id)
    assert source is not None
    expected_latest = (first_time + timedelta(minutes=3)).replace(tzinfo=None)
    assert source.last_checked_at == expected_latest
    assert source.last_changed_at == expected_latest
    versions = content.list_source_versions(source_id)
    assert len(versions) == 2
    assert all(content.list_evidence_units(version.id) for version in versions)
    index = KnowledgeFabricIndexRepository(database)
    for version in versions:
        index.rebuild_entries_for_source_version(version.id)
    source = content.get_source(source_id)
    assert source is not None
    candidates = index.search_sparse(
        authorized_corpus_ids=frozenset({source.corpus_id}),
        query="version",
        candidate_limit=10,
    )
    version_by_id = {version.id: version for version in versions}
    assert [
        (version_by_id[item.source_version_id].status, item.text_content) for item in candidates
    ] == [("available", "Second version.")]
    with database.session() as session:
        assert session.get(DatabaseSchemaMigrationRecord, KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION)


def test_website_sync_fails_closed_without_fetching_unsafe_or_non_website_sources(
    tmp_path: Path,
) -> None:
    fetcher = QueueFetcher([])
    _storage, content, sync, service, source_id, _database = _service(
        tmp_path,
        fetcher,
        locator="http://example.test/guide",
    )
    rejected = asyncio.run(service.sync(source_id, checked_at=datetime(2026, 8, 25, tzinfo=UTC)))
    assert rejected == type(rejected)(outcome="failed", error_code="source_rejected")
    assert fetcher.calls == []
    state = sync.get_state(source_id)
    assert state is not None and state.last_error_code == "source_rejected"
    assert content.list_source_versions(source_id) == []

    wrong_fetcher = QueueFetcher([])
    (tmp_path / "wrong").mkdir()
    _storage, _content, _sync, wrong_service, wrong_source_id, _database = _service(
        tmp_path / "wrong",
        wrong_fetcher,
        source_type="manual_text",
    )
    with pytest.raises(
        ValueError,
        match="External Website sync requires a public HTTPS Website Source",
    ):
        asyncio.run(wrong_service.sync(wrong_source_id))
    assert wrong_fetcher.calls == []


def test_website_sync_maps_network_auth_redirect_and_content_failures_to_safe_codes(
    tmp_path: Path,
) -> None:
    fetcher = QueueFetcher(
        [
            RuntimeError("provider details must not persist"),
            WebsiteFetchResponse(401, b"credential body", {"content-type": "text/html"}),
            WebsiteFetchResponse(302, b"", {"content-type": "text/html", "location": "https://elsewhere.test"}),
            WebsiteFetchResponse(200, b"binary", {"content-type": "application/octet-stream"}),
        ]
    )
    _storage, _content, sync, service, source_id, _database = _service(tmp_path, fetcher)

    results = [asyncio.run(service.sync(source_id)) for _ in range(4)]

    assert [result.error_code for result in results] == [
        "fetch_failed",
        "authorization_failed",
        "redirect_refused",
        "content_type_rejected",
    ]
    state = sync.get_state(source_id)
    assert state is not None
    assert state.last_outcome == "failed"
    assert state.last_error_code == "content_type_rejected"
    assert "provider details" not in (state.last_error_code or "")


def test_website_sync_rejects_unsafe_validator_before_publishing_content(tmp_path: Path) -> None:
    fetcher = QueueFetcher(
        [
            WebsiteFetchResponse(
                200,
                b"<html><body><main><p>Must not persist.</p></main></body></html>",
                {"content-type": "text/html", "etag": "valid\nnot-a-header"},
            )
        ]
    )
    storage, content, sync, service, source_id, _database = _service(tmp_path, fetcher)

    result = asyncio.run(service.sync(source_id, checked_at=datetime(2026, 8, 25, tzinfo=UTC)))

    assert result == type(result)(outcome="failed", error_code="validator_rejected")
    assert storage.put_calls == 0
    assert content.list_source_versions(source_id) == []
    state = sync.get_state(source_id)
    assert state is not None and state.last_error_code == "validator_rejected"
    for invalid in ("", " ", "bad\nvalidator", "x" * 513):
        with pytest.raises(
            WebsiteSourceRejected,
            match=r"^Website response validator is invalid\.$",
        ):
            normalized_website_validator(invalid)


def test_website_sync_claim_never_fetches_or_persists_after_its_schedule_lease_is_revoked(
    tmp_path: Path,
) -> None:
    fetcher = QueueFetcher(
        [
            WebsiteFetchResponse(
                200,
                b"<html><body><main><p>Must not publish.</p></main></body></html>",
                {"content-type": "text/html"},
            )
        ]
    )
    storage, content, sync, service, source_id, database = _service(tmp_path, fetcher)
    schedules = KnowledgeFabricExternalScheduleRepository(database)
    now = datetime(2026, 8, 26, tzinfo=UTC)
    schedules.configure(source_id=source_id, enabled=True, interval_seconds=900, now=now)
    claim = schedules.claim_due(limit=1, now=now)[0]
    schedules.configure(source_id=source_id, enabled=False, interval_seconds=900, now=now)

    result = asyncio.run(
        service.sync(
            source_id,
            checked_at=now,
            external_schedule_lease_token=claim.lease_token,
        )
    )

    assert result.outcome == "stale"
    assert fetcher.calls == []
    assert storage.put_calls == 0
    assert content.list_source_versions(source_id) == []
    assert sync.get_state(source_id) is None


def test_website_sync_rechecks_its_claim_after_fetch_before_starting_ingestion(
    tmp_path: Path,
) -> None:
    initial_fetcher = QueueFetcher([])
    storage, content, sync, service, source_id, database = _service(tmp_path, initial_fetcher)
    schedules = KnowledgeFabricExternalScheduleRepository(database)
    now = datetime(2026, 8, 26, tzinfo=UTC)
    schedules.configure(source_id=source_id, enabled=True, interval_seconds=900, now=now)
    claim = schedules.claim_due(limit=1, now=now)[0]

    class _RevokingFetcher:
        async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse:
            del url, headers
            schedules.configure(
                source_id=source_id,
                enabled=False,
                interval_seconds=900,
                now=now,
            )
            return WebsiteFetchResponse(
                200,
                b"<html><body><main><p>Must not publish.</p></main></body></html>",
                {"content-type": "text/html"},
            )

    service.fetcher = _RevokingFetcher()
    result = asyncio.run(
        service.sync(
            source_id,
            checked_at=now,
            external_schedule_lease_token=claim.lease_token,
        )
    )

    assert result.outcome == "stale"
    assert storage.put_calls == 0
    assert content.list_source_versions(source_id) == []
    assert sync.get_state(source_id) is None
