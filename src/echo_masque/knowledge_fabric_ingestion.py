"""Deterministic snapshot ingestion orchestration outside the Character reply path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from echo_masque.knowledge_fabric_ingestion_policy import deterministic_artifact_key
from echo_masque.knowledge_object_storage import KnowledgeObjectStorage, ObjectStorageError
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalDocumentInput,
    KnowledgeFabricContentRepository,
    KnowledgeIngestionAlreadyRunning,
    KnowledgeSourceVersionConflict,
)
from echo_masque.persistence.knowledge_fabric_models import KnowledgeSourceVersionRecord


@dataclass(frozen=True, slots=True)
class SourceSnapshotIngestionRequest:
    """One adapter-produced snapshot; no LLM output is required or accepted here."""

    source_id: str
    version_key: str
    idempotency_key: str
    artifact_content: bytes
    artifact_content_type: str
    documents: Sequence[CanonicalDocumentInput] = ()
    published_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    activate_git_version: bool = False


class KnowledgeFabricIngestionService:
    """Coordinate idempotent private upload then atomic source-version publication."""

    def __init__(
        self,
        repository: KnowledgeFabricContentRepository,
        object_storage: KnowledgeObjectStorage,
        *,
        object_key_prefix: str,
    ) -> None:
        self.repository = repository
        self.object_storage = object_storage
        self.object_key_prefix = object_key_prefix

    def ingest_snapshot(
        self,
        request: SourceSnapshotIngestionRequest,
    ) -> KnowledgeSourceVersionRecord:
        """Publish a source version only after its private artifact is durable."""

        if request.activate_git_version:
            self.repository.require_git_source(request.source_id)
        source_hash = sha256(request.artifact_content).hexdigest()
        job = self.repository.get_or_create_ingestion_job(
            source_id=request.source_id,
            job_type="source_snapshot",
            idempotency_key=request.idempotency_key,
        )
        if job.source_version_id is not None:
            version = self.repository.get_source_version(job.source_version_id)
            if version is not None:
                if request.activate_git_version:
                    return self.repository.activate_git_version_as_current(
                        source_id=request.source_id,
                        source_version_id=version.id,
                    )
                return version
        try:
            claimed = self.repository.claim_ingestion_job(job.id)
        except KnowledgeIngestionAlreadyRunning:
            raise
        if claimed.source_version_id is not None:
            version = self.repository.get_source_version(claimed.source_version_id)
            if version is not None:
                if request.activate_git_version:
                    return self.repository.activate_git_version_as_current(
                        source_id=request.source_id,
                        source_version_id=version.id,
                    )
                return version

        existing = self.repository.get_source_version_by_key(
            source_id=request.source_id,
            version_key=request.version_key,
        )
        if existing is not None:
            if existing.source_hash != source_hash:
                self.repository.fail_ingestion_job(job_id=claimed.id, error_code="version_conflict")
                raise KnowledgeSourceVersionConflict(
                    "Knowledge source version key already refers to different content."
                )
            return self.repository.complete_existing_version_job(
                job_id=claimed.id,
                source_version_id=existing.id,
                activate_git_version=request.activate_git_version,
            )

        object_key = deterministic_artifact_key(
            prefix=self.object_key_prefix,
            source_id=request.source_id,
            content_sha256=source_hash,
        )
        try:
            artifact = self.object_storage.put_private(
                object_key=object_key,
                content=request.artifact_content,
                content_type=request.artifact_content_type,
                metadata={"source-id": request.source_id},
            )
        except ObjectStorageError:
            self.repository.fail_ingestion_job(
                job_id=claimed.id,
                error_code="object_storage_failed",
            )
            raise
        try:
            return self.repository.publish_source_snapshot(
                job_id=claimed.id,
                source_id=request.source_id,
                version_key=request.version_key,
                source_hash=source_hash,
                artifact=artifact,
                published_at=request.published_at,
                metadata=request.metadata,
                documents=request.documents,
                activate_git_version=request.activate_git_version,
            )
        except Exception:
            self.repository.fail_ingestion_job(job_id=claimed.id, error_code="persistence_failed")
            raise

    def recover_interrupted_jobs(self) -> int:
        """Call on a worker restart before accepting another snapshot delivery."""

        return self.repository.requeue_interrupted_ingestion_jobs()


__all__ = ["KnowledgeFabricIngestionService", "SourceSnapshotIngestionRequest"]
