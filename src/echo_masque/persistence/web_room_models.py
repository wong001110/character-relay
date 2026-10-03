"""Explicit web-room publication, membership, owned profiles and at-most-once sends."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class WebRoomRecord(Base):
    __tablename__ = "web_rooms"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "guild_id", "channel_id", "thread_id", name="uq_web_room_destination"
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True)
    connection_id: Mapped[str] = mapped_column(String(64), index=True)
    guild_id: Mapped[str] = mapped_column(String(200))
    channel_id: Mapped[str] = mapped_column(String(200))
    thread_id: Mapped[str] = mapped_column(String(200), default="")
    name: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebRoomMemberRecord(Base):
    __tablename__ = "web_room_members"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    can_post: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_web_room_member"),)


class WebProfileRecord(Base):
    __tablename__ = "web_participant_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    avatar_url: Mapped[str] = mapped_column(String(1000), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)


class WebReactionRecord(Base):
    __tablename__ = "web_room_reactions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[str] = mapped_column(String(200), index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    emoji_key: Mapped[str] = mapped_column(String(240))
    emoji_name: Mapped[str] = mapped_column(String(160))
    emoji_id: Mapped[str] = mapped_column(String(200), default="")
    animated: Mapped[bool] = mapped_column(Boolean, default=False)
    asset_url: Mapped[str] = mapped_column(String(3000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "room_id", "message_id", "profile_id", "emoji_key",
            name="uq_web_room_reaction_profile",
        ),
    )


class WebOutboxRecord(Base):
    __tablename__ = "web_room_outbox"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True)
    profile_id: Mapped[str] = mapped_column(String(64))
    client_message_id: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    claim_nonce: Mapped[str] = mapped_column(String(64), default="")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discord_message_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    discord_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    webhook_id: Mapped[str] = mapped_column(String(200), default="")
    reason: Mapped[str] = mapped_column(String(80), default="")
    routing_status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    __table_args__ = (
        UniqueConstraint("owner_id", "client_message_id", name="uq_web_outbox_client"),
    )
