"""Persistent system notices emitted by Deployment Presence authority."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DeploymentPresenceNoticeRecord(Base):
    """One Bot-account status notice request, never a Character webhook message."""

    __tablename__ = "deployment_presence_notices"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "source_message_id",
            "notice_type",
            name="uq_deployment_presence_notice_source",
        ),
        Index(
            "ix_deployment_presence_notice_due",
            "status",
            "available_at",
            "created_at",
        ),
        Index(
            "ix_deployment_presence_notice_cooldown",
            "deployment_id",
            "channel_id",
            "thread_id",
            "notice_type",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    notice_type: Mapped[str] = mapped_column(String(40), nullable=False)
    character_display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["DeploymentPresenceNoticeRecord"]
