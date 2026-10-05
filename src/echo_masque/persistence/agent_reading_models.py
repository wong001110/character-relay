"""Participant-scoped progress and immutable batch references, without transcript copies."""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base


class AgentReadingCursorRecord(Base):
    __tablename__ = "web_room_agent_reading_cursors"
    __table_args__ = (
        UniqueConstraint("user_id", "room_id", "profile_id", name="uq_agent_reading_scope"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("web_rooms.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("web_participant_profiles.id", ondelete="CASCADE"), index=True
    )
    cursor_revision: Mapped[int] = mapped_column(Integer, default=0)
    gap_generation: Mapped[int] = mapped_column(Integer, default=1)
    completed_gap_generation: Mapped[int] = mapped_column(Integer, default=0)
    last_gap_event_id: Mapped[str] = mapped_column(String(64), default="")
    batch_id: Mapped[str] = mapped_column(String(64), default="")
    batch_from_revision: Mapped[int] = mapped_column(Integer, default=0)
    batch_to_revision: Mapped[int] = mapped_column(Integer, default=0)
    batch_gap_generation: Mapped[int] = mapped_column(Integer, default=0)
    batch_needs_reread: Mapped[int] = mapped_column(Integer, default=0)
    batch_references_json: Mapped[str] = mapped_column(Text, default="[]")
    last_completed_batch_id: Mapped[str] = mapped_column(String(64), default="")
