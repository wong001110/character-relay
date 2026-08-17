"""User-controlled durable Character Core Memory records."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class CharacterCoreMemoryRecord(Base):
    """Explicit Saved/Core Memory separated from background-synthesized Memory vNext."""

    __tablename__ = "character_core_memories"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "character_card_id",
            "connection_id",
            "guild_id",
            "scope_type",
            "subject_user_id",
            "normalized_key",
            name="uq_character_core_memory_scope_key",
        ),
        Index(
            "ix_character_core_memory_scope",
            "owner_id",
            "character_card_id",
            "connection_id",
            "guild_id",
            "status",
            "priority",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, default="", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), index=True, default="character_global")
    subject_user_id: Mapped[str] = mapped_column(String(200), index=True, default="")
    memory_type: Mapped[str] = mapped_column(String(40), index=True, default="other")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(320), nullable=False)
    priority: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, default="active", nullable=False)
    source_memory_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["CharacterCoreMemoryRecord"]
