"""Regenerable sparse and dense indexes over source-aligned Knowledge Evidence Units."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, delete, exists, or_, select, text
from sqlalchemy.orm import Session

from echo_masque.knowledge_fabric_external_policy import source_uses_current_entries
from echo_masque.knowledge_fabric_query_policy import interpretation_is_available_as_of
from echo_masque.knowledge_retrieval import KnowledgeResource, score_sparse_knowledge_resources
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_interpretation_repository import (
    normalize_canonical_entity_name,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCanonicalDocumentRecord,
    KnowledgeCanonicalEntityRecord,
    KnowledgeEvidenceEmbeddingRecord,
    KnowledgeEvidenceGraphRelationRecord,
    KnowledgeEvidenceRetrievalEntryRecord,
    KnowledgeEvidenceUnitRecord,
    KnowledgeExtractedAssertionRecord,
    KnowledgeInterpretationEvidenceRecord,
    KnowledgeSourceCurrentEntryRecord,
    KnowledgeSourceRecord,
    KnowledgeSourceVersionRecord,
    KnowledgeWorldEventParticipantRecord,
    KnowledgeWorldEventRecord,
)


@dataclass(frozen=True, slots=True)
class KnowledgeIndexCandidate:
    """One source-aligned candidate returned by a single bounded retrieval channel."""

    retrieval_entry_id: str
    evidence_unit_id: str
    corpus_id: str
    source_version_id: str
    evidence_locator: str
    document_title: str
    text_content: str
    authority_profile: str
    score: float


class KnowledgeFabricIndexRepository:
    """Build/query derived indexes without making them an authority separate from Evidence."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def rebuild_entries_for_source_version(
        self,
        source_version_id: str,
    ) -> list[KnowledgeEvidenceRetrievalEntryRecord]:
        """Materialize portable retrieval rows for immutable Evidence Units in one version."""

        with self.database.session() as session:
            source_version = session.get(KnowledgeSourceVersionRecord, source_version_id)
            if source_version is None:
                raise KeyError("source_version")
            source = session.get(KnowledgeSourceRecord, source_version.source_id)
            if source is None:
                raise KeyError("source")
            statement = select(KnowledgeEvidenceUnitRecord.id).where(
                KnowledgeEvidenceUnitRecord.source_version_id == source_version_id
            )
            if source_uses_current_entries(source.source_type):
                statement = statement.join(
                    KnowledgeSourceCurrentEntryRecord,
                    KnowledgeSourceCurrentEntryRecord.current_evidence_unit_id
                    == KnowledgeEvidenceUnitRecord.id,
                ).where(
                    KnowledgeSourceCurrentEntryRecord.source_id == source.id,
                    KnowledgeSourceCurrentEntryRecord.status == "available",
                )
            evidence_ids = list(session.scalars(statement))
        return [self.upsert_retrieval_entry(evidence_unit_id) for evidence_unit_id in evidence_ids]

    def upsert_retrieval_entry(
        self,
        evidence_unit_id: str,
    ) -> KnowledgeEvidenceRetrievalEntryRecord:
        """Create the one corpus-filterable projection row after validating its provenance join."""

        with self.database.session() as session:
            evidence, source_version, source = self._require_evidence_provenance(
                session,
                evidence_unit_id,
            )
            record = session.scalar(
                select(KnowledgeEvidenceRetrievalEntryRecord).where(
                    KnowledgeEvidenceRetrievalEntryRecord.evidence_unit_id == evidence.id
                )
            )
            if record is None:
                record = KnowledgeEvidenceRetrievalEntryRecord(
                    id=str(uuid4()),
                    corpus_id=source.corpus_id,
                    evidence_unit_id=evidence.id,
                    source_version_id=source_version.id,
                    retrieval_text=evidence.text_content,
                    content_sha256=evidence.content_sha256,
                )
                session.add(record)
            else:
                record.corpus_id = source.corpus_id
                record.source_version_id = source_version.id
                record.retrieval_text = evidence.text_content
                record.content_sha256 = evidence.content_sha256
            session.commit()
            session.refresh(record)
            return record

    def upsert_embedding(
        self,
        *,
        retrieval_entry_id: str,
        embedding_model: str,
        vector: Sequence[float],
    ) -> KnowledgeEvidenceEmbeddingRecord:
        """Store a deterministic derived dense representation; the source hash is immutable."""

        self._require_embedding_profile(embedding_model, vector)
        normalized_vector = [float(value) for value in vector]
        encoded_vector = json.dumps(normalized_vector, separators=(",", ":"))
        with self.database.session() as session:
            entry = session.get(KnowledgeEvidenceRetrievalEntryRecord, retrieval_entry_id)
            if entry is None:
                raise KeyError("Knowledge retrieval entry not found.")
            record = session.scalar(
                select(KnowledgeEvidenceEmbeddingRecord).where(
                    KnowledgeEvidenceEmbeddingRecord.retrieval_entry_id == entry.id,
                    KnowledgeEvidenceEmbeddingRecord.embedding_model == embedding_model,
                    KnowledgeEvidenceEmbeddingRecord.embedding_dimension == len(normalized_vector),
                    KnowledgeEvidenceEmbeddingRecord.source_hash == entry.content_sha256,
                )
            )
            if record is None:
                record = KnowledgeEvidenceEmbeddingRecord(
                    id=str(uuid4()),
                    retrieval_entry_id=entry.id,
                    embedding_model=embedding_model,
                    embedding_dimension=len(normalized_vector),
                    source_hash=entry.content_sha256,
                    embedding_json=encoded_vector,
                )
                session.add(record)
                session.flush()
            if self.database.engine.dialect.name == "postgresql":
                session.execute(
                    text(
                        "UPDATE knowledge_evidence_embeddings "
                        "SET embedding = CAST(:embedding AS vector) "
                        "WHERE id = :embedding_id"
                    ),
                    {"embedding": encoded_vector, "embedding_id": record.id},
                )
            session.commit()
            session.refresh(record)
            return record

    def search_sparse(
        self,
        *,
        authorized_corpus_ids: frozenset[str],
        query: str,
        candidate_limit: int,
    ) -> list[KnowledgeIndexCandidate]:
        """Search only already-authorized corpus rows, using PostgreSQL FTS when available."""

        self._require_search_inputs(authorized_corpus_ids, query, candidate_limit)
        with self.database.session() as session:
            if self.database.engine.dialect.name == "postgresql":
                return self._search_postgresql_sparse(
                    session,
                    authorized_corpus_ids=authorized_corpus_ids,
                    query=query,
                    candidate_limit=candidate_limit,
                )
            candidates = self._load_candidates_for_corpora(session, authorized_corpus_ids)
        resources = [
            KnowledgeResource(
                chunk_id=item.retrieval_entry_id,
                knowledge_base_id=item.corpus_id,
                document_id=item.source_version_id,
                document_title=item.document_title,
                chunk_index=0,
                content=item.text_content,
            )
            for item in candidates
        ]
        sparse_scores = {
            item.resource.chunk_id: item.score
            for item in score_sparse_knowledge_resources(resources, query=query)
            if item.score > 0.0
        }
        return self._with_scores(candidates, sparse_scores, candidate_limit)

    def search_dense(
        self,
        *,
        authorized_corpus_ids: frozenset[str],
        embedding_model: str,
        query_vector: Sequence[float],
        candidate_limit: int,
    ) -> list[KnowledgeIndexCandidate]:
        """Search dense projections with the same corpus filter supplied before ranking."""

        self._require_search_inputs(authorized_corpus_ids, "dense", candidate_limit)
        self._require_embedding_profile(embedding_model, query_vector)
        normalized_vector = [float(value) for value in query_vector]
        with self.database.session() as session:
            if self.database.engine.dialect.name == "postgresql":
                return self._search_postgresql_dense(
                    session,
                    authorized_corpus_ids=authorized_corpus_ids,
                    embedding_model=embedding_model,
                    query_vector=normalized_vector,
                    candidate_limit=candidate_limit,
                )
            rows = list(
                session.execute(
                    self._candidate_select()
                    .add_columns(KnowledgeEvidenceEmbeddingRecord)
                    .join(
                        KnowledgeEvidenceEmbeddingRecord,
                        KnowledgeEvidenceEmbeddingRecord.retrieval_entry_id
                        == KnowledgeEvidenceRetrievalEntryRecord.id,
                    )
                    .where(
                        KnowledgeEvidenceRetrievalEntryRecord.corpus_id.in_(authorized_corpus_ids),
                        KnowledgeEvidenceEmbeddingRecord.embedding_model == embedding_model,
                        KnowledgeEvidenceEmbeddingRecord.embedding_dimension
                        == len(normalized_vector),
                    )
                )
            )
        candidates = self._candidates_from_rows(rows, channel="dense")
        scores: dict[str, float] = {}
        for candidate, row in zip(candidates, rows, strict=True):
            embedding = row[5]
            assert isinstance(embedding, KnowledgeEvidenceEmbeddingRecord)
            try:
                stored_vector = json.loads(embedding.embedding_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(stored_vector, list) or len(stored_vector) != len(normalized_vector):
                continue
            if not all(isinstance(value, int | float) for value in stored_vector):
                continue
            scores[candidate.retrieval_entry_id] = self._cosine(normalized_vector, stored_vector)
        return self._with_scores(candidates, scores, candidate_limit)

    def search_entity_graph(
        self,
        *,
        authorized_corpus_ids: frozenset[str],
        query: str,
        as_of: datetime | None,
        candidate_limit: int,
    ) -> list[KnowledgeIndexCandidate]:
        """Return source Evidence linked to an exact corpus entity or its graph relations."""

        self._require_search_inputs(authorized_corpus_ids, query, candidate_limit)
        normalized_query = normalize_canonical_entity_name(query)

        with self.database.session() as session:
            entities = list(
                session.scalars(
                    select(KnowledgeCanonicalEntityRecord).where(
                        KnowledgeCanonicalEntityRecord.corpus_id.in_(authorized_corpus_ids),
                        KnowledgeCanonicalEntityRecord.normalized_name == normalized_query,
                    )
                )
            )
            entity_ids = [item.id for item in entities]
            if not entity_ids:
                return []
            evidence_ids: list[str] = []
            assertions = list(
                session.scalars(
                    select(KnowledgeExtractedAssertionRecord).where(
                        KnowledgeExtractedAssertionRecord.corpus_id.in_(authorized_corpus_ids),
                        KnowledgeExtractedAssertionRecord.subject_entity_id.in_(entity_ids),
                    )
                )
            )
            events = list(
                session.scalars(
                    select(KnowledgeWorldEventRecord)
                    .join(
                        KnowledgeWorldEventParticipantRecord,
                        KnowledgeWorldEventParticipantRecord.event_id
                        == KnowledgeWorldEventRecord.id,
                    )
                    .where(
                        KnowledgeWorldEventRecord.corpus_id.in_(authorized_corpus_ids),
                        KnowledgeWorldEventParticipantRecord.canonical_entity_id.in_(entity_ids),
                    )
                )
            )
            graph_relation_ids = list(
                session.scalars(
                    select(KnowledgeEvidenceGraphRelationRecord.id).where(
                        KnowledgeEvidenceGraphRelationRecord.corpus_id.in_(
                            authorized_corpus_ids
                        ),
                        (
                            (
                                KnowledgeEvidenceGraphRelationRecord.source_ref_type
                                == "canonical_entity"
                            )
                            & KnowledgeEvidenceGraphRelationRecord.source_ref_id.in_(entity_ids)
                        )
                        | (
                            (
                                KnowledgeEvidenceGraphRelationRecord.target_ref_type
                                == "canonical_entity"
                            )
                            & KnowledgeEvidenceGraphRelationRecord.target_ref_id.in_(entity_ids)
                        ),
                    )
                )
            )
            interpretation_ids = [
                *(item.id for item in assertions if interpretation_is_available_as_of(
                    valid_from=item.valid_from,
                    valid_to=item.valid_to,
                    as_of=as_of,
                )),
                *(item.id for item in events if interpretation_is_available_as_of(
                    valid_from=item.valid_from,
                    valid_to=item.valid_to,
                    as_of=as_of,
                )),
                *graph_relation_ids,
            ]
            if interpretation_ids:
                evidence_ids = list(
                    session.scalars(
                        select(KnowledgeInterpretationEvidenceRecord.evidence_unit_id).where(
                            KnowledgeInterpretationEvidenceRecord.corpus_id.in_(
                                authorized_corpus_ids
                            ),
                            KnowledgeInterpretationEvidenceRecord.interpretation_id.in_(
                                interpretation_ids
                            ),
                        )
                    )
                )
            candidates = self._load_candidates_for_evidence(
                session,
                evidence_ids,
                channel="entity",
            )
            return candidates[:candidate_limit]

    @staticmethod
    def delete_indexes_for_evidence_units(
        session: Session,
        evidence_unit_ids: Sequence[str],
    ) -> dict[str, int]:
        """Delete regenerable children before Phase 3 removes their Evidence Units."""

        if not evidence_unit_ids:
            return {
                "knowledge_fabric_evidence_embeddings": 0,
                "knowledge_fabric_retrieval_entries": 0,
            }
        entry_ids = list(
            session.scalars(
                select(KnowledgeEvidenceRetrievalEntryRecord.id).where(
                    KnowledgeEvidenceRetrievalEntryRecord.evidence_unit_id.in_(evidence_unit_ids)
                )
            )
        )
        embedding_result = (
            session.execute(
                delete(KnowledgeEvidenceEmbeddingRecord).where(
                    KnowledgeEvidenceEmbeddingRecord.retrieval_entry_id.in_(entry_ids)
                )
            )
            if entry_ids
            else None
        )
        entry_result = session.execute(
            delete(KnowledgeEvidenceRetrievalEntryRecord).where(
                KnowledgeEvidenceRetrievalEntryRecord.evidence_unit_id.in_(evidence_unit_ids)
            )
        )
        return {
            "knowledge_fabric_evidence_embeddings": KnowledgeFabricIndexRepository._rowcount(
                embedding_result
            ),
            "knowledge_fabric_retrieval_entries": KnowledgeFabricIndexRepository._rowcount(
                entry_result
            ),
        }

    def _search_postgresql_sparse(
        self,
        session: Session,
        *,
        authorized_corpus_ids: frozenset[str],
        query: str,
        candidate_limit: int,
    ) -> list[KnowledgeIndexCandidate]:
        statement = text(
            "SELECT entry.id AS entry_id, "
            "ts_rank_cd(to_tsvector('simple', entry.retrieval_text), "
            "websearch_to_tsquery('simple', :query)) AS score "
            "FROM knowledge_evidence_retrieval_entries AS entry "
            "JOIN knowledge_evidence_units AS evidence ON evidence.id = entry.evidence_unit_id "
            "JOIN knowledge_source_versions AS version ON version.id = entry.source_version_id "
            "JOIN knowledge_sources AS source ON source.id = version.source_id "
            "WHERE entry.corpus_id IN :corpus_ids "
            "AND evidence.status = 'available' AND version.status = 'available' "
            "AND source.enabled IS TRUE "
            "AND (source.source_type NOT IN ("
            "'atom_public_https', 'website_collection_public_https') OR EXISTS ("
            "SELECT 1 FROM knowledge_source_current_entries AS current_entry "
            "WHERE current_entry.source_id = source.id "
            "AND current_entry.current_evidence_unit_id = evidence.id "
            "AND current_entry.status = 'available')) "
            "AND to_tsvector('simple', entry.retrieval_text) "
            "@@ websearch_to_tsquery('simple', :query) "
            "ORDER BY score DESC, entry.id ASC LIMIT :candidate_limit"
        ).bindparams(bindparam("corpus_ids", expanding=True))
        rows = session.execute(
            statement,
            {
                "corpus_ids": sorted(authorized_corpus_ids),
                "query": query,
                "candidate_limit": candidate_limit,
            },
        ).mappings()
        scores = {str(row["entry_id"]): float(row["score"]) for row in rows}
        return self._load_candidates_for_entries(
            session,
            scores,
            channel="sparse",
            candidate_limit=candidate_limit,
        )

    def _search_postgresql_dense(
        self,
        session: Session,
        *,
        authorized_corpus_ids: frozenset[str],
        embedding_model: str,
        query_vector: Sequence[float],
        candidate_limit: int,
    ) -> list[KnowledgeIndexCandidate]:
        vector_literal = json.dumps(list(query_vector), separators=(",", ":"))
        statement = text(
            "SELECT entry.id AS entry_id, "
            "1 - (embedding.embedding <=> CAST(:query_vector AS vector)) AS score "
            "FROM knowledge_evidence_embeddings AS embedding "
            "JOIN knowledge_evidence_retrieval_entries AS entry "
            "ON entry.id = embedding.retrieval_entry_id "
            "JOIN knowledge_evidence_units AS evidence ON evidence.id = entry.evidence_unit_id "
            "JOIN knowledge_source_versions AS version ON version.id = entry.source_version_id "
            "JOIN knowledge_sources AS source ON source.id = version.source_id "
            "WHERE entry.corpus_id IN :corpus_ids "
            "AND embedding.embedding_model = :embedding_model "
            "AND embedding.embedding_dimension = :embedding_dimension "
            "AND embedding.embedding IS NOT NULL "
            "AND evidence.status = 'available' AND version.status = 'available' "
            "AND source.enabled IS TRUE "
            "AND (source.source_type NOT IN ("
            "'atom_public_https', 'website_collection_public_https') OR EXISTS ("
            "SELECT 1 FROM knowledge_source_current_entries AS current_entry "
            "WHERE current_entry.source_id = source.id "
            "AND current_entry.current_evidence_unit_id = evidence.id "
            "AND current_entry.status = 'available')) "
            "ORDER BY embedding.embedding <=> CAST(:query_vector AS vector), entry.id ASC "
            "LIMIT :candidate_limit"
        ).bindparams(bindparam("corpus_ids", expanding=True))
        rows = session.execute(
            statement,
            {
                "corpus_ids": sorted(authorized_corpus_ids),
                "embedding_model": embedding_model,
                "embedding_dimension": len(query_vector),
                "query_vector": vector_literal,
                "candidate_limit": candidate_limit,
            },
        ).mappings()
        scores = {str(row["entry_id"]): float(row["score"]) for row in rows}
        return self._load_candidates_for_entries(
            session,
            scores,
            channel="dense",
            candidate_limit=candidate_limit,
        )

    def _load_candidates_for_entries(
        self,
        session: Session,
        scores: dict[str, float],
        *,
        channel: str,
        candidate_limit: int,
    ) -> list[KnowledgeIndexCandidate]:
        if not scores:
            return []
        rows = list(
            session.execute(
                self._candidate_select().where(
                    KnowledgeEvidenceRetrievalEntryRecord.id.in_(scores)
                )
            )
        )
        candidates = self._candidates_from_rows(rows, channel=channel)
        return self._with_scores(candidates, scores, candidate_limit)

    def _load_candidates_for_corpora(
        self,
        session: Session,
        authorized_corpus_ids: frozenset[str],
    ) -> list[KnowledgeIndexCandidate]:
        rows = list(
            session.execute(
                self._candidate_select().where(
                    KnowledgeEvidenceRetrievalEntryRecord.corpus_id.in_(authorized_corpus_ids)
                )
            )
        )
        return self._candidates_from_rows(rows, channel="sparse")

    def _load_candidates_for_evidence(
        self,
        session: Session,
        evidence_unit_ids: Sequence[str],
        *,
        channel: str,
    ) -> list[KnowledgeIndexCandidate]:
        if not evidence_unit_ids:
            return []
        rows = list(
            session.execute(
                self._candidate_select().where(
                    KnowledgeEvidenceRetrievalEntryRecord.evidence_unit_id.in_(evidence_unit_ids)
                )
            )
        )
        return sorted(
            self._candidates_from_rows(rows, channel=channel),
            key=lambda item: item.retrieval_entry_id,
        )

    @staticmethod
    def _candidate_select() -> Any:
        current_entry_evidence = exists(
            select(KnowledgeSourceCurrentEntryRecord.id).where(
                KnowledgeSourceCurrentEntryRecord.source_id == KnowledgeSourceRecord.id,
                KnowledgeSourceCurrentEntryRecord.current_evidence_unit_id
                == KnowledgeEvidenceUnitRecord.id,
                KnowledgeSourceCurrentEntryRecord.status == "available",
            )
        )
        return (
            select(
                KnowledgeEvidenceRetrievalEntryRecord,
                KnowledgeEvidenceUnitRecord,
                KnowledgeSourceVersionRecord,
                KnowledgeSourceRecord,
                KnowledgeCanonicalDocumentRecord,
            )
            .join(
                KnowledgeEvidenceUnitRecord,
                KnowledgeEvidenceUnitRecord.id
                == KnowledgeEvidenceRetrievalEntryRecord.evidence_unit_id,
            )
            .join(
                KnowledgeSourceVersionRecord,
                KnowledgeSourceVersionRecord.id
                == KnowledgeEvidenceRetrievalEntryRecord.source_version_id,
            )
            .join(
                KnowledgeSourceRecord,
                KnowledgeSourceRecord.id == KnowledgeSourceVersionRecord.source_id,
            )
            .join(
                KnowledgeCanonicalDocumentRecord,
                KnowledgeCanonicalDocumentRecord.id == KnowledgeEvidenceUnitRecord.document_id,
            )
            .where(
                KnowledgeEvidenceUnitRecord.status == "available",
                KnowledgeSourceVersionRecord.status == "available",
                KnowledgeSourceRecord.enabled.is_(True),
                or_(
                    ~KnowledgeSourceRecord.source_type.in_(
                        ("atom_public_https", "website_collection_public_https")
                    ),
                    current_entry_evidence,
                ),
            )
        )

    @staticmethod
    def _candidates_from_rows(
        rows: Sequence[Sequence[object]],
        *,
        channel: str,
    ) -> list[KnowledgeIndexCandidate]:
        del channel
        candidates: list[KnowledgeIndexCandidate] = []
        for row in rows:
            entry, evidence, version, _source, document = row[:5]
            assert isinstance(entry, KnowledgeEvidenceRetrievalEntryRecord)
            assert isinstance(evidence, KnowledgeEvidenceUnitRecord)
            assert isinstance(version, KnowledgeSourceVersionRecord)
            assert isinstance(document, KnowledgeCanonicalDocumentRecord)
            candidates.append(
                KnowledgeIndexCandidate(
                    retrieval_entry_id=entry.id,
                    evidence_unit_id=evidence.id,
                    corpus_id=entry.corpus_id,
                    source_version_id=version.id,
                    evidence_locator=evidence.evidence_locator,
                    document_title=document.title,
                    text_content=evidence.text_content,
                    authority_profile=evidence.authority_profile,
                    score=0.0,
                )
            )
        return candidates

    @staticmethod
    def _with_scores(
        candidates: Sequence[KnowledgeIndexCandidate],
        scores: dict[str, float],
        candidate_limit: int,
    ) -> list[KnowledgeIndexCandidate]:
        ranked = [
            KnowledgeIndexCandidate(
                retrieval_entry_id=item.retrieval_entry_id,
                evidence_unit_id=item.evidence_unit_id,
                corpus_id=item.corpus_id,
                source_version_id=item.source_version_id,
                evidence_locator=item.evidence_locator,
                document_title=item.document_title,
                text_content=item.text_content,
                authority_profile=item.authority_profile,
                score=round(scores[item.retrieval_entry_id], 6),
            )
            for item in candidates
            if item.retrieval_entry_id in scores and scores[item.retrieval_entry_id] > 0.0
        ]
        ranked.sort(key=lambda item: (-item.score, item.retrieval_entry_id))
        return ranked[:candidate_limit]

    @staticmethod
    def _require_evidence_provenance(
        session: Session,
        evidence_unit_id: str,
    ) -> tuple[KnowledgeEvidenceUnitRecord, KnowledgeSourceVersionRecord, KnowledgeSourceRecord]:
        row = session.execute(
            select(
                KnowledgeEvidenceUnitRecord,
                KnowledgeSourceVersionRecord,
                KnowledgeSourceRecord,
            )
            .join(
                KnowledgeSourceVersionRecord,
                KnowledgeSourceVersionRecord.id == KnowledgeEvidenceUnitRecord.source_version_id,
            )
            .join(
                KnowledgeSourceRecord,
                KnowledgeSourceRecord.id == KnowledgeSourceVersionRecord.source_id,
            )
            .where(KnowledgeEvidenceUnitRecord.id == evidence_unit_id)
        ).one_or_none()
        if row is None:
            raise KeyError("Knowledge Evidence Unit not found.")
        evidence, version, source = row
        return evidence, version, source

    @staticmethod
    def _require_search_inputs(
        authorized_corpus_ids: frozenset[str],
        query: str,
        candidate_limit: int,
    ) -> None:
        if not authorized_corpus_ids:
            raise ValueError("Knowledge search requires an authorized corpus.")
        if not query.strip():
            raise ValueError("Knowledge search query is required.")
        if candidate_limit <= 0:
            raise ValueError("Knowledge candidate limit must be positive.")

    @staticmethod
    def _require_embedding_profile(embedding_model: str, vector: Sequence[float]) -> None:
        if not embedding_model.strip():
            raise ValueError("Knowledge embedding model is required.")
        if not vector or not all(math.isfinite(float(value)) for value in vector):
            raise ValueError("Knowledge embedding vector must contain finite values.")

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[object]) -> float:
        try:
            right_values = [float(str(value)) for value in right]
        except (TypeError, ValueError):
            return 0.0
        dot = sum(
            left_value * right_value
            for left_value, right_value in zip(left, right_values, strict=True)
        )
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right_values))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _rowcount(result: object | None) -> int:
        value = getattr(result, "rowcount", 0)
        return int(value) if isinstance(value, int) and value > 0 else 0


__all__ = ["KnowledgeFabricIndexRepository", "KnowledgeIndexCandidate"]
