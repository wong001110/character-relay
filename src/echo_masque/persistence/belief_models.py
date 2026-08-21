"""Evidence-backed revisable Belief Store persistence for Intelligence Core v3."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class BeliefV3Record(Base):
    __tablename__ = "beliefs_v3"
    __table_args__ = (
        Index(
            "ix_beliefs_v3_subject_predicate",
            "owner_id",
            "connection_id",
            "guild_id",
            "subject_entity_id",
            "subject_ref",
            "predicate",
            "status",
        ),
        Index(
            "ix_beliefs_v3_character_scope",
            "owner_id",
            "character_card_id",
            "connection_id",
            "guild_id",
            "scope",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, default="", nullable=False)
    subject_entity_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(240), index=True, default="", nullable=False)
    predicate: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    value_text: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(40), default="server", index=True, nullable=False)
    authority_class: Mapped[str] = mapped_column(String(64), default="conversation", nullable=False)
    authority_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    origin: Mapped[str] = mapped_column(String(64), default="conversation", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="provisional", index=True, nullable=False)
    supersedes_belief_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    authored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BeliefEvidenceDependencyRecord(Base):
    __tablename__ = "belief_evidence_dependencies_v3"
    __table_args__ = (
        UniqueConstraint(
            "belief_id",
            "evidence_edge_id",
            name="uq_belief_evidence_dependency_v3",
        ),
        Index(
            "ix_belief_evidence_dependency_v3_edge",
            "owner_id",
            "evidence_edge_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    belief_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    evidence_edge_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BeliefRevisionEventRecord(Base):
    __tablename__ = "belief_revision_events_v3"
    __table_args__ = (
        Index(
            "ix_belief_revision_events_v3_subject",
            "owner_id",
            "subject_ref",
            "predicate",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    belief_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    previous_belief_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    predicate: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "BeliefEvidenceDependencyRecord",
    "BeliefRevisionEventRecord",
    "BeliefV3Record",
]
