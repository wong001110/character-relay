"""Durable, transport-neutral records for asynchronous Discord turns."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class TurnJobRecord(Base):
    __tablename__ = "discord_turn_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    connection_id: Mapped[str] = mapped_column(String(64), index=True)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True)
    guild_id: Mapped[str] = mapped_column(String(200), default="")
    channel_id: Mapped[str] = mapped_column(String(200), default="")
    thread_id: Mapped[str] = mapped_column(String(200), default="")
    category_id: Mapped[str] = mapped_column(String(200), default="")
    source_message_id: Mapped[str] = mapped_column(String(200), default="")
    source_author_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    reply_json: Mapped[str] = mapped_column(Text, default="")
    social_step_json: Mapped[str] = mapped_column(Text, default="")
    runtime_step_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_notice_ack_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TurnJobProgressRecord(Base):
    __tablename__ = "discord_turn_job_progress"
    __table_args__ = (UniqueConstraint("job_id", "ordinal", name="uq_turn_job_progress_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String(500))
    claim_nonce: Mapped[str] = mapped_column(String(64), default="")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
