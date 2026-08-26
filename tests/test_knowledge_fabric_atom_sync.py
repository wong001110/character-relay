from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import SimpleNamespace

from echo_masque.knowledge_fabric_atom_sync import KnowledgeFabricAtomSyncService
from echo_masque.knowledge_fabric_ingestion import SourceSnapshotIngestionRequest
from echo_masque.knowledge_fabric_website_sync import WebsiteFetchResponse
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    ExternalSourceScheduleClaim,
)


class _SyncRepository:
    def __init__(self) -> None:
        self.outcomes: list[dict[str, object]] = []

    def schedule_claim_is_current(
        self,
        *,
        source_id: str,
        lease_token: str,
        now: object,
    ) -> bool:
        del now
        return (source_id, lease_token) == ("source-1", "lease-1")

    def require_public_https_source(
        self,
        source_id: str,
        *,
        allowed_source_types: frozenset[str],
    ) -> SimpleNamespace:
        assert source_id == "source-1"
        assert allowed_source_types == frozenset({"atom_public_https"})
        return SimpleNamespace(locator="https://example.test/feed")

    def get_state(self, source_id: str) -> None:
        assert source_id == "source-1"
        return None

    def record_outcome(self, **kwargs: object) -> object:
        self.outcomes.append(kwargs)
        return object()


class _IngestionRepository:
    def get_source_version_by_key(self, *, source_id: str, version_key: str) -> None:
        assert source_id == "source-1"
        assert version_key.startswith("atom:")
        return None


class _IngestionService:
    def __init__(self) -> None:
        self.repository = _IngestionRepository()
        self.request: SourceSnapshotIngestionRequest | None = None

    def ingest_snapshot(self, request: SourceSnapshotIngestionRequest) -> SimpleNamespace:
        self.request = request
        return SimpleNamespace(id="version-1")


class _Fetcher:
    async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse:
        assert url == "https://example.test/feed"
        assert headers["Accept"].startswith("application/atom+xml")
        return WebsiteFetchResponse(
            status_code=200,
            content=(
                b'<feed xmlns="http://www.w3.org/2005/Atom"><title>News</title>'
                b"<entry><id>entry-1</id><title>First</title><summary>Safe evidence.</summary>"
                b"</entry></feed>"
            ),
            headers={"content-type": "application/atom+xml"},
        )


def test_atom_scheduler_claim_is_fenced_through_snapshot_publication_and_state() -> None:
    sync_repository = _SyncRepository()
    ingestion = _IngestionService()
    service = KnowledgeFabricAtomSyncService(
        sync_repository=sync_repository,  # type: ignore[arg-type]
        ingestion_service=ingestion,  # type: ignore[arg-type]
        fetcher=_Fetcher(),
    )
    claim = ExternalSourceScheduleClaim(
        source_id="source-1",
        source_type="atom_public_https",
        hostname="example.test",
        lease_token="lease-1",
    )

    result = asyncio.run(service.sync_claim(claim))

    assert result.source_version_id == "version-1"
    assert ingestion.request is not None
    assert ingestion.request.external_schedule_lease_token == claim.lease_token
    assert len(sync_repository.outcomes) == 1
    outcome = sync_repository.outcomes[0]
    assert outcome["source_id"] == "source-1"
    assert outcome["outcome"] == "changed"
    assert outcome["changed"] is True
    assert outcome["schedule_lease_token"] == "lease-1"
    assert outcome["allowed_source_types"] == frozenset({"atom_public_https"})
