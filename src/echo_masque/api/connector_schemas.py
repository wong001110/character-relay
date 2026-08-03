"""Internal schemas used by managed and local platform connectors."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DiscordParticipationMode = Literal[
    "mention_only",
    "reply_only",
    "mention_and_reply",
    "smart",
]
DiscordConnectionStatus = Literal["connected", "offline", "error"]


class DiscordConnectorDeploymentView(BaseModel):
    deployment_id: str
    connection_id: str
    character_card_id: str
    character_display_name: str
    workspace_id: str
    workspace_name: str
    channel_id: str
    channel_name: str
    thread_id: str
    thread_name: str
    participation_mode: DiscordParticipationMode
    version_label: str
    status: Literal["active"]


class DiscordConnectorHeartbeat(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    bot_user_id: str = Field(min_length=1, max_length=200)
    bot_display_name: str = Field(min_length=1, max_length=120)
    status: DiscordConnectionStatus = "connected"
    last_error: str = Field(default="", max_length=2000)


class DiscordContextMessage(BaseModel):
    message_id: str = Field(min_length=1, max_length=200)
    author_id: str = Field(min_length=1, max_length=200)
    author_display_name: str = Field(min_length=1, max_length=160)
    text: str = Field(default="", max_length=10000)
    created_at: datetime | None = None
    is_bot: bool = False


class DiscordInboundMessage(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    message_id: str = Field(min_length=1, max_length=200)
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(default="", max_length=160)
    channel_id: str = Field(min_length=1, max_length=200)
    channel_name: str = Field(default="", max_length=160)
    thread_id: str = Field(default="", max_length=200)
    thread_name: str = Field(default="", max_length=160)
    author_id: str = Field(min_length=1, max_length=200)
    author_display_name: str = Field(min_length=1, max_length=160)
    text: str = Field(default="", max_length=10000)
    mentioned_bot: bool = False
    replied_to_bot: bool = False
    smart_candidate: bool = False
    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)


class DiscordConnectorReplyView(BaseModel):
    action: Literal["silent", "reply"]
    reason: str
    deployment_id: str | None = None
    character_display_name: str | None = None
    text: str | None = None
    reply_to_message_id: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
