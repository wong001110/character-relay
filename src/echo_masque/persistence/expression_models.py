"""Persistence models for Server expression resources and workflow state."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DiscordExpressionSemanticRecord(Base):
    """One Server Emoji or Sticker with owner-confirmed semantic metadata."""

    __tablename__ = "discord_expression_semantics"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "resource_type",
            "resource_id",
            name="uq_discord_expression_semantic",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    situations_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    avoid_when_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    allowed_actions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    format_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    asset_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    animated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    semantic_intent: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    semantic_emotion: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    semantic_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    semantic_source: Mapped[str] = mapped_column(
        String(32), default="discord_metadata", nullable=False
    )
    semantic_confidence: Mapped[float] = mapped_column(Float, default=0.35, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordExpressionRunRecord(Base):
    """Durable state for one character expression decision workflow."""

    __tablename__ = "discord_expression_runs"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "source_message_id",
            "deployment_id",
            name="uq_discord_expression_run_trigger",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    current_node: Mapped[str] = mapped_column(
        String(80), default="filter_resources", nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    selected_action: Mapped[str] = mapped_column(String(24), default="none", nullable=False)
    selected_resource_key: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    state_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscordExpressionNodeRecord(Base):
    """One persisted node transition within an expression workflow run."""

    __tablename__ = "discord_expression_nodes"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "node_index",
            name="uq_discord_expression_node_index",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    node_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    node_index: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    input_summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
