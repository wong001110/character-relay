"""Canonical Character relationships and Deployment-scoped lived social state."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class CharacterRelationshipPriorRecord(Base):
    """Directional author-controlled relationship truth between two Character Cards."""

    __tablename__ = "character_relationship_priors"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "source_character_card_id",
            "target_character_card_id",
            name="uq_character_relationship_prior_direction",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source_character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), default="other", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    familiarity_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    affinity_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trust_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    comfort_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentRelationshipStateRecord(Base):
    """Directional lived social state from one Deployment toward one actor/Deployment."""

    __tablename__ = "deployment_relationship_states"
    __table_args__ = (
        UniqueConstraint(
            "source_deployment_id",
            "target_type",
            "target_key",
            name="uq_deployment_relationship_target",
        ),
        Index(
            "ix_deployment_relationship_owner_source",
            "owner_id",
            "source_deployment_id",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source_deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_key: Mapped[str] = mapped_column(String(200), nullable=False)
    familiarity_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    affinity_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trust_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    comfort_baseline: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    familiarity_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    affinity_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trust_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    comfort_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_evidence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    def __init__(self, **kwargs: object) -> None:
        # SQLAlchemy Column defaults are applied during INSERT, not while a new ORM
        # instance is still pending. Relationship evidence reads the deltas before
        # the first flush, so initialize them eagerly as part of the Python object.
        super().__init__(**kwargs)
        if self.familiarity_delta is None:
            self.familiarity_delta = 0.0
        if self.affinity_delta is None:
            self.affinity_delta = 0.0
        if self.trust_delta is None:
            self.trust_delta = 0.0
        if self.comfort_delta is None:
            self.comfort_delta = 0.0


class DeploymentRelationshipEventRecord(Base):
    """Append-only evidence for one dynamic relationship dimension."""

    __tablename__ = "deployment_relationship_events"
    __table_args__ = (
        Index(
            "ix_deployment_relationship_event_recent",
            "owner_id",
            "source_deployment_id",
            "target_key",
            "recorded_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source_deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_key: Mapped[str] = mapped_column(String(200), nullable=False)
    dimension: Mapped[str] = mapped_column(String(24), nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_burst_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CharacterPersonImpressionRecord(Base):
    """Evidence-grounded qualitative view one Deployment holds about one target."""

    __tablename__ = "character_person_impressions"
    __table_args__ = (
        UniqueConstraint(
            "source_deployment_id",
            "target_type",
            "target_key",
            name="uq_character_person_impression_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source_deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_key: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    observations_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "CharacterPersonImpressionRecord",
    "CharacterRelationshipPriorRecord",
    "DeploymentRelationshipEventRecord",
    "DeploymentRelationshipStateRecord",
]
