"""Regenerable, provenance-bearing Knowledge Fabric Projections."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from echo_masque.knowledge_fabric_external_policy import source_uses_current_entries
from echo_masque.knowledge_fabric_projection_policy import source_projection_is_current
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCanonicalDocumentRecord,
    KnowledgeEvidenceUnitRecord,
    KnowledgeProjectionDependencyRecord,
    KnowledgeProjectionRecord,
    KnowledgeSourceCurrentEntryRecord,
    KnowledgeSourceRecord,
    KnowledgeSourceVersionRecord,
)

SOURCE_OVERVIEW_PROJECTION = "source_overview"
SOURCE_SUBJECT_REF_TYPE = "source"


@dataclass(frozen=True, slots=True)
class KnowledgeProjectionProvenance:
    """One explicit immutable dependency suitable for audit and invalidation."""

    source_version_id: str
    evidence_unit_id: str
    source_hash: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class KnowledgeProjectionView:
    """A derived view plus the immutable evidence it is allowed to represent."""

    id: str
    corpus_id: str
    projection_type: str
    subject_ref_type: str
    subject_ref_id: str
    title: str
    text_content: str
    source_hash: str
    stale: bool
    provenance: tuple[KnowledgeProjectionProvenance, ...]


class KnowledgeFabricProjectionRepository:
    """Materialize disposable views without treating them as a second knowledge authority."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get_source_overview(self, source_id: str) -> KnowledgeProjectionView | None:
        """Return a current source overview, rebuilding it only when it is absent or stale."""

        with self.database.session() as session:
            version = session.scalar(
                select(KnowledgeSourceVersionRecord)
                .where(KnowledgeSourceVersionRecord.source_id == source_id)
                .order_by(
                    KnowledgeSourceVersionRecord.observed_at.desc(),
                    KnowledgeSourceVersionRecord.id.desc(),
                )
            )
            if version is None:
                return None
            projection = self._find_source_overview(session, source_id=source_id)
            source = session.get(KnowledgeSourceRecord, source_id)
            if source is None:
                raise KeyError("source")
            projection_is_current = projection is not None and source_projection_is_current(
                projection_source_hash=projection.source_hash,
                current_source_hash=version.source_hash,
                stale=projection.stale,
            )
            if projection is not None and (
                projection_is_current
                or (
                    source_uses_current_entries(source.source_type)
                    and not projection.stale
                )
            ):
                return self._view(session, projection)
        return self.rebuild_source_overview(source_version_id=version.id)

    def rebuild_source_overview(self, *, source_version_id: str) -> KnowledgeProjectionView:
        """Deterministically replace the source overview and its exact dependencies."""

        with self.database.session() as session:
            source_version = session.get(KnowledgeSourceVersionRecord, source_version_id)
            if source_version is None:
                raise KeyError("source_version")
            source = session.get(KnowledgeSourceRecord, source_version.source_id)
            if source is None:
                raise KeyError("source")
            evidence_statement = (
                select(
                    KnowledgeEvidenceUnitRecord,
                    KnowledgeCanonicalDocumentRecord.title,
                    KnowledgeSourceVersionRecord,
                )
                .join(
                    KnowledgeCanonicalDocumentRecord,
                    KnowledgeCanonicalDocumentRecord.id == KnowledgeEvidenceUnitRecord.document_id,
                )
                .join(
                    KnowledgeSourceVersionRecord,
                    KnowledgeSourceVersionRecord.id
                    == KnowledgeEvidenceUnitRecord.source_version_id,
                )
                .order_by(
                    KnowledgeEvidenceUnitRecord.created_at,
                    KnowledgeEvidenceUnitRecord.id,
                )
            )
            if source_uses_current_entries(source.source_type):
                evidence_statement = evidence_statement.join(
                    KnowledgeSourceCurrentEntryRecord,
                    KnowledgeSourceCurrentEntryRecord.current_evidence_unit_id
                    == KnowledgeEvidenceUnitRecord.id,
                ).where(
                    KnowledgeSourceCurrentEntryRecord.source_id == source.id,
                    KnowledgeSourceCurrentEntryRecord.status == "available",
                )
            else:
                evidence_statement = evidence_statement.where(
                    KnowledgeEvidenceUnitRecord.source_version_id == source_version.id
                )
            evidence_rows = list(session.execute(evidence_statement).tuples())
            projection = self._find_source_overview(session, source_id=source.id)
            if projection is None:
                projection = KnowledgeProjectionRecord(
                    id=str(uuid4()),
                    corpus_id=source.corpus_id,
                    projection_type=SOURCE_OVERVIEW_PROJECTION,
                    subject_ref_type=SOURCE_SUBJECT_REF_TYPE,
                    subject_ref_id=source.id,
                    title=self._source_title(source.locator),
                    text_content="",
                    source_hash=source_version.source_hash,
                )
                session.add(projection)
                session.flush()
            else:
                projection.corpus_id = source.corpus_id
                projection.title = self._source_title(source.locator)
                projection.source_hash = source_version.source_hash
                projection.stale = False
                session.execute(
                    delete(KnowledgeProjectionDependencyRecord).where(
                        KnowledgeProjectionDependencyRecord.projection_id == projection.id
                    )
                )

            projection.text_content = self._source_overview_text(evidence_rows)
            for evidence, _title, evidence_source_version in evidence_rows:
                session.add(
                    KnowledgeProjectionDependencyRecord(
                        id=str(uuid4()),
                        projection_id=projection.id,
                        source_version_id=evidence_source_version.id,
                        evidence_unit_id=evidence.id,
                        source_hash=evidence_source_version.source_hash,
                        content_sha256=evidence.content_sha256,
                    )
                )
            session.commit()
            session.refresh(projection)
            return self._view(session, projection)

    def rebuild_existing_source_overview(
        self,
        *,
        source_version_id: str,
    ) -> KnowledgeProjectionView | None:
        """Refresh an existing overview without creating a new view in a worker."""

        with self.database.session() as session:
            source_version = session.get(KnowledgeSourceVersionRecord, source_version_id)
            if source_version is None:
                raise KeyError("source_version")
            if self._find_source_overview(session, source_id=source_version.source_id) is None:
                return None
        return self.rebuild_source_overview(source_version_id=source_version_id)

    def mark_source_projections_stale(self, session: Session, *, source_id: str) -> int:
        """Invalidate every derived view depending on any historical version of one Source."""

        projection_ids = select(KnowledgeProjectionDependencyRecord.projection_id).join(
            KnowledgeSourceVersionRecord,
            KnowledgeSourceVersionRecord.id
            == KnowledgeProjectionDependencyRecord.source_version_id,
        ).where(KnowledgeSourceVersionRecord.source_id == source_id)
        result = session.execute(
            update(KnowledgeProjectionRecord)
            .where(
                KnowledgeProjectionRecord.id.in_(projection_ids),
                KnowledgeProjectionRecord.stale.is_(False),
            )
            .values(stale=True)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    @classmethod
    def delete_projections_for_corpora(
        cls,
        session: Session,
        corpus_ids: Sequence[str],
    ) -> dict[str, int]:
        """Delete dependencies before their Evidence/SourceVersion foreign keys disappear."""

        if not corpus_ids:
            return cls.empty_counts()
        projection_ids = list(
            session.scalars(
                select(KnowledgeProjectionRecord.id).where(
                    KnowledgeProjectionRecord.corpus_id.in_(corpus_ids)
                )
            )
        )
        counts = cls.empty_counts()
        if projection_ids:
            dependencies = session.execute(
                delete(KnowledgeProjectionDependencyRecord).where(
                    KnowledgeProjectionDependencyRecord.projection_id.in_(projection_ids)
                )
            )
            counts["knowledge_fabric_projection_dependencies"] = int(
                getattr(dependencies, "rowcount", 0) or 0
            )
            projections = session.execute(
                delete(KnowledgeProjectionRecord).where(
                    KnowledgeProjectionRecord.id.in_(projection_ids)
                )
            )
            counts["knowledge_fabric_projections"] = int(
                getattr(projections, "rowcount", 0) or 0
            )
        return counts

    @staticmethod
    def empty_counts() -> dict[str, int]:
        return {
            "knowledge_fabric_projections": 0,
            "knowledge_fabric_projection_dependencies": 0,
        }

    @staticmethod
    def _find_source_overview(
        session: Session,
        *,
        source_id: str,
    ) -> KnowledgeProjectionRecord | None:
        return session.scalar(
            select(KnowledgeProjectionRecord).where(
                KnowledgeProjectionRecord.projection_type == SOURCE_OVERVIEW_PROJECTION,
                KnowledgeProjectionRecord.subject_ref_type == SOURCE_SUBJECT_REF_TYPE,
                KnowledgeProjectionRecord.subject_ref_id == source_id,
            )
        )

    @staticmethod
    def _source_title(locator: str) -> str:
        return f"Source overview: {locator}"

    @staticmethod
    def _source_overview_text(
        evidence_rows: list[
            tuple[
                KnowledgeEvidenceUnitRecord,
                str,
                KnowledgeSourceVersionRecord,
            ]
        ],
    ) -> str:
        """Keep a deterministic, provenance-preserving representation, not an invented summary."""

        return "\n\n".join(
            f"[{title or 'Untitled document'}]\n{evidence.text_content}"
            for evidence, title, _source_version in evidence_rows
        )

    @staticmethod
    def _view(
        session: Session,
        projection: KnowledgeProjectionRecord,
    ) -> KnowledgeProjectionView:
        dependencies = tuple(
            KnowledgeProjectionProvenance(
                source_version_id=item.source_version_id,
                evidence_unit_id=item.evidence_unit_id,
                source_hash=item.source_hash,
                content_sha256=item.content_sha256,
            )
            for item in session.scalars(
                select(KnowledgeProjectionDependencyRecord)
                .where(KnowledgeProjectionDependencyRecord.projection_id == projection.id)
                .order_by(
                    KnowledgeProjectionDependencyRecord.source_version_id,
                    KnowledgeProjectionDependencyRecord.evidence_unit_id,
                )
            )
        )
        return KnowledgeProjectionView(
            id=projection.id,
            corpus_id=projection.corpus_id,
            projection_type=projection.projection_type,
            subject_ref_type=projection.subject_ref_type,
            subject_ref_id=projection.subject_ref_id,
            title=projection.title,
            text_content=projection.text_content,
            source_hash=projection.source_hash,
            stale=projection.stale,
            provenance=dependencies,
        )


__all__ = [
    "SOURCE_OVERVIEW_PROJECTION",
    "SOURCE_SUBJECT_REF_TYPE",
    "KnowledgeFabricProjectionRepository",
    "KnowledgeProjectionProvenance",
    "KnowledgeProjectionView",
]
