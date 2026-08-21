"""Durable Discovery sharing policy and outbox persistence."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DeploymentDiscoverySharePolicyRecord(Base):
    __tablename__ = "deployment_discovery_share_policies"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    auto_share_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_share_budget: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    share_cooldown_minutes: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentDiscoveryShareRecord(Base):
    __tablename__ = "deployment_discovery_shares"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "discovery_item_id",
            name="uq_deployment_discovery_share_item",
        ),
        Index("ix_discovery_share_status_due", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    discovery_item_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_decision_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    mode: Mapped[str] = mapped_column(String(24), default="review", nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    motivation: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    conversation_thread_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    relationship_subject_key: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    draft_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    discord_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["DeploymentDiscoverySharePolicyRecord", "DeploymentDiscoveryShareRecord"]
