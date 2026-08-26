from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import select

from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_object_storage import (
    ObjectStorageConflict,
    ObjectStorageError,
    S3CompatibleKnowledgeObjectStorage,
    StoredKnowledgeObject,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    CanonicalSectionInput,
    KnowledgeExternalScheduleClaimLost,
    KnowledgeFabricContentRepository,
    KnowledgeIngestionAlreadyRunning,
    KnowledgeSourceVersionConflict,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCorpusRecord,
    KnowledgeExternalSourceScheduleRecord,
    KnowledgeExternalSourceSyncStateRecord,
    KnowledgeObjectArtifactRecord,
    KnowledgeSourceRecord,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


@dataclass
class FakeObjectStorage:
    objects: dict[str, tuple[bytes, str, dict[str, str]]]
    fail_upload: bool = False
    fail_delete: bool = False
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
        if self.fail_upload:
            raise ObjectStorageError("R2 credential must never be persisted.")
        current = self.objects.get(object_key)
        if current is not None and current[:2] != (content, content_type):
            raise ObjectStorageConflict("content conflict")
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
        if self.fail_delete:
            raise ObjectStorageError("R2 delete failure")
        return self.objects.pop(object_key, None) is not None


class FakeS3Missing(Exception):
    def __init__(self) -> None:
        self.response = {"Error": {"Code": "404"}}


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, object]] = {}
        self.put_requests: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> Mapping[str, object]:
        self.put_requests.append(dict(kwargs))
        key = str(kwargs["Key"])
        self.objects[key] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs["ContentType"],
            "Metadata": kwargs["Metadata"],
        }
        return {}

    def head_object(self, **kwargs: object) -> Mapping[str, object]:
        key = str(kwargs["Key"])
        record = self.objects.get(key)
        if record is None:
            raise FakeS3Missing
        body = record["Body"]
        assert isinstance(body, bytes)
        return {
            "ContentLength": len(body),
            "ContentType": record["ContentType"],
            "Metadata": record["Metadata"],
        }

    def get_object(self, **kwargs: object) -> Mapping[str, object]:
        key = str(kwargs["Key"])
        record = self.objects[key]
        body = record["Body"]
        assert isinstance(body, bytes)
        return {"Body": _ReadableBytes(body)}

    def delete_object(self, **kwargs: object) -> Mapping[str, object]:
        self.objects.pop(str(kwargs["Key"]), None)
        return {}


class _ReadableBytes:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value


def _service(tmp_path: Path, storage: FakeObjectStorage) -> tuple[
    Database,
    KnowledgeFabricRepository,
    KnowledgeFabricContentRepository,
    KnowledgeFabricIngestionService,
    str,
]:
    database = Database(f"sqlite:///{tmp_path / 'knowledge-phase3.db'}")
    database.initialize()
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Global Fabric",
        description="",
        default_authority_profile="standard",
        status="active",
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
    service = KnowledgeFabricIngestionService(
        content,
        storage,
        object_key_prefix="knowledge-fabric",
    )
    return database, fabric, content, service, source.id


def _request(
    source_id: str,
    *,
    content: bytes = b"Canonical knowledge",
) -> SourceSnapshotIngestionRequest:
    return SourceSnapshotIngestionRequest(
        source_id=source_id,
        version_key="revision-1",
        idempotency_key="delivery-1",
        artifact_content=content,
        artifact_content_type="text/markdown",
        published_at=datetime(2026, 8, 25, tzinfo=UTC),
        metadata={"revision": "revision-1"},
        documents=(
            CanonicalDocumentInput(
                canonical_locator="https://docs.example.test/fabric",
                title="Fabric",
                mime_type="text/markdown",
                sections=(
                    CanonicalSectionInput(
                        structural_path="heading:0",
                        heading="Overview",
                        ordinal=0,
                        coordinates={"line": 1},
                    ),
                ),
                blocks=(
                    CanonicalBlockInput(
                        structural_path="paragraph:0",
                        block_type="paragraph",
                        ordinal=0,
                        section_path="heading:0",
                        text_content="Canonical knowledge",
                        coordinates={"line_start": 2, "line_end": 2},
                    ),
                ),
            ),
        ),
    )


def test_snapshot_is_immutable_content_addressed_and_invalidates_dependents(tmp_path: Path) -> None:
    storage = FakeObjectStorage(objects={})
    _, _, content, service, source_id = _service(tmp_path, storage)

    version = service.ingest_snapshot(_request(source_id))
    again = service.ingest_snapshot(_request(source_id))

    assert again.id == version.id
    assert storage.put_calls == 1
    artifact = content.get_artifact(version.artifact_id)
    assert artifact is not None
    assert artifact.content_sha256 == sha256(b"Canonical knowledge").hexdigest()
    assert artifact.object_key.startswith(f"knowledge-fabric/{source_id}/")
    assert "http" not in artifact.object_key
    assert storage.get_private(object_key=artifact.object_key) == b"Canonical knowledge"
    evidence = content.list_evidence_units(version.id)
    assert [(item.evidence_locator, item.text_content) for item in evidence] == [
        ("https://docs.example.test/fabric#paragraph:0", "Canonical knowledge")
    ]
    assert [item.dependency_type for item in content.list_pending_invalidations(version.id)] == [
        "indexes",
        "projections",
    ]
    document = content.list_canonical_documents(version.id)[0]
    block = content.list_canonical_blocks(document.id)[0]
    asset = content.create_asset_reference(
        document_id=document.id,
        block_id=block.id,
        artifact_id=artifact.id,
        asset_type="source_snapshot",
        structural_path="asset:source",
        coordinates={"role": "original"},
    )
    assert [item.id for item in content.list_asset_references(document.id)] == [asset.id]

    with pytest.raises(KnowledgeSourceVersionConflict):
        service.ingest_snapshot(
            replace(
                _request(source_id, content=b"Different source"),
                idempotency_key="delivery-2",
            )
        )
    assert len(content.list_source_versions(source_id)) == 1


