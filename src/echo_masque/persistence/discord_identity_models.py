"""Persistence models for per-deployment Discord identity and channel webhooks."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DeploymentMessageIdentityRecord(Base):
    """Presentation identity used when one deployment sends a chat message."""

    __tablename__ = "deployment_message_identities"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(24), default="webhook", nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    avatar_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    webhook_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordWebhookBindingRecord(Base):
    """One encrypted incoming-webhook binding shared by a Discord parent channel."""

    __tablename__ = "discord_webhook_bindings"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "channel_id",
            name="uq_discord_webhook_channel",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False)
    webhook_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
