"""Deterministic snapshot ingestion orchestration outside the Character reply path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Literal

from echo_masque.knowledge_fabric_ingestion_policy import deterministic_artifact_key
from echo_masque.knowledge_object_storage import (
    KnowledgeObjectStorage,
    ObjectStorageError,
    StoredKnowledgeObject,
)
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalDocumentInput,
    KnowledgeExternalScheduleClaimLost,
    KnowledgeFabricContentRepository,
    KnowledgeIngestionAlreadyRunning,
    KnowledgeSourceVersionConflict,
    PublishedKnowledgeAssetInput,
)
from echo_masque.persistence.knowledge_fabric_models import KnowledgeSourceVersionRecord


@dataclass(frozen=True, slots=True)
class SourceSnapshotAssetInput:
    """An adapter-provided binary child asset for one canonical document.

    Bytes are accepted only at the ingestion boundary and are published to private object
    storage before the asset/document/Evidence records are atomically linked.
    """

    document_locator: str
    structural_path: str
    asset_type: str
    artifact_content: bytes
    artifact_content_type: str
    evidence_locator: str
    evidence_type: str = "asset"
    text_content: str = ""
    block_structural_path: str | None = None
    coordinates: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceSnapshotIngestionRequest:
    """One adapter-produced snapshot; no LLM output is required or accepted here."""

    source_id: str
    version_key: str
    idempotency_key: str
    artifact_content: bytes
    artifact_content_type: str
    documents: Sequence[CanonicalDocumentInput] = ()
    assets: Sequence[SourceSnapshotAssetInput] = ()
    published_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    activate_git_version: bool = False
    external_schedule_lease_token: str | None = None
    current_entry_mode: Literal["automatic", "full", "delta"] = "automatic"
    removed_entry_locators: Sequence[str] = ()


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
                return self.repository.activate_source_version_as_current(
                    source_id=request.source_id,
                    source_version_id=version.id,
                )
        try:
            claimed = self.repository.claim_ingestion_job(job.id)
        except KnowledgeIngestionAlreadyRunning:
            raise
        if claimed.source_version_id is not None:
            version = self.repository.get_source_version(claimed.source_version_id)
            if version is not None:
                return self.repository.activate_source_version_as_current(
                    source_id=request.source_id,
                    source_version_id=version.id,
                )

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
        uploaded_artifacts: list[StoredKnowledgeObject] = []
        registered_artifact_keys: set[str] = set()
        try:
            artifact = self.object_storage.put_private(
                object_key=object_key,
                content=request.artifact_content,
                content_type=request.artifact_content_type,
                metadata={"source-id": request.source_id},
            )
            uploaded_artifacts.append(artifact)
            self.repository.register_uploaded_artifact(
                source_id=request.source_id,
                artifact=artifact,
            )
            registered_artifact_keys.add(artifact.object_key)
            published_assets: list[PublishedKnowledgeAssetInput] = []
            for asset_input in request.assets:
                asset_hash = sha256(asset_input.artifact_content).hexdigest()
                asset_key = deterministic_artifact_key(
                    prefix=f"{self.object_key_prefix}/assets",
                    source_id=request.source_id,
                    content_sha256=asset_hash,
                )
                stored_asset = self.object_storage.put_private(
                    object_key=asset_key,
                    content=asset_input.artifact_content,
                    content_type=asset_input.artifact_content_type,
                    metadata={
                        "source-id": request.source_id,
                        "asset-type": asset_input.asset_type,
                    },
                )
                uploaded_artifacts.append(stored_asset)
                self.repository.register_uploaded_artifact(
                    source_id=request.source_id,
                    artifact=stored_asset,
                )
                registered_artifact_keys.add(stored_asset.object_key)
                published_assets.append(
                    PublishedKnowledgeAssetInput(
                        document_locator=asset_input.document_locator,
                        structural_path=asset_input.structural_path,
                        asset_type=asset_input.asset_type,
                        artifact=stored_asset,
                        evidence_locator=asset_input.evidence_locator,
                        evidence_type=asset_input.evidence_type,
                        text_content=asset_input.text_content,
                        block_structural_path=asset_input.block_structural_path,
                        coordinates=asset_input.coordinates,
                    )
                )
        except ObjectStorageError:
            self._discard_failed_uploads(
                uploaded_artifacts,
                registered_artifact_keys,
            )
            self.repository.fail_ingestion_job(
                job_id=claimed.id,
                error_code="object_storage_failed",
            )
            raise
        except Exception:
            self._discard_failed_uploads(
                uploaded_artifacts,
                registered_artifact_keys,
            )
            self.repository.fail_ingestion_job(
                job_id=claimed.id,
                error_code="persistence_failed",
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
                assets=published_assets,
                activate_git_version=request.activate_git_version,
                external_schedule_lease_token=request.external_schedule_lease_token,
                current_entry_mode=request.current_entry_mode,
                removed_entry_locators=request.removed_entry_locators,
            )
        except KnowledgeExternalScheduleClaimLost:
            self._discard_failed_uploads(
                uploaded_artifacts,
                registered_artifact_keys,
            )
            self.repository.fail_ingestion_job(
                job_id=claimed.id,
                error_code="schedule_claim_lost",
            )
            raise
        except Exception:
            self._discard_failed_uploads(
                uploaded_artifacts,
                registered_artifact_keys,
            )
            self.repository.fail_ingestion_job(
                job_id=claimed.id,
                error_code="persistence_failed",
            )
            raise

    def _discard_failed_uploads(
        self,
        artifacts: Sequence[StoredKnowledgeObject],
        registered_artifact_keys: set[str],
    ) -> None:
        """Compensate every child upload without deleting an already-published object."""

        for artifact in reversed(artifacts):
            if artifact.object_key in registered_artifact_keys:
                self.repository.discard_unpublished_artifact(artifact)
                continue
            with suppress(ObjectStorageError):
                self.object_storage.delete_private(object_key=artifact.object_key)

    def recover_interrupted_jobs(self) -> int:
        """Call on a worker restart before accepting another snapshot delivery."""

        self.repository.process_pending_object_deletions()
        return self.repository.requeue_interrupted_ingestion_jobs()


__all__ = [
    "KnowledgeFabricIngestionService",
    "SourceSnapshotAssetInput",
    "SourceSnapshotIngestionRequest",
]
