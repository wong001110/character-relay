"""Evidence-grounded SocialEvent and versioned Impression persistence for Intelligence Core v3."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class SocialEventV3Record(Base):
    __tablename__ = "social_events_v3"
    __table_args__ = (
        Index(
            "ix_social_events_v3_target_time",
            "owner_id",
            "source_deployment_id",
            "target_type",
            "target_key",
            "status",
            "created_at",
        ),
        Index(
            "ix_social_events_v3_evidence",
            "owner_id",
            "source_relation_id",
            "source_segment_id",
            "source_episode_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source_deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_key: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    familiarity_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    affinity_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trust_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    comfort_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source_relation_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_segment_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_episode_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_message_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ImpressionV3Record(Base):
    __tablename__ = "impressions_v3"
    __table_args__ = (
        Index(
            "ix_impressions_v3_target",
            "owner_id",
            "source_deployment_id",
            "target_type",
            "target_key",
            "status",
            "updated_at",
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
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    supersedes_impression_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["ImpressionV3Record", "SocialEventV3Record"]
