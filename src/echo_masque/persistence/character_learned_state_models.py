from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class CharacterLearnedStateRecord(Base):
    """Derived, rebuildable Character social/participation state with explicit provenance."""

    __tablename__ = "character_learned_states"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "character_card_id",
            "state_type",
            "subject_type",
            "subject_key",
            name="uq_character_learned_state_subject",
        ),
        Index(
            "ix_character_learned_state_character_type_activity",
            "owner_id",
            "character_card_id",
            "state_type",
            "last_evidence_at",
        ),
        Index(
            "ix_character_learned_state_expiry",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    state_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    subject_key: Mapped[str] = mapped_column(String(240), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    positive_evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    negative_evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    half_life_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_evidence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["CharacterLearnedStateRecord"]
