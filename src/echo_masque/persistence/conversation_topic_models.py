"""Persistence model for bounded conversation topic memory."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationTopicRecord(Base):
    """One bounded topic capsule for an exact platform conversation scope."""

    __tablename__ = "conversation_topics"
    __table_args__ = (
        Index(
            "ix_conversation_topics_scope_status",
            "owner_id",
            "platform",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "status",
            "last_active_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    topic_label: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    open_loops_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    pending_actions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    participants_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capsule_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["ConversationTopicRecord"]
