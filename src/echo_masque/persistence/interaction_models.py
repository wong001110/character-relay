"""Persistence models for Discord interaction sessions and Sticker semantics."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DiscordInteractionTemplateRecord(Base):
    """Reusable multi-character interaction rules scoped to one Discord Server."""

    __tablename__ = "discord_interaction_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    server_profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    template_type: Mapped[str] = mapped_column(String(32), default="roast", nullable=False)
    participant_character_card_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    rounds_per_trigger: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    maximum_triggers: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    intensity: Mapped[str] = mapped_column(String(24), default="playful", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordInteractionSessionRecord(Base):
    """One bounded multi-character interaction configured from the Portal."""

    __tablename__ = "discord_interaction_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    guild_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    category_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    target_user_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    target_display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    participant_deployment_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    session_type: Mapped[str] = mapped_column(String(32), default="roast", nullable=False)
    rounds_per_trigger: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    maximum_triggers: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completed_triggers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    intensity: Mapped[str] = mapped_column(String(24), default="playful", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="paused", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordInteractionRunRecord(Base):
    """Idempotent execution record for one triggering Discord message."""

    __tablename__ = "discord_interaction_runs"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "source_message_id",
            name="uq_discord_interaction_run_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stop_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscordStickerSemanticRecord(Base):
    """Observed Discord Sticker metadata with optional owner-confirmed semantics."""

    __tablename__ = "discord_sticker_semantics"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "sticker_id",
            name="uq_discord_sticker_semantic",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    sticker_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), default="Sticker", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    format_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    asset_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    semantic_intent: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    semantic_emotion: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    semantic_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    semantic_source: Mapped[str] = mapped_column(
        String(32), default="discord_metadata", nullable=False
    )
    semantic_confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
