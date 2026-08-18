"""Persisted opt-in daily rhythm for one Deployment Presence instance."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DeploymentPresenceRhythmRecord(Base):
    """Configuration plus the already-materialized local-day sleep schedule."""

    __tablename__ = "deployment_presence_rhythms"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)

    # Local wall-clock minutes from midnight. The first implementation models only a
    # primary overnight sleep window; browsing/leisure opportunities are added later.
    preferred_sleep_start_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    sleep_duration_min_minutes: Mapped[int] = mapped_column(Integer, default=420, nullable=False)
    sleep_duration_max_minutes: Mapped[int] = mapped_column(Integer, default=540, nullable=False)
    variation_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Materialized schedule evidence. Once generated for a local date/config version it is
    # reused across process restarts instead of rolling new pseudo-random offsets.
    schedule_local_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    schedule_timezone: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    scheduled_sleep_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_transition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    next_state: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    last_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_transition_reason: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["DeploymentPresenceRhythmRecord"]
