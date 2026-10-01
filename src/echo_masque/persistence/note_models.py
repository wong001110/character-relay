"""Small explicit character notes. No numerical relationship or automatic extraction state."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class CharacterNoteRecord(Base):
    __tablename__ = "character_notes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # Empty only for deliberately authored character background, never a member write.
    scope_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    scope_json: Mapped[str] = mapped_column(Text, default="", nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(220), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    authored: Mapped[bool] = mapped_column(Boolean, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    source_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NoteCreationReceiptRecord(Base):
    """Content-free command deduplication survives forgetting; never prompt memory."""

    __tablename__ = "note_creation_receipts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
