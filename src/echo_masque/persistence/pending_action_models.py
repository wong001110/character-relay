"""Runtime-owned pending effects. No semantic Thread or Segment foreign key."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class PendingActionRecord(Base):
    """Standalone Tool action state linked to source evidence and optionally a Thread."""

    __tablename__ = "pending_actions"
    __table_args__ = (
        Index(
            "ix_pending_actions_scope_state",
            "owner_id",
            "connection_id",
            "guild_id",
            "channel_id",
            "discord_thread_id",
            "requested_by_user_id",
            "state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    discord_thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    target_character_card_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    deployment_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    tool_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    intent_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
