"""Durable device flow and narrowly scoped grants, separate from login sessions."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base


class CliGrantRecord(Base):
    __tablename__ = "cli_readonly_grants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    client_id: Mapped[str] = mapped_column(String(80))
    scopes_json: Mapped[str] = mapped_column(Text)
    room_ids_json: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CliDeviceRecord(Base):
    __tablename__ = "cli_device_authorizations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    client_id: Mapped[str] = mapped_column(String(80))
    scopes_json: Mapped[str] = mapped_column(Text)
    room_ids_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    reviewing_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    grant_id: Mapped[str | None] = mapped_column(
        ForeignKey("cli_readonly_grants.id"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval: Mapped[int] = mapped_column(Integer, default=5)
    poll_version: Mapped[int] = mapped_column(Integer, default=0)
