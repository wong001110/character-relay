"""Sidecar models for Core revisions, synthesized freshness, and Memory summaries."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class CharacterCoreMemoryRevisionRecord(Base):
    __tablename__ = "character_core_memory_revisions"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "core_memory_id",
            "revision_no",
            name="uq_core_memory_revision_number",
        ),
        Index(
            "ix_core_memory_revision_history",
            "owner_id",
            "core_memory_id",
            "revision_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    core_memory_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_user_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_memory_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SynthesizedMemoryFreshnessRecord(Base):
    __tablename__ = "synthesized_memory_freshness"

    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    freshness_status: Mapped[str] = mapped_column(String(24), index=True, default="fresh")
    stale_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CharacterMemorySummaryRecord(Base):
    __tablename__ = "character_memory_summaries"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "character_card_id",
            "connection_id",
            "guild_id",
            "version",
            name="uq_character_memory_summary_version",
        ),
        Index(
            "ix_character_memory_summary_scope",
            "owner_id",
            "character_card_id",
            "connection_id",
            "guild_id",
            "version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_core_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_memory_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "CharacterCoreMemoryRevisionRecord",
    "CharacterMemorySummaryRecord",
    "SynthesizedMemoryFreshnessRecord",
]
