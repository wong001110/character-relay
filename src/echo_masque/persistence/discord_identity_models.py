"""Persistence models for Discord identities, webhooks, and reply routing."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
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
    webhook_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentMessageAliasRecord(Base):
    """Explicit names that may address one deployed character."""

    __tablename__ = "deployment_message_aliases"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordGuildActorIdentityRecord(Base):
    """Last observed presentation for one Discord member inside one guild.

    Relationship authority continues to use the stable Discord user id. This row is only a
    presentation cache so nickname/avatar changes never split learned social state.
    """

    __tablename__ = "discord_guild_actor_identities"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "user_id",
            name="uq_discord_guild_actor_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    guild_display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    global_display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    username: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    avatar_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
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


class DiscordMessageRouteRecord(Base):
    """Persist which Character Deployment authored one outgoing Discord message."""

    __tablename__ = "discord_message_routes"

    message_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    webhook_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
