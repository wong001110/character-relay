"""Server-isolated durable Memory vNext records."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationMemoryVNextRecord(Base):
    __tablename__ = "conversation_memory_vnext"
    __table_args__ = (
        Index(
            "ix_memory_vnext_scope",
            "owner_id",
            "character_card_id",
            "connection_id",
            "guild_id",
            "scope_type",
            "subject_user_id",
            "status",
        ),
        Index("ix_memory_vnext_topic", "owner_id", "guild_id", "topic_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    subject_user_id: Mapped[str] = mapped_column(String(200), index=True, default="")
    topic_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    memory_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, default="active")
    provenance_episode_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_message_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    supersedes_memory_id: Mapped[str] = mapped_column(String(36), default="")
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryVNextStateRecord(Base):
    __tablename__ = "memory_vnext_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    legacy_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["ConversationMemoryVNextRecord", "MemoryVNextStateRecord"]
