"""Persisted Deployment activity sessions and per-item browsing evidence."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DeploymentActivitySessionRecord(Base):
    """One bounded lived activity session for a Deployment runtime instance."""

    __tablename__ = "deployment_activity_sessions"
    __table_args__ = (
        UniqueConstraint("schedule_key", name="uq_deployment_activity_schedule_key"),
        Index(
            "ix_deployment_activity_session_due",
            "status",
            "scheduled_start_at",
            "latest_start_at",
        ),
        Index(
            "ix_deployment_activity_session_recent",
            "owner_id",
            "deployment_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    activity_type: Mapped[str] = mapped_column(
        String(40), default="discovery_browsing", nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="scheduled", index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="scheduler", nullable=False)
    schedule_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    local_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    schedule_timezone: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latest_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate_budget: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    open_budget: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    watch_budget: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    share_intent_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exploration_percent: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notice_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    watch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentActivitySessionItemRecord(Base):
    """Observed candidate evidence inside one Deployment browsing session."""

    __tablename__ = "deployment_activity_session_items"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "discovery_item_id",
            name="uq_deployment_activity_session_item",
        ),
        Index(
            "ix_deployment_activity_session_item_rank",
            "session_id",
            "rank_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    discovery_item_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    attention_level: Mapped[str] = mapped_column(String(24), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "DeploymentActivitySessionItemRecord",
    "DeploymentActivitySessionRecord",
]
