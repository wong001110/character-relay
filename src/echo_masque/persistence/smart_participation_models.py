"""Persistence models for Smart Participation configuration, semantics, and feedback."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class SmartParticipationProfileRecord(Base):
    """One user-owned Smart Participation profile attached to a Character Card."""

    __tablename__ = "smart_participation_profiles"

    character_card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    style: Mapped[str] = mapped_column(String(24), default="balanced", nullable=False)
    group_role: Mapped[str] = mapped_column(
        String(24), default="independent", nullable=False
    )
    topics_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    trigger_phrases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    avoid_phrases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    preferred_follow_up_character_card_id: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )
    follow_up_window_seconds: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CharacterSemanticProfileRecord(Base):
    """Cached Character Card embedding used as a Smart Participation signal."""

    __tablename__ = "character_semantic_profiles"

    character_card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SmartParticipationFeedbackRecord(Base):
    """One explicit Playground label kept for later participation-judge evaluation."""

    __tablename__ = "smart_participation_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    previous_character_card_id: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )
    predicted_decision: Mapped[str] = mapped_column(String(24), nullable=False)
    predicted_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    minimum_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    signals_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    feedback_label: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