def test_storage_failure_keeps_source_version_unpublished_and_error_redacted(
    tmp_path: Path,
) -> None:
    storage = FakeObjectStorage(objects={}, fail_upload=True)
    _, _, content, service, source_id = _service(tmp_path, storage)

    with pytest.raises(ObjectStorageError):
        service.ingest_snapshot(_request(source_id))

    assert content.list_source_versions(source_id) == []
    job = content.get_or_create_ingestion_job(
        source_id=source_id,
        job_type="source_snapshot",
        idempotency_key="delivery-1",
    )
    assert job.status == "failed"
    assert job.error_code == "object_storage_failed"
    assert "credential" not in job.error_code


def test_restart_recovery_requeues_running_job_without_duplicate_version(tmp_path: Path) -> None:
    storage = FakeObjectStorage(objects={})
    _, _, content, service, source_id = _service(tmp_path, storage)
    job = content.get_or_create_ingestion_job(
        source_id=source_id,
        job_type="source_snapshot",
        idempotency_key="delivery-1",
    )
    content.claim_ingestion_job(job.id)

    assert service.recover_interrupted_jobs() == 1
    version = service.ingest_snapshot(_request(source_id))
    recovered = content.get_ingestion_job(job.id)

    assert recovered is not None
    assert recovered.status == "completed"
    assert recovered.attempt_count == 2
    assert recovered.source_version_id == version.id
    assert {checkpoint.stage for checkpoint in content.list_ingestion_checkpoints(job.id)} >= {
        "acquiring",
        "recovered",
        "published",
    }


def test_ingestion_claim_allows_only_one_active_attempt(tmp_path: Path) -> None:
    storage = FakeObjectStorage(objects={})
    _, _, content, _, source_id = _service(tmp_path, storage)
    job = content.get_or_create_ingestion_job(
        source_id=source_id,
        job_type="source_snapshot",
        idempotency_key="claim-once",
    )

    claimed = content.claim_ingestion_job(job.id)

    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    with pytest.raises(KnowledgeIngestionAlreadyRunning):
        content.claim_ingestion_job(job.id)


def test_stale_external_schedule_claim_cannot_publish_a_private_snapshot(tmp_path: Path) -> None:
    storage = FakeObjectStorage(objects={})
    database, _fabric, content, service, source_id = _service(tmp_path, storage)
    with database.session() as session:
        session.add(
            KnowledgeExternalSourceScheduleRecord(
                source_id=source_id,
                enabled=True,
                lease_token="expired-claim",
                lease_expires_at=datetime(2026, 8, 25, tzinfo=UTC),
            )
        )
        session.commit()

    with pytest.raises(KnowledgeExternalScheduleClaimLost):
        service.ingest_snapshot(
            replace(
                _request(source_id),
                idempotency_key="expired-claim",
                external_schedule_lease_token="expired-claim",
            )
        )

    assert content.list_source_versions(source_id) == []
    assert storage.objects == {}
    failed = content.get_or_create_ingestion_job(
        source_id=source_id,
        job_type="source_snapshot",
        idempotency_key="expired-claim",
    )
    assert failed.error_code == "schedule_claim_lost"


def test_failed_publish_keeps_a_durable_private_object_deletion_tombstone(tmp_path: Path) -> None:
    storage = FakeObjectStorage(objects={})
    _database, _fabric, content, service, source_id = _service(tmp_path, storage)
    storage.fail_delete = True
    malformed = CanonicalDocumentInput(
        canonical_locator="https://docs.example.test/bad",
        title="Bad",
        mime_type="text/plain",
        sections=(
            CanonicalSectionInput(
                structural_path="child",
                heading="Child",
                ordinal=0,
                parent_path="missing",
            ),
        ),
    )

    with pytest.raises(ValueError, match="parent must precede"):
        service.ingest_snapshot(
            replace(
                _request(source_id),
                version_key="bad-revision",
                idempotency_key="bad-delivery",
                documents=(malformed,),
            )
        )

    assert content.list_source_versions(source_id) == []
    assert len(storage.objects) == 1
    pending = content.list_pending_object_deletions()
    assert len(pending) == 1
    assert (pending[0].attempt_count, pending[0].error_code) == (1, "object_storage_failed")

    storage.fail_delete = False
    service.recover_interrupted_jobs()

    assert storage.objects == {}
    assert content.list_pending_object_deletions() == []


