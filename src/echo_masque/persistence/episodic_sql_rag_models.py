"""SQL event/entity incidence and Character episode-access records for episodic retrieval."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationEntityRecord(Base):
    __tablename__ = "conversation_entities"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "entity_type",
            "canonical_key",
            name="uq_conversation_entity_scope_key",
        ),
        Index(
            "ix_conversation_entity_lookup",
            "owner_id",
            "connection_id",
            "guild_id",
            "entity_type",
            "canonical_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(320), nullable=False)
    label: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="deterministic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConversationEpisodeEntityRecord(Base):
    __tablename__ = "conversation_episode_entities"
    __table_args__ = (
        UniqueConstraint("episode_id", "entity_id", name="uq_episode_entity_incidence"),
        Index("ix_episode_entity_episode", "owner_id", "episode_id"),
        Index("ix_episode_entity_entity", "owner_id", "entity_id", "episode_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    episode_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="deterministic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CharacterEpisodeAccessRecord(Base):
    """Evidence that one Character was allowed to perceive/use one Episode."""

    __tablename__ = "character_episode_access"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "character_card_id",
            "episode_id",
            name="uq_character_episode_access",
        ),
        Index(
            "ix_character_episode_access_lookup",
            "owner_id",
            "character_card_id",
            "episode_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    episode_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    access_reason: Mapped[str] = mapped_column(String(60), default="runtime_context", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "CharacterEpisodeAccessRecord",
    "ConversationEntityRecord",
    "ConversationEpisodeEntityRecord",
]
