"""Persistence models for platform connections and character deployments."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class PlatformConnectionRecord(Base):
    """One user-owned platform account or local connector session."""

    __tablename__ = "platform_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    connection_mode: Mapped[str] = mapped_column(String(24), default="managed", nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="disconnected", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CharacterDeploymentRecord(Base):
    """One character version assigned to one concrete chat destination."""

    __tablename__ = "character_deployments"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "channel_id",
            "thread_id",
            "character_card_id",
            name="uq_character_deployment_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    workspace_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(160), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    thread_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    participation_mode: Mapped[str] = mapped_column(
        String(32), default="mention_and_reply", nullable=False
    )
    memory_scope: Mapped[str] = mapped_column(
        String(32), default="channel_isolated", nullable=False
    )
    version_label: Mapped[str] = mapped_column(String(80), default="Current", nullable=False)
    sticker_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="paused", nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
