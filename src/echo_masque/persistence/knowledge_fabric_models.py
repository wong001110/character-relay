"""Durable scope and access records for the Knowledge Fabric.

These records deliberately do not reuse Discord deployment profiles or join-code
access.  A KnowledgeServerScope is a stable product principal and its explicit
administrator membership is the only Phase 2 server-local authority.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class KnowledgeServerScopeRecord(Base):
    """Canonical server identity, stable across profile and connector changes."""

    __tablename__ = "knowledge_server_scopes"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "connection_id",
            "workspace_id",
            name="uq_knowledge_server_scope_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeServerAdministratorRecord(Base):
    """An explicit account membership authorized for one canonical server scope."""

    __tablename__ = "knowledge_server_administrators"
    __table_args__ = (
        UniqueConstraint(
            "server_scope_id",
            "user_id",
            name="uq_knowledge_server_administrator",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_scope_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_server_scopes.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeCorpusRecord(Base):
    """Corpus ownership and visibility metadata; imported content arrives later."""

    __tablename__ = "knowledge_corpora"
    __table_args__ = (Index("ix_knowledge_corpora_owner_scope", "owner_type", "owner_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(24), nullable=False)
    default_authority_profile: Mapped[str] = mapped_column(
        String(80), default="standard", nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeSourceRecord(Base):
    """Registered source metadata only; source versions and artifacts are Phase 3."""

    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    locator: Mapped[str] = mapped_column(String(1000), nullable=False)
    access_profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    parser_profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    sync_policy_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    freshness_policy_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    authority_profile: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="registered", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeExternalSourceSyncStateRecord(Base):
    """Regenerable validator/outcome state for a Source; never raw response or credentials."""

    __tablename__ = "knowledge_external_source_sync_states"

    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"), primary_key=True
    )
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(512))
    last_outcome: Mapped[str] = mapped_column(String(40), default="never_checked", nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeExternalSourceScheduleRecord(Base):
    """Default-disabled durable lease/rate schedule for an approved public external Source."""

    __tablename__ = "knowledge_external_source_schedules"

    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lease_token: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeExternalHostRateRecord(Base):
    """One global host cooldown across all opt-in external Source schedules."""

    __tablename__ = "knowledge_external_host_rates"

    hostname: Mapped[str] = mapped_column(String(253), primary_key=True)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeObjectArtifactRecord(Base):
    """A private R2/S3 object reference; raw bytes never become a public database field."""

    __tablename__ = "knowledge_object_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "storage_provider",
            "bucket",
            "object_key",
            name="uq_knowledge_object_artifact_location",
        ),
        Index("ix_knowledge_object_artifact_source", "source_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"), index=True, nullable=False
    )
    storage_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="stored", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeObjectDeletionRecord(Base):
    """Durable private-object cleanup intent, independent of deleted Fabric provenance rows.

    Object storage cannot join the relational transaction.  This outbox lets lifecycle deletion
    commit the access/provenance removal first, then retry private-object deletion safely after
    the record that referenced it no longer exists.
    """

    __tablename__ = "knowledge_object_deletions"
    __table_args__ = (
        UniqueConstraint(
            "storage_provider",
            "bucket",
            "object_key",
            name="uq_knowledge_object_deletion_location",
        ),
        Index("ix_knowledge_object_deletion_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    storage_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeSourceVersionRecord(Base):
    """One immutable source snapshot anchored to a private original artifact."""

    __tablename__ = "knowledge_source_versions"
    __table_args__ = (
        UniqueConstraint("source_id", "version_key", name="uq_knowledge_source_version_key"),
        UniqueConstraint("source_id", "source_hash", name="uq_knowledge_source_version_hash"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"), index=True, nullable=False
    )
    version_key: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_object_artifacts.id"), index=True, nullable=False
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="available", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeSourceCurrentEntryRecord(Base):
    """Derived current entry pointer for source-native incremental adapters.

    It never replaces an immutable SourceVersion, document, or Evidence Unit.  It only says which
    retained Evidence Unit is the current representation for one stable adapter entry identity.
    """

    __tablename__ = "knowledge_source_current_entries"
    __table_args__ = (
        UniqueConstraint("source_id", "entry_locator", name="uq_knowledge_source_current_entry"),
        Index("ix_knowledge_source_current_entry_evidence", "current_evidence_unit_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"), index=True, nullable=False
    )
    entry_locator: Mapped[str] = mapped_column(String(1000), nullable=False)
    current_source_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_source_versions.id"), index=True, nullable=False
    )
    current_evidence_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_evidence_units.id"), index=True
    )
    entry_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="available", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeCanonicalDocumentRecord(Base):
    """Structured source-version content, distinct from a regenerable retrieval chunk."""

    __tablename__ = "knowledge_canonical_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id",
            "canonical_locator",
            name="uq_knowledge_canonical_document_locator",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_source_versions.id"), index=True, nullable=False
    )
    canonical_locator: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    language: Mapped[str | None] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeCanonicalSectionRecord(Base):
    """Hierarchical canonical document structure with durable source coordinates."""

    __tablename__ = "knowledge_canonical_sections"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "structural_path",
            name="uq_knowledge_canonical_section_path",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_canonical_documents.id"), index=True, nullable=False
    )
    parent_section_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_canonical_sections.id"), index=True
    )
    structural_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    heading: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    coordinates_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeCanonicalBlockRecord(Base):
    """One bounded structured textual unit; index chunks may later reference many blocks."""

    __tablename__ = "knowledge_canonical_blocks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "structural_path",
            name="uq_knowledge_canonical_block_path",
        ),
        Index("ix_knowledge_canonical_block_section", "section_id", "ordinal"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_canonical_documents.id"), index=True, nullable=False
    )
    section_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_canonical_sections.id"), index=True
    )
    structural_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    block_type: Mapped[str] = mapped_column(String(80), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    coordinates_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeAssetReferenceRecord(Base):
    """A binary/image/table asset referenced privately from canonical structure."""

    __tablename__ = "knowledge_asset_references"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "structural_path",
            name="uq_knowledge_asset_reference_path",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_canonical_documents.id"), index=True, nullable=False
    )
    block_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_canonical_blocks.id"), index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_object_artifacts.id"), index=True, nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False)
    structural_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    coordinates_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEvidenceUnitRecord(Base):
    """A bounded, source-addressable evidence target, never a durable chunk identity."""

    __tablename__ = "knowledge_evidence_units"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id",
            "evidence_locator",
            name="uq_knowledge_evidence_unit_locator",
        ),
        Index("ix_knowledge_evidence_unit_document", "document_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_source_versions.id"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_canonical_documents.id"), index=True, nullable=False
    )
    block_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_canonical_blocks.id"), index=True
    )
    asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_asset_references.id"), index=True
    )
    evidence_locator: Mapped[str] = mapped_column(String(1200), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    text_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    coordinates_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    authority_profile: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="available", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeIngestionJobRecord(Base):
    """Restart-safe background ingest work; no Character reply owns this state."""

    __tablename__ = "knowledge_ingestion_jobs"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "job_type",
            "idempotency_key",
            name="uq_knowledge_ingestion_job_idempotency",
        ),
        Index("ix_knowledge_ingestion_job_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"), index=True, nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_source_versions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeIngestionCheckpointRecord(Base):
    """Safe checkpoint metadata for one stage of a restartable ingestion job."""

    __tablename__ = "knowledge_ingestion_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "stage",
            name="uq_knowledge_ingestion_checkpoint_stage",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_ingestion_jobs.id"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeDependencyInvalidationRecord(Base):
    """Pending downstream work when an immutable version changes corpus evidence."""

    __tablename__ = "knowledge_dependency_invalidations"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id",
            "dependency_type",
            name="uq_knowledge_dependency_invalidation",
        ),
        Index("ix_knowledge_dependency_invalidation_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_source_versions.id"), index=True, nullable=False
    )
    dependency_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeProjectionRecord(Base):
    """A disposable Fabric view with explicit, source-aligned provenance."""

    __tablename__ = "knowledge_projections"
    __table_args__ = (
        UniqueConstraint(
            "corpus_id",
            "projection_type",
            "subject_ref_type",
            "subject_ref_id",
            name="uq_knowledge_projection_subject",
        ),
        Index(
            "ix_knowledge_projection_corpus_stale",
            "corpus_id",
            "stale",
            "projection_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    projection_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_ref_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_ref_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    text_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeProjectionDependencyRecord(Base):
    """One exact SourceVersion/Evidence dependency behind a derived Projection."""

    __tablename__ = "knowledge_projection_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "projection_id",
            "source_version_id",
            "evidence_unit_id",
            name="uq_knowledge_projection_dependency",
        ),
        Index(
            "ix_knowledge_projection_dependency_version",
            "source_version_id",
            "projection_id",
        ),
        Index(
            "ix_knowledge_projection_dependency_evidence",
            "evidence_unit_id",
            "projection_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    projection_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_projections.id"), index=True, nullable=False
    )
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_source_versions.id"), index=True, nullable=False
    )
    evidence_unit_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_evidence_units.id"), index=True, nullable=False
    )
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEvidenceRetrievalEntryRecord(Base):
    """Regenerable corpus-filterable sparse retrieval projection for one Evidence Unit."""

    __tablename__ = "knowledge_evidence_retrieval_entries"
    __table_args__ = (
        UniqueConstraint(
            "evidence_unit_id",
            name="uq_knowledge_evidence_retrieval_entry_evidence",
        ),
        Index(
            "ix_knowledge_evidence_retrieval_entry_corpus_version",
            "corpus_id",
            "source_version_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    evidence_unit_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_evidence_units.id"), index=True, nullable=False
    )
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_source_versions.id"), index=True, nullable=False
    )
    retrieval_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeEvidenceEmbeddingRecord(Base):
    """One regenerable dense representation for a retrieval entry and embedding profile."""

    __tablename__ = "knowledge_evidence_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "retrieval_entry_id",
            "embedding_model",
            "embedding_dimension",
            "source_hash",
            name="uq_knowledge_evidence_embedding_profile",
        ),
        Index(
            "ix_knowledge_evidence_embedding_model_dimension",
            "embedding_model",
            "embedding_dimension",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    retrieval_entry_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_evidence_retrieval_entries.id"), index=True, nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Portable JSON remains the exact-search fallback. PostgreSQL additionally receives a
    # migration-owned vector column so the ORM schema does not hard-code one model dimension.
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeCanonicalEntityRecord(Base):
    """One corpus-bound canonical identity, separate from server runtime EntityV3."""

    __tablename__ = "knowledge_canonical_entities"
    __table_args__ = (
        UniqueConstraint(
            "corpus_id",
            "entity_type",
            "normalized_name",
            name="uq_knowledge_canonical_entity_identity",
        ),
        Index("ix_knowledge_canonical_entity_corpus_status", "corpus_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeRuntimeEntityResolutionRecord(Base):
    """Evidence-backed, revisable link from a scoped runtime EntityV3 to a corpus entity."""

    __tablename__ = "knowledge_runtime_entity_resolutions"
    __table_args__ = (
        Index(
            "ix_knowledge_runtime_entity_resolution_runtime_status",
            "runtime_entity_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_knowledge_runtime_entity_resolution_canonical",
            "canonical_entity_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    # No FK: Intelligence lifecycle deletes scoped EntityV3 rows independently.
    runtime_entity_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    canonical_entity_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_canonical_entities.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    authority_profile: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    supersedes_resolution_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    producer: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_model: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeExtractedAssertionRecord(Base):
    """Evidence-backed corpus interpretation; it is deliberately not a Character Belief."""

    __tablename__ = "knowledge_extracted_assertions"
    __table_args__ = (
        Index(
            "ix_knowledge_extracted_assertion_subject_predicate",
            "corpus_id",
            "subject_entity_id",
            "predicate",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    subject_entity_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_canonical_entities.id"), index=True, nullable=False
    )
    predicate: Mapped[str] = mapped_column(String(240), nullable=False)
    object_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_canonical_entities.id"), index=True
    )
    object_value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    qualifiers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    authority_profile: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    supersedes_assertion_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    producer: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_model: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeWorldEventRecord(Base):
    """Corpus/world event, intentionally separate from ConversationEpisodeV3."""

    __tablename__ = "knowledge_world_events"
    __table_args__ = (
        Index("ix_knowledge_world_event_corpus_status", "corpus_id", "status", "valid_from"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_canonical_entities.id"), index=True
    )
    ordering_key: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    outcome_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    authority_profile: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    producer: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_model: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeWorldEventParticipantRecord(Base):
    """A canonical entity's evidence-backed role in a corpus/world event."""

    __tablename__ = "knowledge_world_event_participants"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "canonical_entity_id",
            "participant_role",
            name="uq_knowledge_event_participant",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_world_events.id"), index=True, nullable=False
    )
    canonical_entity_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_canonical_entities.id"), index=True, nullable=False
    )
    participant_role: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEvidenceGraphRelationRecord(Base):
    """Corpus graph relation without changing server-runtime graph scope."""

    __tablename__ = "knowledge_evidence_graph_relations"
    __table_args__ = (
        UniqueConstraint(
            "corpus_id",
            "source_ref_type",
            "source_ref_id",
            "relation_type",
            "target_ref_type",
            "target_ref_id",
            "status",
            name="uq_knowledge_evidence_graph_relation",
        ),
        Index(
            "ix_knowledge_evidence_graph_relation_source",
            "corpus_id",
            "source_ref_type",
            "source_ref_id",
        ),
        Index(
            "ix_knowledge_evidence_graph_relation_target",
            "corpus_id",
            "target_ref_type",
            "target_ref_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    source_ref_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_ref_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    authority_profile: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    producer: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_model: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeInterpretationEvidenceRecord(Base):
    """Evidence-unit provenance for a Fabric interpretation or graph relation."""

    __tablename__ = "knowledge_interpretation_evidence"
    __table_args__ = (
        UniqueConstraint(
            "interpretation_type",
            "interpretation_id",
            "evidence_unit_id",
            "role",
            name="uq_knowledge_interpretation_evidence",
        ),
        Index(
            "ix_knowledge_interpretation_evidence_unit",
            "evidence_unit_id",
            "interpretation_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    interpretation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    interpretation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    evidence_unit_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_evidence_units.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(80), default="support", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeAccessGrantRecord(Base):
    """One enable/disable state for a grantee's access to a corpus."""

    __tablename__ = "knowledge_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "corpus_id",
            "grantee_type",
            "grantee_id",
            name="uq_knowledge_access_grant_grantee",
        ),
        Index(
            "ix_knowledge_grant_grantee_access",
            "grantee_type",
            "grantee_id",
            "enabled",
            "corpus_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    grantee_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    grantee_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    access_mode: Mapped[str] = mapped_column(String(24), default="read", nullable=False)
    policy_metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeOverlayPolicyRecord(Base):
    """Non-destructive, per-server precedence for one granted corpus."""

    __tablename__ = "knowledge_overlay_policies"
    __table_args__ = (
        UniqueConstraint(
            "server_scope_id",
            "corpus_id",
            name="uq_knowledge_overlay_policy_scope_corpus",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_scope_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_server_scopes.id"), index=True, nullable=False
    )
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeCharacterCorpusPolicyRecord(Base):
    """An authored Character admission decision after server/corpus authorization."""

    __tablename__ = "knowledge_character_corpus_policies"
    __table_args__ = (
        UniqueConstraint(
            "server_scope_id",
            "deployment_id",
            "character_card_id",
            "corpus_id",
            name="uq_knowledge_character_corpus_policy",
        ),
        Index(
            "ix_knowledge_character_corpus_policy_lookup",
            "deployment_id",
            "character_card_id",
            "corpus_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_scope_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_server_scopes.id"), index=True, nullable=False
    )
    # Deployment/Card lifecycle is independently owned by Runtime, so authoring validates their
    # current scope rather than introducing a cross-domain delete dependency.
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    corpus_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_corpora.id"), index=True, nullable=False
    )
    effect: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "KnowledgeAccessGrantRecord",
    "KnowledgeAssetReferenceRecord",
    "KnowledgeCanonicalBlockRecord",
    "KnowledgeCanonicalDocumentRecord",
    "KnowledgeCanonicalEntityRecord",
    "KnowledgeCanonicalSectionRecord",
    "KnowledgeCorpusRecord",
    "KnowledgeDependencyInvalidationRecord",
    "KnowledgeEvidenceEmbeddingRecord",
    "KnowledgeEvidenceGraphRelationRecord",
    "KnowledgeEvidenceRetrievalEntryRecord",
    "KnowledgeEvidenceUnitRecord",
    "KnowledgeExternalHostRateRecord",
    "KnowledgeExternalSourceScheduleRecord",
    "KnowledgeExternalSourceSyncStateRecord",
    "KnowledgeExtractedAssertionRecord",
    "KnowledgeIngestionCheckpointRecord",
    "KnowledgeIngestionJobRecord",
    "KnowledgeInterpretationEvidenceRecord",
    "KnowledgeObjectArtifactRecord",
    "KnowledgeOverlayPolicyRecord",
    "KnowledgeProjectionDependencyRecord",
    "KnowledgeProjectionRecord",
    "KnowledgeRuntimeEntityResolutionRecord",
    "KnowledgeServerAdministratorRecord",
    "KnowledgeServerScopeRecord",
    "KnowledgeSourceRecord",
    "KnowledgeSourceVersionRecord",
    "KnowledgeWorldEventParticipantRecord",
    "KnowledgeWorldEventRecord",
]
