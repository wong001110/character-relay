"""Persistence for Burst segments and non-exclusive Semantic Threads."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class SemanticThreadRecord(Base):
    """One durable discussion line; multiple Threads may be concurrently active in a scope."""

    __tablename__ = "semantic_threads"
    __table_args__ = (
        Index(
            "ix_semantic_threads_scope_activity",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "discord_thread_id",
            "status",
            "last_active_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(24), default="discord", nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    label: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="hot", index=True, nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConversationSegmentRecord(Base):
    """One semantic/conversational unit projected from a temporal Conversation Burst."""

    __tablename__ = "conversation_segments"
    __table_args__ = (
        UniqueConstraint("owner_id", "burst_id", "segment_key", name="uq_segment_owner_burst_key"),
        Index(
            "ix_conversation_segments_scope_recent",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "discord_thread_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    burst_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    segment_key: Mapped[str] = mapped_column(String(120), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    message_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    participant_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="discussion", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    semantic_thread_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    thread_action: Mapped[str] = mapped_column(String(32), default="create", nullable=False)
    thread_evidence: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="deterministic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = ["ConversationSegmentRecord", "SemanticThreadRecord"]
