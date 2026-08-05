"""Persistent diagnostic events reported by platform connectors."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DeploymentLogRecord(Base):
    """One privacy-safe connector or character-runtime diagnostic event."""

    __tablename__ = "deployment_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    platform: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    level: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(200), index=True, default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
