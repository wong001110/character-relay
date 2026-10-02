"""Web participants are authenticated principals; webhook names are presentation only."""

from __future__ import annotations

import ipaddress
import unicodedata
from datetime import datetime
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from echo_masque.room_routing import RoomScope


class WebRoomError(ValueError):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.status = status


def public_avatar(value: str) -> str:
    """Validate image URL syntax without fetching it or attaching session credentials."""
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or not host
        or parts.username
        or parts.password
        or parts.fragment
        or parts.port not in (None, 443)
        or any(ord(c) < 33 for c in value)
        or "\\" in value
        or "." not in host
        or host.endswith((".localhost", ".local", ".internal", ".invalid"))
    ):
        raise ValueError("avatar_requires_public_https_url")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("avatar_requires_public_https_url")
    return value


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    display_name: str = Field(min_length=1, max_length=80)
    avatar_url: str = Field(default="", max_length=1000)

    @field_validator("display_name")
    @classmethod
    def name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(unicodedata.category(c) in {"Cc", "Cf"} for c in value):
            raise ValueError("invalid_display_name")
        return value

    @field_validator("avatar_url")
    @classmethod
    def avatar(cls, value: str) -> str:
        return public_avatar(value)


class ProfileUpdate(ProfileInput):
    expected_version: int = Field(ge=1)


class ProfileView(ProfileInput):
    id: str
    version: int


class WebRoomInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    name: str = Field(min_length=1, max_length=80)


class WebRoomView(WebRoomInput):
    id: str
    enabled: bool
    can_manage: bool
    can_post: bool


class MembershipInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=120)
    can_post: bool = True


class WebSend(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile_id: str = Field(min_length=1, max_length=64)
    client_message_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=1800)
    reply_to_message_id: str = Field(default="", max_length=200)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if len(value.encode("utf-16-le")) // 2 > 1800:
            raise ValueError("message_too_long")
        if not value.strip():
            raise ValueError("empty_message")
        return value


class WebDeliveryView(BaseModel):
    id: str
    client_message_id: str
    profile_id: str
    display_name: str
    avatar_url: str
    text: str
    reply_to_message_id: str
    status: Literal["pending", "claimed", "delivered", "failed", "uncertain", "cancelled"]
    discord_message_id: str
    reason: str
    created_at: datetime
    routing_status: str


class WebRoomDelivery(WebDeliveryView):
    """Connector-only claim; never returned to a browser."""

    room_id: str
    claim_nonce: str
    guild_id: str
    channel_id: str
    thread_id: str
    webhook_id: str
    actor_id: str


class RoomLocationRecord(Protocol):
    owner_id: str
    connection_id: str
    guild_id: str
    channel_id: str
    thread_id: str


def room_scope(record: RoomLocationRecord) -> RoomScope:
    # Callers use WebRoomRecord; importing persistence here would couple domain contracts to SQL.
    return RoomScope.model_validate(
        {
            "owner_id": record.owner_id,
            "connection_id": record.connection_id,
            "guild_id": record.guild_id,
            "channel_id": record.channel_id,
            "thread_id": record.thread_id,
        }
    )
