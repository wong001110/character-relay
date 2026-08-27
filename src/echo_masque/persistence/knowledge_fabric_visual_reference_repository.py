"""Corpus-bound visual-reference provenance; no runtime/server identity authority."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select

from echo_masque.knowledge_fabric_visual_reference_policy import (
    external_comparison_is_authorizable,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeAssetReferenceRecord,
    KnowledgeCanonicalEntityRecord,
    KnowledgeCanonicalVisualReferenceRecord,
    KnowledgeEvidenceUnitRecord,
    KnowledgeObjectArtifactRecord,
    KnowledgeSourceRecord,
    KnowledgeSourceVersionRecord,
)

VISUAL_REFERENCE_ACTIVE = "active"
VISUAL_REFERENCE_REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class VisualReferenceCandidate:
    corpus_id: str
    canonical_entity_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class VisualReferenceComparisonCandidate:
    """Private-only input for explicitly authorized fictional-character comparison."""

    corpus_id: str
    canonical_entity_id: str
    canonical_name: str
    artifact_sha256: str
    object_key: str
    content_type: str


class KnowledgeFabricVisualReferenceRepository:
    """Bind approved image assets to canonical entities inside one corpus only."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        corpus_id: str,
        canonical_entity_id: str,
        evidence_unit_id: str,
        asset_id: str,
        descriptor: Mapping[str, object] | None = None,
        comparison_authorized: bool = False,
    ) -> KnowledgeCanonicalVisualReferenceRecord:
        with self.database.session() as session:
            entity = session.get(KnowledgeCanonicalEntityRecord, canonical_entity_id)
            evidence = session.get(KnowledgeEvidenceUnitRecord, evidence_unit_id)
            asset = session.get(KnowledgeAssetReferenceRecord, asset_id)
            if entity is None or evidence is None or asset is None:
                raise KeyError("knowledge_visual_reference_provenance")
            if entity.corpus_id != corpus_id:
                raise ValueError("Canonical entity is outside the visual-reference corpus.")
            if comparison_authorized and not external_comparison_is_authorizable(
                entity_type=entity.entity_type
            ):
                raise ValueError(
                    "External visual comparison is limited to fictional_character entities."
                )
            version = session.get(KnowledgeSourceVersionRecord, evidence.source_version_id)
            artifact = session.get(KnowledgeObjectArtifactRecord, asset.artifact_id)
            if version is None or artifact is None or asset.document_id != evidence.document_id:
                raise ValueError("Visual reference provenance is inconsistent.")
            source = session.get(KnowledgeSourceRecord, version.source_id)
            if source is None or source.corpus_id != corpus_id or artifact.source_id != source.id:
                raise ValueError("Visual reference provenance is outside the corpus.")
            existing = session.scalar(
                select(KnowledgeCanonicalVisualReferenceRecord).where(
                    KnowledgeCanonicalVisualReferenceRecord.canonical_entity_id
                    == canonical_entity_id,
                    KnowledgeCanonicalVisualReferenceRecord.evidence_unit_id == evidence_unit_id,
                    KnowledgeCanonicalVisualReferenceRecord.asset_id == asset_id,
                )
            )
            if existing is not None:
                return existing
            stored_descriptor = dict(descriptor or {})
            if comparison_authorized:
                stored_descriptor["comparison_authorized"] = True
            record = KnowledgeCanonicalVisualReferenceRecord(
                id=str(uuid4()),
                corpus_id=corpus_id,
                canonical_entity_id=canonical_entity_id,
                evidence_unit_id=evidence_unit_id,
                asset_id=asset_id,
                descriptor_json=json.dumps(stored_descriptor, ensure_ascii=False, sort_keys=True),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def revoke(self, reference_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(KnowledgeCanonicalVisualReferenceRecord, reference_id)
            if record is None or record.status == VISUAL_REFERENCE_REVOKED:
                return False
            record.status = VISUAL_REFERENCE_REVOKED
            session.commit()
            return True

    def list_active(self, corpus_id: str) -> list[KnowledgeCanonicalVisualReferenceRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCanonicalVisualReferenceRecord)
                    .where(
                        KnowledgeCanonicalVisualReferenceRecord.corpus_id == corpus_id,
                        KnowledgeCanonicalVisualReferenceRecord.status == VISUAL_REFERENCE_ACTIVE,
                    )
                    .order_by(KnowledgeCanonicalVisualReferenceRecord.id)
                )
            )

    def list_active_candidates(self, corpus_id: str) -> list[VisualReferenceCandidate]:
        with self.database.session() as session:
            rows = session.execute(
                select(
                    KnowledgeCanonicalVisualReferenceRecord,
                    KnowledgeCanonicalEntityRecord,
                    KnowledgeObjectArtifactRecord,
                )
                .join(
                    KnowledgeCanonicalEntityRecord,
                    KnowledgeCanonicalEntityRecord.id
                    == KnowledgeCanonicalVisualReferenceRecord.canonical_entity_id,
                )
                .join(
                    KnowledgeAssetReferenceRecord,
                    KnowledgeAssetReferenceRecord.id
                    == KnowledgeCanonicalVisualReferenceRecord.asset_id,
                )
                .join(
                    KnowledgeObjectArtifactRecord,
                    KnowledgeObjectArtifactRecord.id == KnowledgeAssetReferenceRecord.artifact_id,
                )
                .where(
                    KnowledgeCanonicalVisualReferenceRecord.corpus_id == corpus_id,
                    KnowledgeCanonicalVisualReferenceRecord.status == VISUAL_REFERENCE_ACTIVE,
                )
                .order_by(KnowledgeCanonicalVisualReferenceRecord.id)
            ).tuples()
            return [
                VisualReferenceCandidate(
                    corpus_id=reference.corpus_id,
                    canonical_entity_id=entity.id,
                    canonical_name=entity.canonical_name,
                    aliases=tuple(json.loads(entity.aliases_json)),
                    artifact_sha256=artifact.content_sha256,
                )
                for reference, entity, artifact in rows
            ]

    def list_active_comparison_candidates(
        self,
        corpus_id: str,
    ) -> list[VisualReferenceComparisonCandidate]:
        """Keep private object coordinates inside the Runtime-only comparison boundary."""

        with self.database.session() as session:
            rows = session.execute(
                select(
                    KnowledgeCanonicalVisualReferenceRecord,
                    KnowledgeCanonicalEntityRecord,
                    KnowledgeObjectArtifactRecord,
                )
                .join(
                    KnowledgeCanonicalEntityRecord,
                    KnowledgeCanonicalEntityRecord.id
                    == KnowledgeCanonicalVisualReferenceRecord.canonical_entity_id,
                )
                .join(
                    KnowledgeAssetReferenceRecord,
                    KnowledgeAssetReferenceRecord.id
                    == KnowledgeCanonicalVisualReferenceRecord.asset_id,
                )
                .join(
                    KnowledgeObjectArtifactRecord,
                    KnowledgeObjectArtifactRecord.id == KnowledgeAssetReferenceRecord.artifact_id,
                )
                .where(
                    KnowledgeCanonicalVisualReferenceRecord.corpus_id == corpus_id,
                    KnowledgeCanonicalVisualReferenceRecord.status == VISUAL_REFERENCE_ACTIVE,
                    KnowledgeCanonicalEntityRecord.entity_type == "fictional_character",
                )
                .order_by(KnowledgeCanonicalVisualReferenceRecord.id)
            ).tuples().all()
        values: list[VisualReferenceComparisonCandidate] = []
        for reference, entity, artifact in rows:
            try:
                descriptor = json.loads(reference.descriptor_json)
            except json.JSONDecodeError:
                continue
            if (
                not isinstance(descriptor, dict)
                or descriptor.get("comparison_authorized") is not True
            ):
                continue
            values.append(
                VisualReferenceComparisonCandidate(
                    corpus_id=reference.corpus_id,
                    canonical_entity_id=entity.id,
                    canonical_name=entity.canonical_name,
                    artifact_sha256=artifact.content_sha256,
                    object_key=artifact.object_key,
                    content_type=artifact.content_type,
                )
            )
        return values


__all__ = [
    "VISUAL_REFERENCE_ACTIVE",
    "VISUAL_REFERENCE_REVOKED",
    "KnowledgeFabricVisualReferenceRepository",
    "VisualReferenceCandidate",
    "VisualReferenceComparisonCandidate",
]
