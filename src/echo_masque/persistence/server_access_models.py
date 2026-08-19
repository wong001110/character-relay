"""Persistence models for account access to Super Admin-managed Discord servers."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DiscordServerJoinConfigRecord(Base):
    """Join-code configuration for one Discord server exposed by the managed connector."""

    __tablename__ = "discord_server_join_configs"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "guild_id",
            name="uq_discord_server_join_config_connection_guild",
        ),
        UniqueConstraint("join_code", name="uq_discord_server_join_config_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    join_code: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    join_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordServerAccessRecord(Base):
    """Account-to-server access granted by a join code or the Super Admin."""

    __tablename__ = "discord_server_access"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "connection_id",
            "guild_id",
            name="uq_discord_server_access_user_connection_guild",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    access_source: Mapped[str] = mapped_column(String(24), default="join_code", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
