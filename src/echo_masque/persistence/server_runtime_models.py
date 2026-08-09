"""Companion persistence for Discord Server runtime settings."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DiscordServerRuntimeRecord(Base):
    """Mutable runtime settings kept separate from legacy Server Profile rows."""

    __tablename__ = "discord_server_runtimes"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(120), default="UTC", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
