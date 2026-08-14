from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
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


__all__ = ["SmartParticipationDeploymentStateRecord", "SmartParticipationScopeStateRecord"]
