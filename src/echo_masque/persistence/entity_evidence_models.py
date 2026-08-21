"""Canonical/provisional Entity and evidence graph persistence for Intelligence Core v3."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class EntityV3Record(Base):
    """Server-scoped identity that may remain provisional without hallucinating details."""

    __tablename__ = "entities_v3"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "entity_type",
            "normalized_name",
            name="uq_entities_v3_scope_type_name",
        ),
        Index(
            "ix_entities_v3_scope_status",
            "owner_id",
            "connection_id",
            "guild_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        String(64), index=True, default="", nullable=False
    )
    guild_id: Mapped[str] = mapped_column(
        String(200), index=True, default="", nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(320), nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="provisional", index=True, nullable=False
    )
    merged_into_entity_id: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EvidenceEdgeV3Record(Base):
    """Typed provenance edge; interpretation never duplicates the truth store."""

    __tablename__ = "evidence_edges_v3"
    __table_args__ = (
        Index(
            "ix_evidence_edges_v3_source",
            "owner_id",
            "source_ref_type",
            "source_ref",
            "relation_type",
            "status",
        ),
        Index(
            "ix_evidence_edges_v3_target",
            "owner_id",
            "target_ref_type",
            "target_ref",
            "relation_type",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        String(64), index=True, default="", nullable=False
    )
    guild_id: Mapped[str] = mapped_column(
        String(200), index=True, default="", nullable=False
    )
    source_ref_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(320), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    target_ref_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    authority_class: Mapped[str] = mapped_column(
        String(48), default="conversation", nullable=False
    )
    source_kind: Mapped[str] = mapped_column(
        String(48), default="runtime", nullable=False
    )
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="active", index=True, nullable=False
    )
    supersedes_edge_id: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )
    producer: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_model: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeGapRecord(Base):
    """Missing entity knowledge that can optionally trigger existing Discovery."""

    __tablename__ = "knowledge_gaps_v3"
    __table_args__ = (
        Index(
            "ix_knowledge_gaps_v3_scope_state",
            "owner_id",
            "connection_id",
            "guild_id",
            "resolution_state",
            "importance",
            "updated_at",
        ),
        Index(
            "ix_knowledge_gaps_v3_entity",
            "owner_id",
            "entity_id",
            "resolution_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        String(64), index=True, default="", nullable=False
    )
    guild_id: Mapped[str] = mapped_column(
        String(200), index=True, default="", nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    missing_fields_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    triggered_by_ref: Mapped[str] = mapped_column(
        String(320), default="", nullable=False
    )
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    resolution_state: Mapped[str] = mapped_column(
        String(32), default="unresolved", index=True, nullable=False
    )
    possible_sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    discovery_requested: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    resolution_evidence_refs_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "EntityV3Record",
    "EvidenceEdgeV3Record",
    "KnowledgeGapRecord",
]
