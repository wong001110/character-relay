"""Minimal room evidence, selection and explicit note storage; no cognitive graph."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class RoomStateRecord(Base):
    __tablename__ = "room_states"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    readable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permission_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoomSourceRecord(Base):
    __tablename__ = "room_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    room_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoomSelectionRecord(Base):
    __tablename__ = "room_selections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    requester_id: Mapped[str] = mapped_column(String(200), nullable=False)
    requester_is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    target_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    origin: Mapped[str] = mapped_column(String(24), nullable=False)
    focus_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoomRouteRecord(Base):
    """One idempotent, bounded room decision; metadata only, not a prompt archive."""

    __tablename__ = "room_routes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(200), nullable=False)
    optional: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="in_progress", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoomDeliverySourceRecord(Base):
    """Confirmed Discord IDs linked to the persisted generation's actual source.

    This is destination-scoped evidence, not an invitation or a tool authorization.
    The same public room may be observed by roles owned by different users.
    """

    __tablename__ = "room_delivery_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    message_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    target_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    step_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelAttemptBucketRecord(Base):
    __tablename__ = "room_model_attempt_buckets"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
