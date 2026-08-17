"""Derived Episode projection over authoritative conversation messages/bursts."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationEpisodeRecord(Base):
    __tablename__ = "conversation_episodes"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "platform",
            "connection_id",
            "guild_id",
            "episode_key",
            name="uq_conversation_episode_projection",
        ),
        Index(
            "ix_conversation_episode_scope_time",
            "owner_id",
            "platform",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "ended_at",
        ),
        Index("ix_conversation_episode_topic", "owner_id", "topic_id", "ended_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    episode_key: Mapped[str] = mapped_column(String(120), nullable=False)
    topic_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    burst_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_message_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    participant_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    media_refs_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    key_points_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["ConversationEpisodeRecord"]
