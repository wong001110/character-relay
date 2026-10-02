"""Corpus-bound Knowledge Fabric entities, interpretations, and graph provenance."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from echo_masque.knowledge_fabric_interpretation_policy import (
    interpretation_status_is_valid,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCanonicalEntityRecord,
    KnowledgeCorpusRecord,
    KnowledgeEvidenceGraphRelationRecord,
    KnowledgeEvidenceUnitRecord,
    KnowledgeExtractedAssertionRecord,
    KnowledgeInterpretationEvidenceRecord,
    KnowledgeSourceRecord,
    KnowledgeSourceVersionRecord,
    KnowledgeWorldEventParticipantRecord,
    KnowledgeWorldEventRecord,
)


def normalize_canonical_entity_name(value: str) -> str:
    """Use stable Unicode comparison only inside the explicit corpus boundary."""

    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.split())[:500]


def _encode(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _aliases(values: Sequence[str]) -> str:
    normalized = [" ".join(item.split())[:500] for item in values if item.strip()]
    return json.dumps(list(dict.fromkeys(normalized)), ensure_ascii=False)


class KnowledgeFabricInterpretationRepository:
    """Keep corpus interpretation distinct from server runtime identity and BeliefV3."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_canonical_entity(
        self,
        *,
        corpus_id: str,
        entity_type: str,
        canonical_name: str,
        aliases: Sequence[str] = (),
        status: str = "active",
        metadata: Mapping[str, object] | None = None,
    ) -> KnowledgeCanonicalEntityRecord:
        normalized_name = normalize_canonical_entity_name(canonical_name)
        self._require_identifier("entity_type", entity_type)
        if not normalized_name:
            raise ValueError("Canonical entity name is required.")
        if not interpretation_status_is_valid(status):
            raise ValueError("Unknown Knowledge interpretation status.")
        with self.database.session() as session:
            self._require_corpus(session, corpus_id)
            existing = session.scalar(
                select(KnowledgeCanonicalEntityRecord).where(
                    KnowledgeCanonicalEntityRecord.corpus_id == corpus_id,
                    KnowledgeCanonicalEntityRecord.entity_type == entity_type,
                    KnowledgeCanonicalEntityRecord.normalized_name == normalized_name,
                )
            )
            if existing is not None:
                return existing
            record = KnowledgeCanonicalEntityRecord(
                id=str(uuid4()),
                corpus_id=corpus_id,
                entity_type=entity_type,
                canonical_name=" ".join(canonical_name.split())[:500],
                normalized_name=normalized_name,
                aliases_json=_aliases(aliases),
                status=status,
                metadata_json=_encode(metadata or {}),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_canonical_entities(self, corpus_id: str) -> list[KnowledgeCanonicalEntityRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCanonicalEntityRecord)
                    .where(KnowledgeCanonicalEntityRecord.corpus_id == corpus_id)
                    .order_by(
                        KnowledgeCanonicalEntityRecord.entity_type,
                        KnowledgeCanonicalEntityRecord.canonical_name,
                        KnowledgeCanonicalEntityRecord.id,
                    )
                )
            )

    def create_assertion(
        self,
        *,
        corpus_id: str,
        subject_entity_id: str,
        predicate: str,
        evidence_unit_ids: Sequence[str],
        object_entity_id: str | None = None,
        object_value: str = "",
        qualifiers: Mapping[str, object] | None = None,
        confidence: float = 0.0,
        authority_profile: str = "standard",
        status: str = "active",
        producer: str = "",
        source_model: str = "",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> KnowledgeExtractedAssertionRecord:
        self._require_identifier("predicate", predicate)
        if not interpretation_status_is_valid(status):
            raise ValueError("Unknown Knowledge interpretation status.")
        if bool(object_entity_id) == bool(object_value.strip()):
            raise ValueError("Assertion requires exactly one object entity or object value.")
        with self.database.session() as session:
            self._require_corpus(session, corpus_id)
            self._require_entity_in_corpus(session, subject_entity_id, corpus_id)
            if object_entity_id is not None:
                self._require_entity_in_corpus(session, object_entity_id, corpus_id)
            self._require_evidence_units(session, corpus_id, evidence_unit_ids)
            record = KnowledgeExtractedAssertionRecord(
                id=str(uuid4()),
                corpus_id=corpus_id,
                subject_entity_id=subject_entity_id,
                predicate=predicate,
                object_entity_id=object_entity_id,
                object_value=object_value.strip(),
                qualifiers_json=_encode(qualifiers or {}),
                confidence=confidence,
                authority_profile=authority_profile,
                status=status,
                producer=producer,
                source_model=source_model,
                valid_from=valid_from,
                valid_to=valid_to,
            )
            session.add(record)
            self._attach_evidence(
                session,
                corpus_id=corpus_id,
                interpretation_type="assertion",
                interpretation_id=record.id,
                evidence_unit_ids=evidence_unit_ids,
            )
            session.commit()
            session.refresh(record)
            return record

    def create_world_event(
        self,
        *,
        corpus_id: str,
        event_type: str,
        title: str,
        evidence_unit_ids: Sequence[str],
        participants: Sequence[tuple[str, str]] = (),
        description: str = "",
        location_entity_id: str | None = None,
        ordering_key: str = "",
        outcome: Mapping[str, object] | None = None,
        confidence: float = 0.0,
        authority_profile: str = "standard",
        status: str = "active",
        producer: str = "",
        source_model: str = "",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> KnowledgeWorldEventRecord:
        self._require_identifier("event_type", event_type)
        self._require_identifier("event title", title)
        if not interpretation_status_is_valid(status):
            raise ValueError("Unknown Knowledge interpretation status.")
        with self.database.session() as session:
            self._require_corpus(session, corpus_id)
            self._require_evidence_units(session, corpus_id, evidence_unit_ids)
            if location_entity_id is not None:
                self._require_entity_in_corpus(session, location_entity_id, corpus_id)
            for entity_id, role in participants:
                self._require_entity_in_corpus(session, entity_id, corpus_id)
                self._require_identifier("event participant role", role)
            record = KnowledgeWorldEventRecord(
                id=str(uuid4()),
                corpus_id=corpus_id,
                event_type=event_type,
                title=title,
                description=description,
                location_entity_id=location_entity_id,
                ordering_key=ordering_key,
                outcome_json=_encode(outcome or {}),
                confidence=confidence,
                authority_profile=authority_profile,
                status=status,
                producer=producer,
                source_model=source_model,
                valid_from=valid_from,
                valid_to=valid_to,
            )
            session.add(record)
            # There is no ORM relationship on the intentionally small write model,
            # so flush the parent before creating participant rows with its FK.
            session.flush()
            for entity_id, role in participants:
                session.add(
                    KnowledgeWorldEventParticipantRecord(
                        id=str(uuid4()),
                        event_id=record.id,
                        canonical_entity_id=entity_id,
                        participant_role=role,
                    )
                )
            self._attach_evidence(
                session,
                corpus_id=corpus_id,
                interpretation_type="world_event",
                interpretation_id=record.id,
                evidence_unit_ids=evidence_unit_ids,
            )
            session.commit()
            session.refresh(record)
            return record

    def add_graph_relation(
        self,
        *,
        corpus_id: str,
        source_ref_type: str,
        source_ref_id: str,
        relation_type: str,
        target_ref_type: str,
        target_ref_id: str,
        evidence_unit_ids: Sequence[str],
        confidence: float = 0.0,
        authority_profile: str = "standard",
        status: str = "active",
        producer: str = "",
        source_model: str = "",
    ) -> KnowledgeEvidenceGraphRelationRecord:
        self._require_identifier("graph relation type", relation_type)
        if not interpretation_status_is_valid(status):
            raise ValueError("Unknown Knowledge interpretation status.")
        with self.database.session() as session:
            self._require_corpus(session, corpus_id)
            self._require_graph_node(session, corpus_id, source_ref_type, source_ref_id)
            self._require_graph_node(session, corpus_id, target_ref_type, target_ref_id)
            self._require_evidence_units(session, corpus_id, evidence_unit_ids)
            existing = session.scalar(
                select(KnowledgeEvidenceGraphRelationRecord).where(
                    KnowledgeEvidenceGraphRelationRecord.corpus_id == corpus_id,
                    KnowledgeEvidenceGraphRelationRecord.source_ref_type == source_ref_type,
                    KnowledgeEvidenceGraphRelationRecord.source_ref_id == source_ref_id,
                    KnowledgeEvidenceGraphRelationRecord.relation_type == relation_type,
                    KnowledgeEvidenceGraphRelationRecord.target_ref_type == target_ref_type,
                    KnowledgeEvidenceGraphRelationRecord.target_ref_id == target_ref_id,
                    KnowledgeEvidenceGraphRelationRecord.status == status,
                )
            )
            if existing is not None:
                return existing
            record = KnowledgeEvidenceGraphRelationRecord(
                id=str(uuid4()),
                corpus_id=corpus_id,
                source_ref_type=source_ref_type,
                source_ref_id=source_ref_id,
                relation_type=relation_type,
                target_ref_type=target_ref_type,
                target_ref_id=target_ref_id,
                confidence=confidence,
                authority_profile=authority_profile,
                status=status,
                producer=producer,
                source_model=source_model,
            )
            session.add(record)
            self._attach_evidence(
                session,
                corpus_id=corpus_id,
                interpretation_type="graph_relation",
                interpretation_id=record.id,
                evidence_unit_ids=evidence_unit_ids,
            )
            session.commit()
            session.refresh(record)
            return record

    def list_interpretation_evidence(
        self,
        *,
        interpretation_type: str,
        interpretation_id: str,
    ) -> list[KnowledgeInterpretationEvidenceRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeInterpretationEvidenceRecord)
                    .where(
                        KnowledgeInterpretationEvidenceRecord.interpretation_type
                        == interpretation_type,
                        KnowledgeInterpretationEvidenceRecord.interpretation_id
                        == interpretation_id,
                    )
                    .order_by(KnowledgeInterpretationEvidenceRecord.created_at)
                )
            )

    def delete_interpretations_for_corpora(self, corpus_ids: Sequence[str]) -> dict[str, int]:
        """Remove corpus-owned interpretations while preserving unrelated runtime entities."""

        if not corpus_ids:
            return self.empty_interpretation_counts()
        with self.database.session() as session:
            counts = self.delete_interpretations_for_corpora_in_session(session, corpus_ids)
            session.commit()
            return counts

    def delete_interpretations_for_corpora_in_session(
        self,
        session: Session,
        corpus_ids: Sequence[str],
    ) -> dict[str, int]:
        """Stage corpus interpretation deletion in the caller's lifecycle transaction."""

        if not corpus_ids:
            return self.empty_interpretation_counts()
        event_ids = list(
            session.scalars(
                select(KnowledgeWorldEventRecord.id).where(
                    KnowledgeWorldEventRecord.corpus_id.in_(corpus_ids)
                )
            )
        )
        counts = self.empty_interpretation_counts()
        counts["knowledge_fabric_interpretation_evidence"] = self._delete_corpus_rows(
            session, KnowledgeInterpretationEvidenceRecord, corpus_ids
        )
        counts["knowledge_fabric_evidence_graph_relations"] = self._delete_corpus_rows(
            session, KnowledgeEvidenceGraphRelationRecord, corpus_ids
        )
        if event_ids:
            counts["knowledge_fabric_world_event_participants"] = self._rowcount(
                session.execute(
                    delete(KnowledgeWorldEventParticipantRecord).where(
                        KnowledgeWorldEventParticipantRecord.event_id.in_(event_ids)
                    )
                )
            )
        counts["knowledge_fabric_extracted_assertions"] = self._delete_corpus_rows(
            session, KnowledgeExtractedAssertionRecord, corpus_ids
        )
        counts["knowledge_fabric_world_events"] = self._delete_corpus_rows(
            session, KnowledgeWorldEventRecord, corpus_ids
        )
        counts["knowledge_fabric_canonical_entities"] = self._delete_corpus_rows(
            session, KnowledgeCanonicalEntityRecord, corpus_ids
        )
        return counts

    @staticmethod
    def empty_interpretation_counts() -> dict[str, int]:
        return {
            "knowledge_fabric_canonical_entities": 0,
            "knowledge_fabric_extracted_assertions": 0,
            "knowledge_fabric_world_events": 0,
            "knowledge_fabric_world_event_participants": 0,
            "knowledge_fabric_evidence_graph_relations": 0,
            "knowledge_fabric_interpretation_evidence": 0,
        }

    @staticmethod
    def _rowcount(result: object) -> int:
        value = getattr(result, "rowcount", 0)
        return int(value) if isinstance(value, int) and value > 0 else 0

    @classmethod
    def _delete_corpus_rows(
        cls,
        session: Session,
        model: type[Any],
        corpus_ids: Sequence[str],
    ) -> int:
        return cls._rowcount(session.execute(delete(model).where(model.corpus_id.in_(corpus_ids))))

    @staticmethod
    def _require_identifier(name: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"Knowledge {name} is required.")

    @staticmethod
    def _require_corpus(session: Session, corpus_id: str) -> KnowledgeCorpusRecord:
        corpus = session.get(KnowledgeCorpusRecord, corpus_id)
        if corpus is None:
            raise KeyError("Knowledge corpus not found.")
        return corpus

    @staticmethod
    def _require_canonical_entity(
        session: Session,
        canonical_entity_id: str,
    ) -> KnowledgeCanonicalEntityRecord:
        record = session.get(KnowledgeCanonicalEntityRecord, canonical_entity_id)
        if record is None:
            raise KeyError("Knowledge canonical entity not found.")
        return record

    @classmethod
    def _require_entity_in_corpus(
        cls,
        session: Session,
        canonical_entity_id: str,
        corpus_id: str,
    ) -> KnowledgeCanonicalEntityRecord:
        record = cls._require_canonical_entity(session, canonical_entity_id)
        if record.corpus_id != corpus_id:
            raise ValueError("Knowledge canonical entity is outside the corpus.")
        return record

    @staticmethod
    def _require_evidence_units(
        session: Session,
        corpus_id: str,
        evidence_unit_ids: Sequence[str],
    ) -> None:
        values = tuple(dict.fromkeys(evidence_unit_ids))
        if not values:
            raise ValueError("Knowledge interpretation requires Evidence Units.")
        rows = list(
            session.scalars(
                select(KnowledgeEvidenceUnitRecord)
                .join(
                    KnowledgeSourceVersionRecord,
                    KnowledgeSourceVersionRecord.id
                    == KnowledgeEvidenceUnitRecord.source_version_id,
                )
                .join(
                    KnowledgeSourceRecord,
                    KnowledgeSourceRecord.id == KnowledgeSourceVersionRecord.source_id,
                )
                .where(
                    KnowledgeEvidenceUnitRecord.id.in_(values),
                    KnowledgeSourceRecord.corpus_id == corpus_id,
                )
            )
        )
        if len(rows) != len(values):
            raise ValueError("Knowledge Evidence Unit is outside the corpus.")

    @staticmethod
    def _attach_evidence(
        session: Session,
        *,
        corpus_id: str,
        interpretation_type: str,
        interpretation_id: str,
        evidence_unit_ids: Sequence[str],
    ) -> None:
        for evidence_unit_id in dict.fromkeys(evidence_unit_ids):
            session.add(
                KnowledgeInterpretationEvidenceRecord(
                    id=str(uuid4()),
                    corpus_id=corpus_id,
                    interpretation_type=interpretation_type,
                    interpretation_id=interpretation_id,
                    evidence_unit_id=evidence_unit_id,
                )
            )

    def _require_graph_node(
        self,
        session: Session,
        corpus_id: str,
        ref_type: str,
        ref_id: str,
    ) -> None:
        if ref_type == "canonical_entity":
            self._require_entity_in_corpus(session, ref_id, corpus_id)
            return
        models: dict[str, type[Any]] = {
            "assertion": KnowledgeExtractedAssertionRecord,
            "world_event": KnowledgeWorldEventRecord,
            "evidence_unit": KnowledgeEvidenceUnitRecord,
        }
        model = models.get(ref_type)
        if model is not None:
            if ref_type == "evidence_unit":
                self._require_evidence_units(session, corpus_id, (ref_id,))
                return
            record = session.get(model, ref_id)
            if record is None or record.corpus_id != corpus_id:
                raise ValueError("Knowledge graph node is outside the corpus.")
            return
        if ref_type == "source_version":
            version = session.scalar(
                select(KnowledgeSourceVersionRecord)
                .join(
                    KnowledgeSourceRecord,
                    KnowledgeSourceRecord.id == KnowledgeSourceVersionRecord.source_id,
                )
                .where(
                    KnowledgeSourceVersionRecord.id == ref_id,
                    KnowledgeSourceRecord.corpus_id == corpus_id,
                )
            )
            if version is not None:
                return
        raise ValueError("Unknown or inaccessible Knowledge graph node.")


__all__ = ["KnowledgeFabricInterpretationRepository", "normalize_canonical_entity_name"]
