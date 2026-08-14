"""Durable scoped conversation memory for Utility Intelligence."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationMemoryRecord(Base):
    __tablename__ = "conversation_memory_v2"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    platform: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(120), index=True, default="")
    guild_id: Mapped[str] = mapped_column(String(120), index=True, default="")
    channel_id: Mapped[str] = mapped_column(String(120), index=True, default="")
    thread_id: Mapped[str] = mapped_column(String(120), index=True, default="")
    subject_user_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, default="active")
    source_message_id: Mapped[str] = mapped_column(String(200), default="")
    source_topic_id: Mapped[str] = mapped_column(String(36), default="")
    supersedes_memory_id: Mapped[str] = mapped_column(String(36), default="")
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
