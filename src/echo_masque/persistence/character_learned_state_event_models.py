"""Append-only evidence history behind the aggregate Character Learned State read model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class CharacterLearnedStateEventRecord(Base):
    """One bounded evidence update with optional Discord scope for observation/replay."""

    __tablename__ = "character_learned_state_events"
    __table_args__ = (
        Index(
            "ix_learned_state_event_character_time",
            "owner_id",
            "character_card_id",
            "state_type",
            "recorded_at",
        ),
        Index(
            "ix_learned_state_event_server_time",
            "owner_id",
            "connection_id",
            "guild_id",
            "recorded_at",
        ),
        Index("ix_learned_state_event_state", "state_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    state_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    subject_key: Mapped[str] = mapped_column(String(240), nullable=False)

    connection_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), default="", index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    topic_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    delta: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    value_before: Mapped[float] = mapped_column(Float, nullable=False)
    value_after: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_before: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_after: Mapped[float] = mapped_column(Float, nullable=False)
    contradiction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_burst_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


__all__ = ["CharacterLearnedStateEventRecord"]
