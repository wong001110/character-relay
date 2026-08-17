"""Bounded observation records for Topic continuity/lifecycle decisions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationTopicDecisionRecord(Base):
    """One privacy-bounded Topic routing decision; raw message text is never stored here."""

    __tablename__ = "conversation_topic_decisions"
    __table_args__ = (
        Index(
            "ix_topic_decision_scope_created",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "created_at",
        ),
        Index("ix_topic_decision_message", "owner_id", "message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(40), default="discord", nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    message_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    from_topic_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    to_topic_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    dense_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sparse_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    continuation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    switch_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    candidate_dense_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    candidate_sparse_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


__all__ = ["ConversationTopicDecisionRecord"]
