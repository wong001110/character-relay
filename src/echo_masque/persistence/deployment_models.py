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


class DiscordServerCatalogRecord(Base):
    """Latest Discord guild and channel inventory observed by a connector."""

    __tablename__ = "discord_server_catalogs"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "guild_id",
            name="uq_discord_server_catalog_connection_guild",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    guild_name: Mapped[str] = mapped_column(String(160), nullable=False)
    channels_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordServerProfileRecord(Base):
    """Reusable owner-defined settings for one Discord server."""

    __tablename__ = "discord_server_profiles"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            name="uq_discord_server_profile_connection_guild",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    guild_name: Mapped[str] = mapped_column(String(160), nullable=False)
    channel_scope_mode: Mapped[str] = mapped_column(
        String(24), default="all_except", nullable=False
    )
    excluded_channel_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    excluded_category_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    thread_policy: Mapped[str] = mapped_column(
        String(24), default="inherit_parent", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CharacterDeploymentRecord(Base):
    """One character version assigned to one concrete or server-wide destination."""

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


class DeploymentToolProfileRecord(Base):
    """Tools explicitly assigned to one Character Deployment."""

    __tablename__ = "deployment_tool_profiles"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    enabled_tools_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordDeploymentScopeRecord(Base):
    """Optional server-wide Discord scope attached to a deployment.

    Keeping this in a separate table preserves compatibility with existing SQLite
    databases whose character_deployments table predates server profiles.
    """

    __tablename__ = "discord_deployment_scopes"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    server_profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    channel_scope_mode: Mapped[str] = mapped_column(
        String(24), default="all_except", nullable=False
    )
    excluded_channel_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    excluded_category_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordConnectorEventRecord(Base):
    """Privacy-safe event emitted by the Discord Gateway connector."""

    __tablename__ = "discord_connector_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    level: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, default="", nullable=False)
    guild_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    channel_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    thread_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(
        String(200), index=True, default="", nullable=False
    )
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    character_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
