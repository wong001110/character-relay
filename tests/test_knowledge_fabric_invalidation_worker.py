from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import sleep

from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_fabric_invalidation_worker import KnowledgeFabricInvalidationWorker
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_index_repository import KnowledgeFabricIndexRepository
from echo_masque.persistence.knowledge_fabric_invalidation_repository import (
    KnowledgeFabricInvalidationRepository,
)
from echo_masque.persistence.knowledge_fabric_models import KnowledgeDependencyInvalidationRecord
from echo_masque.persistence.knowledge_fabric_projection_repository import (
    KnowledgeFabricProjectionRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


@dataclass
class _Storage:
    objects: dict[str, bytes]

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        del metadata
        self.objects[object_key] = content
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


def _request(source_id: str, version: str, text: str) -> SourceSnapshotIngestionRequest:
    return SourceSnapshotIngestionRequest(
        source_id=source_id,
        version_key=version,
        idempotency_key=f"delivery-{version}",
        artifact_content=text.encode(),
        artifact_content_type="text/plain",
        documents=(
            CanonicalDocumentInput(
                canonical_locator="https://docs.example.test/fabric",
                title="Fabric",
                mime_type="text/plain",
                blocks=(
                    CanonicalBlockInput(
                        structural_path="paragraph:0",
                        block_type="paragraph",
                        ordinal=0,
                        text_content=text,
                    ),
                ),
            ),
        ),
    )


def _worker(tmp_path: Path) -> tuple[
    Database,
    KnowledgeFabricIngestionService,
    KnowledgeFabricInvalidationRepository,
    KnowledgeFabricInvalidationWorker,
    str,
]:
    database = Database(f"sqlite:///{tmp_path / 'derived-work.db'}")
    database.initialize()
    storage = _Storage({})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Global", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="manual_text",
        locator="https://docs.example.test/fabric",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    ingest = KnowledgeFabricIngestionService(content, storage, object_key_prefix="knowledge-fabric")
    invalidations = KnowledgeFabricInvalidationRepository(database)
    worker = KnowledgeFabricInvalidationWorker(
        invalidations=invalidations,
        indexes=KnowledgeFabricIndexRepository(database),
        projections=KnowledgeFabricProjectionRepository(database),
    )
    return database, ingest, invalidations, worker, source.id


def test_worker_rebuilds_indexes_and_existing_projection_for_a_new_snapshot(tmp_path: Path) -> None:
    database, ingest, invalidations, worker, source_id = _worker(tmp_path)
    ingest.ingest_snapshot(_request(source_id, "one", "first evidence"))
    projections = KnowledgeFabricProjectionRepository(database)
    projections.get_source_overview(source_id)

    assert asyncio.run(worker.run_once()) == 1
    assert asyncio.run(worker.run_once()) == 1
    second = ingest.ingest_snapshot(_request(source_id, "two", "second evidence"))

    assert asyncio.run(worker.run_once()) == 1
    assert asyncio.run(worker.run_once()) == 1
    indexes = KnowledgeFabricIndexRepository(database).rebuild_entries_for_source_version(second.id)
    assert [entry.retrieval_text for entry in indexes] == ["second evidence"]
    projection = projections.get_source_overview(source_id)
    assert projection is not None
    assert projection.source_hash == second.source_hash
    assert invalidations.summary_for_source_ids((source_id,))[source_id].pending == 0
    assert invalidations.summary_for_source_ids((source_id,))[source_id].running == 0


def test_failed_work_retries_with_a_lease_then_requires_explicit_source_retry(
    tmp_path: Path,
) -> None:
    database, ingest, invalidations, _worker_instance, source_id = _worker(tmp_path)
    version = ingest.ingest_snapshot(_request(source_id, "one", "evidence"))
    now = datetime(2026, 8, 26, tzinfo=UTC)

    first = invalidations.claim_due(now=now)
    assert len(first) == 2
    target_id = first[0].invalidation_id
    assert invalidations.fail(claim=first[0], error_code="derived_work_failed", now=now)
    assert invalidations.claim_due(now=now + timedelta(seconds=59)) == []
    second = next(
        claim
        for claim in invalidations.claim_due(now=now + timedelta(seconds=60))
        if claim.invalidation_id == target_id
    )
    assert invalidations.fail(claim=second, error_code="derived_work_failed", now=now)
    third = next(
        claim
        for claim in invalidations.claim_due(now=now + timedelta(seconds=120))
        if claim.invalidation_id == target_id
    )
    assert invalidations.fail(claim=third, error_code="derived_work_failed", now=now)

    assert invalidations.retry_failed_for_source(source_id, now=now + timedelta(hours=1)) == 1
    with database.session() as session:
        failed = session.get(KnowledgeDependencyInvalidationRecord, third.invalidation_id)
        assert failed is not None and failed.status == "pending"
    assert invalidations.recover_expired(now=now) == 0
    assert version.source_id == source_id


def test_expired_derived_work_claim_cannot_complete_or_fail_and_can_be_reclaimed(
    tmp_path: Path,
) -> None:
    _database, ingest, invalidations, _worker_instance, source_id = _worker(tmp_path)
    ingest.ingest_snapshot(_request(source_id, "one", "evidence"))
    now = datetime(2026, 8, 26, tzinfo=UTC)

    claim = invalidations.claim_due(limit=1, lease_seconds=30, now=now)[0]

    assert not invalidations.complete(claim=claim, now=now + timedelta(seconds=31))
    assert not invalidations.fail(
        claim=claim,
        error_code="derived_work_failed",
        now=now + timedelta(seconds=31),
    )
    replacement = invalidations.claim_due(limit=1, now=now + timedelta(seconds=31))[0]
    assert replacement.invalidation_id == claim.invalidation_id
    assert replacement.lease_token != claim.lease_token


class _SlowInvalidations:
    def claim_due(self, *, limit: int, lease_seconds: int) -> list[object]:
        del limit, lease_seconds
        sleep(0.05)
        return []


def test_worker_moves_blocking_claim_work_off_the_event_loop() -> None:
    worker = KnowledgeFabricInvalidationWorker(
        invalidations=_SlowInvalidations(),  # type: ignore[arg-type]
        indexes=object(),  # type: ignore[arg-type]
        projections=object(),  # type: ignore[arg-type]
    )

    async def run() -> None:
        task = asyncio.create_task(worker.run_once())
        await asyncio.sleep(0)
        assert not task.done()
        assert await task == 0

    asyncio.run(run())
