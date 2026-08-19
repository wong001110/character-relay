from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class SmartParticipationScopeStateRecord(Base):
    """Durable channel/thread admission window shared by all Connector replicas."""

    __tablename__ = "smart_participation_scope_states"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            name="uq_smart_participation_scope_state",
        ),
        Index(
            "ix_smart_participation_scope_activity",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "last_admitted_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(64), nullable=False)
    guild_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(128), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    last_admitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recent_deployment_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    window_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    window_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SmartParticipationDeploymentStateRecord(Base):
    """Durable per-deployment admission timestamp used for Character cooldowns."""

    __tablename__ = "smart_participation_deployment_states"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "deployment_id",
            name="uq_smart_participation_deployment_state",
        ),
        Index(
            "ix_smart_participation_deployment_activity",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "last_admitted_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(64), nullable=False)
    guild_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(128), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_admitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SmartParticipationReplyDecisionRecord(Base):
    """Persist the vNext Segment/Thread target chosen for one planned Character reply."""

    __tablename__ = "smart_participation_reply_decisions"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "guild_id",
            "source_message_id",
            "deployment_id",
            name="uq_smart_participation_reply_decision",
        ),
        Index(
            "ix_smart_participation_reply_decision_recent",
            "owner_id",
            "connection_id",
            "guild_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    burst_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    segment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    semantic_thread_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    guidance: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    plan_kind: Mapped[str] = mapped_column(String(24), default="speaker", nullable=False)
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolver_version: Mapped[str] = mapped_column(
        String(80), default="conversation-intelligence-vnext", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "SmartParticipationDeploymentStateRecord",
    "SmartParticipationReplyDecisionRecord",
    "SmartParticipationScopeStateRecord",
]
