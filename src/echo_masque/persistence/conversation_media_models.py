"""Conversation-scoped media perception references.

Unlike the global Media Analysis cache, these records intentionally include conversation and
Character scope. They record what a specific Character actually perceived so later replies can
rehydrate that perception without pretending unseen content became Character knowledge.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ConversationMediaReferenceRecord(Base):
    """Bounded objective context a Character perceived from one Discord source message."""

    __tablename__ = "conversation_media_references"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "character_card_id",
            "message_id",
            "source_key",
            name="uq_conversation_media_reference_identity",
        ),
        Index(
            "ix_conversation_media_scope_recent",
            "deployment_id",
            "character_card_id",
            "guild_id",
            "channel_id",
            "thread_id",
            "created_at",
        ),
        Index("ix_conversation_media_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    message_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_key: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    context_json: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
