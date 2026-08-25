"""Immutable source/version/content persistence for Knowledge Fabric Phase 3."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from echo_masque.knowledge_fabric_ingestion_policy import (
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_QUEUED,
    JOB_RUNNING,
    may_claim_ingestion_job,
    may_requeue_ingestion_job,
    source_version_hash_matches,
)
from echo_masque.knowledge_object_storage import (
    KnowledgeObjectStorage,
    ObjectStorageUnavailable,
    StoredKnowledgeObject,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeAssetReferenceRecord,
    KnowledgeCanonicalBlockRecord,
    KnowledgeCanonicalDocumentRecord,
    KnowledgeCanonicalSectionRecord,
    KnowledgeDependencyInvalidationRecord,
    KnowledgeEvidenceUnitRecord,
    KnowledgeIngestionCheckpointRecord,
    KnowledgeIngestionJobRecord,
    KnowledgeObjectArtifactRecord,
    KnowledgeSourceRecord,
    KnowledgeSourceVersionRecord,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class KnowledgeSourceVersionConflict(ValueError):
    """A version key is immutable and cannot be reused for different content."""


class KnowledgeIngestionAlreadyRunning(RuntimeError):
    """Duplicate delivery must wait for recovery instead of publishing twice."""


@dataclass(frozen=True, slots=True)
class CanonicalSectionInput:
    """Parser-preserved section hierarchy for one canonical document."""

    structural_path: str
    heading: str = ""
    ordinal: int = 0
    parent_path: str | None = None
    coordinates: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalBlockInput:
    """A bounded text unit which later indexes may reference or regroup."""

    structural_path: str
    block_type: str
    ordinal: int
    text_content: str
    section_path: str | None = None
    coordinates: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalDocumentInput:
    """Structured canonical content derived deterministically from one snapshot."""

    canonical_locator: str
    title: str
    mime_type: str
    language: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    sections: Sequence[CanonicalSectionInput] = ()
    blocks: Sequence[CanonicalBlockInput] = ()


class KnowledgeFabricContentRepository:
    """Persist immutable provenance records and restart-safe job/checkpoint state."""

    def __init__(
        self,
        database: Database,
        *,
        object_storage: KnowledgeObjectStorage | None = None,
    ) -> None:
        self.database = database
        self.object_storage = object_storage

    def get_source(self, source_id: str) -> KnowledgeSourceRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeSourceRecord, source_id)

    def get_source_version(self, source_version_id: str) -> KnowledgeSourceVersionRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeSourceVersionRecord, source_version_id)

    def get_source_version_by_key(
        self,
        *,
        source_id: str,
        version_key: str,
    ) -> KnowledgeSourceVersionRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(KnowledgeSourceVersionRecord).where(
                    KnowledgeSourceVersionRecord.source_id == source_id,
                    KnowledgeSourceVersionRecord.version_key == version_key,
                )
            )

    def list_source_versions(self, source_id: str) -> list[KnowledgeSourceVersionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeSourceVersionRecord)
                    .where(KnowledgeSourceVersionRecord.source_id == source_id)
                    .order_by(
                        KnowledgeSourceVersionRecord.observed_at,
                        KnowledgeSourceVersionRecord.id,
                    )
                )
            )

    def get_or_create_ingestion_job(
        self,
        *,
        source_id: str,
        job_type: str,
        idempotency_key: str,
    ) -> KnowledgeIngestionJobRecord:
        self._require_identifier("job_type", job_type)
        self._require_identifier("idempotency_key", idempotency_key)
        with self.database.session() as session:
            existing = session.scalar(
                select(KnowledgeIngestionJobRecord).where(
                    KnowledgeIngestionJobRecord.source_id == source_id,
                    KnowledgeIngestionJobRecord.job_type == job_type,
                    KnowledgeIngestionJobRecord.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return existing
            source = session.get(KnowledgeSourceRecord, source_id)
            if source is None:
                raise KeyError("source")
            record = KnowledgeIngestionJobRecord(
                id=str(uuid4()),
                corpus_id=source.corpus_id,
                source_id=source.id,
                job_type=job_type,
                idempotency_key=idempotency_key,
                status=JOB_QUEUED,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(KnowledgeIngestionJobRecord).where(
                        KnowledgeIngestionJobRecord.source_id == source_id,
                        KnowledgeIngestionJobRecord.job_type == job_type,
                        KnowledgeIngestionJobRecord.idempotency_key == idempotency_key,
                    )
                )
                if existing is None:
                    raise
                return existing
            session.refresh(record)
            return record

    def get_ingestion_job(self, job_id: str) -> KnowledgeIngestionJobRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeIngestionJobRecord, job_id)

    def claim_ingestion_job(self, job_id: str) -> KnowledgeIngestionJobRecord:
        """Atomically enter a new attempt or return a completed idempotent job."""

        with self.database.session() as session:
            record = self._require_job(session, job_id)
            if record.status == JOB_COMPLETED:
                return record
            if not may_claim_ingestion_job(record.status):
                raise KnowledgeIngestionAlreadyRunning("Knowledge ingestion is already running.")
            record.status = JOB_RUNNING
            record.attempt_count += 1
            record.current_stage = "acquiring"
            record.error_code = None
            record.started_at = datetime.now(UTC)
            self._upsert_checkpoint(
                session,
                job_id=record.id,
                stage="acquiring",
                status=JOB_RUNNING,
                metadata={"attempt": record.attempt_count},
            )
            session.commit()
            session.refresh(record)
            return record

    def requeue_interrupted_ingestion_jobs(self) -> int:
        """Make persisted running jobs eligible for a controlled process-restart retry."""

        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(KnowledgeIngestionJobRecord).where(
                        KnowledgeIngestionJobRecord.status == JOB_RUNNING
                    )
                )
            )
            requeued = 0
            for record in records:
                if not may_requeue_ingestion_job(record.status):
                    continue
                record.status = JOB_QUEUED
                record.current_stage = "recovered"
                self._upsert_checkpoint(
                    session,
                    job_id=record.id,
                    stage="recovered",
                    status=JOB_QUEUED,
                    metadata={"attempt": record.attempt_count},
                )
                requeued += 1
            session.commit()
            return requeued

    def complete_existing_version_job(
        self,
        *,
        job_id: str,
        source_version_id: str,
    ) -> KnowledgeSourceVersionRecord:
        """Finish a duplicate delivery without mutating its immutable version."""

        with self.database.session() as session:
            record = self._require_job(session, job_id)
            version = session.get(KnowledgeSourceVersionRecord, source_version_id)
            if version is None:
                raise KeyError("source_version")
            self._complete_job(
                session,
                record=record,
                source_version_id=version.id,
                stage="deduplicated",
            )
            session.commit()
            session.refresh(version)
            return version

    def fail_ingestion_job(self, *, job_id: str, error_code: str) -> None:
        """Persist only a bounded failure code, never provider detail or source content."""

        self._require_identifier("error_code", error_code)
        with self.database.session() as session:
            record = self._require_job(session, job_id)
            if record.status == JOB_COMPLETED:
                return
            record.status = JOB_FAILED
            record.error_code = error_code
            record.current_stage = "failed"
            record.completed_at = datetime.now(UTC)
            self._upsert_checkpoint(
                session,
                job_id=record.id,
                stage="failed",
                status=JOB_FAILED,
                metadata={"error_code": error_code},
            )
            session.commit()

    def list_ingestion_checkpoints(self, job_id: str) -> list[KnowledgeIngestionCheckpointRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeIngestionCheckpointRecord)
                    .where(KnowledgeIngestionCheckpointRecord.job_id == job_id)
                    .order_by(KnowledgeIngestionCheckpointRecord.created_at)
                )
            )

    def publish_source_snapshot(
        self,
        *,
        job_id: str,
        source_id: str,
        version_key: str,
        source_hash: str,
        artifact: StoredKnowledgeObject,
        published_at: datetime | None,
        metadata: Mapping[str, object],
        documents: Sequence[CanonicalDocumentInput],
    ) -> KnowledgeSourceVersionRecord:
        """Atomically publish immutable metadata after private artifact upload succeeds."""

        self._require_identifier("version_key", version_key)
        with self.database.session() as session:
            job = self._require_job(session, job_id)
            source = session.get(KnowledgeSourceRecord, source_id)
            if source is None or job.source_id != source_id:
                raise KeyError("source")
            if job.status != JOB_RUNNING:
                raise KnowledgeIngestionAlreadyRunning("Knowledge ingestion is not claimed.")
            existing_version = session.scalar(
                select(KnowledgeSourceVersionRecord).where(
                    KnowledgeSourceVersionRecord.source_id == source_id,
                    KnowledgeSourceVersionRecord.version_key == version_key,
                )
            )
            if existing_version is not None:
                if source_version_hash_matches(
                    existing_hash=existing_version.source_hash,
                    incoming_hash=source_hash,
                ):
                    self._complete_job(
                        session,
                        record=job,
                        source_version_id=existing_version.id,
                        stage="deduplicated",
                    )
                    session.commit()
                    session.refresh(existing_version)
                    return existing_version
                raise KnowledgeSourceVersionConflict(
                    "Knowledge source version key already refers to different content."
                )
            if artifact.content_sha256 != source_hash:
                raise KnowledgeSourceVersionConflict(
                    "Knowledge artifact hash does not match source content."
                )

            artifact_record = session.scalar(
                select(KnowledgeObjectArtifactRecord).where(
                    KnowledgeObjectArtifactRecord.storage_provider == artifact.provider,
                    KnowledgeObjectArtifactRecord.bucket == artifact.bucket,
                    KnowledgeObjectArtifactRecord.object_key == artifact.object_key,
                )
            )
            if artifact_record is None:
                artifact_record = KnowledgeObjectArtifactRecord(
                    id=str(uuid4()),
                    corpus_id=source.corpus_id,
                    source_id=source.id,
                    storage_provider=artifact.provider,
                    bucket=artifact.bucket,
                    object_key=artifact.object_key,
                    content_sha256=artifact.content_sha256,
                    byte_size=artifact.byte_size,
                    content_type=artifact.content_type,
                )
                session.add(artifact_record)
                session.flush()
            elif (
                artifact_record.content_sha256 != artifact.content_sha256
                or artifact_record.byte_size != artifact.byte_size
                or artifact_record.content_type != artifact.content_type
            ):
                raise KnowledgeSourceVersionConflict(
                    "Knowledge artifact metadata conflicts with storage."
                )

            version = KnowledgeSourceVersionRecord(
                id=str(uuid4()),
                source_id=source.id,
                version_key=version_key,
                observed_at=datetime.now(UTC),
                published_at=published_at,
                source_hash=source_hash,
                artifact_id=artifact_record.id,
                metadata_json=_encode(metadata),
            )
            session.add(version)
            session.flush()
            for document_input in documents:
                self._create_document_content(session, version=version, value=document_input)
            for dependency_type in ("indexes", "projections"):
                session.add(
                    KnowledgeDependencyInvalidationRecord(
                        id=str(uuid4()),
                        source_version_id=version.id,
                        dependency_type=dependency_type,
                        metadata_json=_encode({"source_id": source.id}),
                    )
                )
            self._complete_job(session, record=job, source_version_id=version.id, stage="published")
            session.commit()
            session.refresh(version)
            return version

    def get_artifact(self, artifact_id: str) -> KnowledgeObjectArtifactRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeObjectArtifactRecord, artifact_id)

    def list_evidence_units(self, source_version_id: str) -> list[KnowledgeEvidenceUnitRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeEvidenceUnitRecord)
                    .where(KnowledgeEvidenceUnitRecord.source_version_id == source_version_id)
                    .order_by(KnowledgeEvidenceUnitRecord.evidence_locator)
                )
            )

    def list_canonical_documents(
        self,
        source_version_id: str,
    ) -> list[KnowledgeCanonicalDocumentRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCanonicalDocumentRecord)
                    .where(KnowledgeCanonicalDocumentRecord.source_version_id == source_version_id)
                    .order_by(
                        KnowledgeCanonicalDocumentRecord.canonical_locator,
                        KnowledgeCanonicalDocumentRecord.id,
                    )
                )
            )

    def list_canonical_blocks(
        self,
        document_id: str,
    ) -> list[KnowledgeCanonicalBlockRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCanonicalBlockRecord)
                    .where(KnowledgeCanonicalBlockRecord.document_id == document_id)
                    .order_by(
                        KnowledgeCanonicalBlockRecord.ordinal,
                        KnowledgeCanonicalBlockRecord.structural_path,
                    )
                )
            )

    def create_asset_reference(
        self,
        *,
        document_id: str,
        artifact_id: str,
        asset_type: str,
        structural_path: str,
        block_id: str | None = None,
        coordinates: Mapping[str, object] | None = None,
    ) -> KnowledgeAssetReferenceRecord:
        """Attach an already-private source artifact to one canonical document coordinate."""

        self._require_identifier("asset_type", asset_type)
        self._require_identifier("asset structural_path", structural_path)
        with self.database.session() as session:
            document = session.get(KnowledgeCanonicalDocumentRecord, document_id)
            artifact = session.get(KnowledgeObjectArtifactRecord, artifact_id)
            if document is None or artifact is None:
                raise KeyError("canonical_asset")
            version = session.get(KnowledgeSourceVersionRecord, document.source_version_id)
            if version is None or artifact.source_id != version.source_id:
                raise ValueError("Knowledge asset must belong to the document source.")
            if block_id is not None:
                block = session.get(KnowledgeCanonicalBlockRecord, block_id)
                if block is None or block.document_id != document.id:
                    raise ValueError("Knowledge asset block must belong to the document.")
            record = KnowledgeAssetReferenceRecord(
                id=str(uuid4()),
                document_id=document.id,
                block_id=block_id,
                artifact_id=artifact.id,
                asset_type=asset_type,
                structural_path=structural_path,
                coordinates_json=_encode(coordinates or {}),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_asset_references(self, document_id: str) -> list[KnowledgeAssetReferenceRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeAssetReferenceRecord)
                    .where(KnowledgeAssetReferenceRecord.document_id == document_id)
                    .order_by(KnowledgeAssetReferenceRecord.structural_path)
                )
            )

    def list_pending_invalidations(
        self,
        source_version_id: str,
    ) -> list[KnowledgeDependencyInvalidationRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeDependencyInvalidationRecord)
                    .where(
                        KnowledgeDependencyInvalidationRecord.source_version_id
                        == source_version_id,
                        KnowledgeDependencyInvalidationRecord.status == "pending",
                    )
                    .order_by(KnowledgeDependencyInvalidationRecord.dependency_type)
                )
            )

    def delete_content_for_corpora(self, corpus_ids: Sequence[str]) -> dict[str, int]:
        """Delete derived descendants only after private artifact deletion succeeds."""

        if not corpus_ids:
            return self.empty_content_counts()
        with self.database.session() as session:
            source_ids = list(
                session.scalars(
                    select(KnowledgeSourceRecord.id).where(
                        KnowledgeSourceRecord.corpus_id.in_(corpus_ids)
                    )
                )
            )
            artifacts = list(
                session.scalars(
                    select(KnowledgeObjectArtifactRecord).where(
                        KnowledgeObjectArtifactRecord.corpus_id.in_(corpus_ids)
                    )
                )
            )
            if artifacts and self.object_storage is None:
                raise ObjectStorageUnavailable(
                    "Knowledge object storage is unavailable for lifecycle cleanup."
                )
            if self.object_storage is not None:
                for artifact in artifacts:
                    self.object_storage.delete_private(object_key=artifact.object_key)

            version_ids = list(
                session.scalars(
                    select(KnowledgeSourceVersionRecord.id).where(
                        KnowledgeSourceVersionRecord.source_id.in_(source_ids)
                    )
                )
                if source_ids
                else []
            )
            document_ids = list(
                session.scalars(
                    select(KnowledgeCanonicalDocumentRecord.id).where(
                        KnowledgeCanonicalDocumentRecord.source_version_id.in_(version_ids)
                    )
                )
                if version_ids
                else []
            )
            section_ids = list(
                session.scalars(
                    select(KnowledgeCanonicalSectionRecord.id).where(
                        KnowledgeCanonicalSectionRecord.document_id.in_(document_ids)
                    )
                )
                if document_ids
                else []
            )
            block_ids = list(
                session.scalars(
                    select(KnowledgeCanonicalBlockRecord.id).where(
                        KnowledgeCanonicalBlockRecord.document_id.in_(document_ids)
                    )
                )
                if document_ids
                else []
            )
            job_ids = list(
                session.scalars(
                    select(KnowledgeIngestionJobRecord.id).where(
                        KnowledgeIngestionJobRecord.source_id.in_(source_ids)
                    )
                )
                if source_ids
                else []
            )
            counts = self.empty_content_counts()
            counts["knowledge_fabric_ingestion_checkpoints"] = self._delete_ids(
                session,
                KnowledgeIngestionCheckpointRecord,
                KnowledgeIngestionCheckpointRecord.job_id,
                job_ids,
            )
            counts["knowledge_fabric_ingestion_jobs"] = self._delete_ids(
                session, KnowledgeIngestionJobRecord, KnowledgeIngestionJobRecord.id, job_ids
            )
            counts["knowledge_fabric_dependency_invalidations"] = self._delete_ids(
                session,
                KnowledgeDependencyInvalidationRecord,
                KnowledgeDependencyInvalidationRecord.source_version_id,
                version_ids,
            )
            counts["knowledge_fabric_evidence_units"] = self._delete_ids(
                session,
                KnowledgeEvidenceUnitRecord,
                KnowledgeEvidenceUnitRecord.source_version_id,
                version_ids,
            )
            counts["knowledge_fabric_asset_references"] = self._delete_ids(
                session,
                KnowledgeAssetReferenceRecord,
                KnowledgeAssetReferenceRecord.document_id,
                document_ids,
            )
            counts["knowledge_fabric_canonical_blocks"] = self._delete_ids(
                session,
                KnowledgeCanonicalBlockRecord,
                KnowledgeCanonicalBlockRecord.id,
                block_ids,
            )
            counts["knowledge_fabric_canonical_sections"] = self._delete_ids(
                session,
                KnowledgeCanonicalSectionRecord,
                KnowledgeCanonicalSectionRecord.id,
                section_ids,
            )
            counts["knowledge_fabric_canonical_documents"] = self._delete_ids(
                session,
                KnowledgeCanonicalDocumentRecord,
                KnowledgeCanonicalDocumentRecord.id,
                document_ids,
            )
            counts["knowledge_fabric_source_versions"] = self._delete_ids(
                session,
                KnowledgeSourceVersionRecord,
                KnowledgeSourceVersionRecord.id,
                version_ids,
            )
            artifact_ids = [artifact.id for artifact in artifacts]
            counts["knowledge_fabric_object_artifacts"] = self._delete_ids(
                session,
                KnowledgeObjectArtifactRecord,
                KnowledgeObjectArtifactRecord.id,
                artifact_ids,
            )
            session.commit()
            return counts

    @staticmethod
    def empty_content_counts() -> dict[str, int]:
        return {
            "knowledge_fabric_source_versions": 0,
            "knowledge_fabric_canonical_documents": 0,
            "knowledge_fabric_canonical_sections": 0,
            "knowledge_fabric_canonical_blocks": 0,
            "knowledge_fabric_asset_references": 0,
            "knowledge_fabric_evidence_units": 0,
            "knowledge_fabric_object_artifacts": 0,
            "knowledge_fabric_ingestion_jobs": 0,
            "knowledge_fabric_ingestion_checkpoints": 0,
            "knowledge_fabric_dependency_invalidations": 0,
        }

    def _create_document_content(
        self,
        session: Session,
        *,
        version: KnowledgeSourceVersionRecord,
        value: CanonicalDocumentInput,
    ) -> None:
        self._require_identifier("canonical_locator", value.canonical_locator)
        self._require_identifier("mime_type", value.mime_type)
        document = KnowledgeCanonicalDocumentRecord(
            id=str(uuid4()),
            source_version_id=version.id,
            canonical_locator=value.canonical_locator,
            title=value.title,
            language=value.language,
            mime_type=value.mime_type,
            metadata_json=_encode(value.metadata),
        )
        session.add(document)
        session.flush()
        section_ids: dict[str, str] = {}
        for section in value.sections:
            self._require_identifier("section structural_path", section.structural_path)
            parent_id = None
            if section.parent_path is not None:
                parent_id = section_ids.get(section.parent_path)
                if parent_id is None:
                    raise ValueError("Knowledge section parent must precede its child.")
            section_record = KnowledgeCanonicalSectionRecord(
                id=str(uuid4()),
                document_id=document.id,
                parent_section_id=parent_id,
                structural_path=section.structural_path,
                heading=section.heading,
                ordinal=section.ordinal,
                coordinates_json=_encode(section.coordinates),
            )
            session.add(section_record)
            section_ids[section.structural_path] = section_record.id
        session.flush()
        for block in value.blocks:
            self._require_identifier("block structural_path", block.structural_path)
            self._require_identifier("block_type", block.block_type)
            section_id = None
            if block.section_path is not None:
                section_id = section_ids.get(block.section_path)
                if section_id is None:
                    raise ValueError("Knowledge block section must exist in its document.")
            content_hash = sha256(block.text_content.encode("utf-8")).hexdigest()
            block_record = KnowledgeCanonicalBlockRecord(
                id=str(uuid4()),
                document_id=document.id,
                section_id=section_id,
                structural_path=block.structural_path,
                block_type=block.block_type,
                ordinal=block.ordinal,
                text_content=block.text_content,
                content_sha256=content_hash,
                coordinates_json=_encode(block.coordinates),
            )
            session.add(block_record)
            session.flush()
            session.add(
                KnowledgeEvidenceUnitRecord(
                    id=str(uuid4()),
                    source_version_id=version.id,
                    document_id=document.id,
                    block_id=block_record.id,
                    evidence_locator=f"{document.canonical_locator}#{block.structural_path}",
                    evidence_type=block.block_type,
                    content_sha256=content_hash,
                    text_content=block.text_content,
                    coordinates_json=_encode(block.coordinates),
                )
            )

    @staticmethod
    def _delete_ids(session: Session, model: Any, column: Any, values: Sequence[str]) -> int:
        if not values:
            return 0
        result = session.execute(delete(model).where(column.in_(values)))
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    def _require_identifier(field_name: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"{field_name} is required.")

    @staticmethod
    def _require_job(session: Session, job_id: str) -> KnowledgeIngestionJobRecord:
        record = session.get(KnowledgeIngestionJobRecord, job_id)
        if record is None:
            raise KeyError("ingestion_job")
        return record

    @staticmethod
    def _upsert_checkpoint(
        session: Session,
        *,
        job_id: str,
        stage: str,
        status: str,
        metadata: Mapping[str, object],
    ) -> None:
        existing = session.scalar(
            select(KnowledgeIngestionCheckpointRecord).where(
                KnowledgeIngestionCheckpointRecord.job_id == job_id,
                KnowledgeIngestionCheckpointRecord.stage == stage,
            )
        )
        if existing is None:
            session.add(
                KnowledgeIngestionCheckpointRecord(
                    id=str(uuid4()),
                    job_id=job_id,
                    stage=stage,
                    status=status,
                    metadata_json=_encode(metadata),
                )
            )
            return
        existing.status = status
        existing.metadata_json = _encode(metadata)

    def _complete_job(
        self,
        session: Session,
        *,
        record: KnowledgeIngestionJobRecord,
        source_version_id: str,
        stage: str,
    ) -> None:
        record.status = JOB_COMPLETED
        record.source_version_id = source_version_id
        record.current_stage = stage
        record.error_code = None
        record.completed_at = datetime.now(UTC)
        self._upsert_checkpoint(
            session,
            job_id=record.id,
            stage=stage,
            status=JOB_COMPLETED,
            metadata={"source_version_id": source_version_id},
        )


def _encode(value: Mapping[str, object]) -> str:
    """Persist structured metadata, never arbitrary reprs that can leak object values."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


__all__ = [
    "CanonicalBlockInput",
    "CanonicalDocumentInput",
    "CanonicalSectionInput",
    "KnowledgeFabricContentRepository",
    "KnowledgeIngestionAlreadyRunning",
    "KnowledgeSourceVersionConflict",
]
