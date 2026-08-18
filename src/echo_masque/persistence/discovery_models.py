"""Shared external content plus Deployment-scoped Discovery experience records."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DiscoveryItemRecord(Base):
    """Objective public candidate shared across Deployments by canonical source identity."""

    __tablename__ = "discovery_items"
    __table_args__ = (
        UniqueConstraint("source", "canonical_key", name="uq_discovery_item_source_key"),
        Index("ix_discovery_item_freshness", "source", "expires_at", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_kind: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creator: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentDiscoveryProfileRecord(Base):
    """Owner-controlled Discovery rollout mode for one Deployment incarnation."""

    __tablename__ = "deployment_discovery_profiles"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(24), default="off", index=True, nullable=False)
    youtube_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bilibili_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentDiscoveryExposureRecord(Base):
    """Subjective evidence that one Deployment actually encountered an external item."""

    __tablename__ = "deployment_discovery_exposures"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "discovery_item_id",
            name="uq_deployment_discovery_exposure",
        ),
        Index(
            "ix_deployment_discovery_exposure_recent",
            "owner_id",
            "deployment_id",
            "last_exposed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    discovery_item_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    attention_level: Mapped[str] = mapped_column(String(24), default="notice", nullable=False)
    interest_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    subjective_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    exposure_count: Mapped[int] = mapped_column(default=1, nullable=False)
    first_exposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_exposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentDiscoveryDecisionRecord(Base):
    """Append-only subjective decision evidence for one Deployment and Discovery item."""

    __tablename__ = "deployment_discovery_decisions"
    __table_args__ = (
        Index(
            "ix_deployment_discovery_decision_recent",
            "owner_id",
            "deployment_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    discovery_item_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    motivation: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    scores_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "DeploymentDiscoveryDecisionRecord",
    "DeploymentDiscoveryExposureRecord",
    "DeploymentDiscoveryProfileRecord",
    "DiscoveryItemRecord",
]