def test_account_deletion_removes_private_object_and_all_derived_content(tmp_path: Path) -> None:
    storage = FakeObjectStorage(objects={})
    database, fabric, content, service, source_id = _service(tmp_path, storage)
    with database.session() as session:
        session.add(
            KnowledgeCorpusRecord(
                id="user-corpus",
                name="User corpus",
                owner_type="user",
                owner_id="user-1",
                visibility="private",
                default_authority_profile="standard",
                status="active",
            )
        )
        session.flush()
        source = session.get(KnowledgeSourceRecord, source_id)
        assert source is not None
        source.corpus_id = "user-corpus"
        session.add(
            KnowledgeExternalSourceSyncStateRecord(
                source_id=source_id,
                last_outcome="changed",
            )
        )
        session.add(
            KnowledgeExternalSourceScheduleRecord(
                source_id=source_id,
                enabled=False,
            )
        )
        session.commit()
    version = service.ingest_snapshot(_request(source_id))
    artifact = content.get_artifact(version.artifact_id)
    assert artifact is not None
    document = content.list_canonical_documents(version.id)[0]
    content.create_asset_reference(
        document_id=document.id,
        artifact_id=artifact.id,
        asset_type="source_snapshot",
        structural_path="asset:source",
    )

    counts = fabric.delete_owner("user-1")

    assert counts["knowledge_fabric_source_versions"] == 1
    assert counts["knowledge_fabric_object_artifacts"] == 1
    assert counts["knowledge_fabric_evidence_units"] == 1
    assert counts["knowledge_fabric_asset_references"] == 1
    assert counts["knowledge_fabric_external_source_schedules"] == 1
    assert counts["knowledge_fabric_external_source_sync_states"] == 1
    assert artifact.object_key not in storage.objects
    with database.session() as session:
        assert session.get(KnowledgeObjectArtifactRecord, artifact.id) is None
        assert (
            session.scalar(
                select(KnowledgeSourceRecord).where(KnowledgeSourceRecord.id == source_id)
            )
            is None
        )
        assert session.get(KnowledgeExternalSourceSyncStateRecord, source_id) is None
        assert session.get(KnowledgeExternalSourceScheduleRecord, source_id) is None


def test_account_deletion_removes_database_access_before_retrying_private_object_cleanup(
    tmp_path: Path,
) -> None:
    storage = FakeObjectStorage(objects={})
    database, fabric, content, service, source_id = _service(tmp_path, storage)
    with database.session() as session:
        session.add(
            KnowledgeCorpusRecord(
                id="user-corpus",
                name="User corpus",
                owner_type="user",
                owner_id="user-1",
                visibility="private",
                default_authority_profile="standard",
                status="active",
            )
        )
        source = session.get(KnowledgeSourceRecord, source_id)
        assert source is not None
        source.corpus_id = "user-corpus"
        session.commit()
    version = service.ingest_snapshot(_request(source_id))
    artifact = content.get_artifact(version.artifact_id)
    assert artifact is not None
    storage.fail_delete = True

    counts = fabric.delete_owner("user-1")

    assert counts["knowledge_fabric_object_deletions_pending"] == 1
    assert artifact.object_key in storage.objects
    with database.session() as session:
        assert session.get(KnowledgeObjectArtifactRecord, artifact.id) is None
        assert session.get(KnowledgeCorpusRecord, "user-corpus") is None
        assert session.get(KnowledgeSourceRecord, source_id) is None
    pending = content.list_pending_object_deletions()
    assert len(pending) == 1
    assert pending[0].error_code == "object_storage_failed"

    storage.fail_delete = False
    assert content.process_pending_object_deletions() == 1
    assert artifact.object_key not in storage.objects
    assert content.list_pending_object_deletions() == []


def test_s3_compatible_storage_stays_private_and_reuses_matching_content() -> None:
    client = FakeS3Client()
    storage = S3CompatibleKnowledgeObjectStorage(
        provider="cloudflare_r2",
        bucket="knowledge-private",
        client=client,
    )

    first = storage.put_private(
        object_key="knowledge-fabric/source/aa/hash",
        content=b"artifact",
        content_type="text/plain",
        metadata={"source-id": "source"},
    )
    second = storage.put_private(
        object_key="knowledge-fabric/source/aa/hash",
        content=b"artifact",
        content_type="text/plain",
        metadata={"source-id": "source"},
    )

    assert first == second
    assert len(client.put_requests) == 1
    assert "ACL" not in client.put_requests[0]
    assert storage.get_private(object_key=first.object_key) == b"artifact"
    assert storage.delete_private(object_key=first.object_key)
    assert not storage.delete_private(object_key=first.object_key)


def test_source_version_mutation_request_helper_has_no_hidden_test_secret() -> None:
    """Keep fixture values visibly public/non-secret for redaction regression scans."""

    request = _request("source")
    assert request.metadata == {"revision": "revision-1"}
    assert not any("secret" in str(value).casefold() for value in request.metadata.values())
