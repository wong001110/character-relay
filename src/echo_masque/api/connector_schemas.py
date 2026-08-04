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
DiscordIdentityMode = Literal["bot", "webhook"]
DiscordWebhookStatus = Literal["pending", "active", "error", "not_required"]
DiscordChannelScopeMode = Literal["exact", "all_except"]


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
    category_id: str = ""
    server_profile_id: str = ""
    channel_scope_mode: DiscordChannelScopeMode = "exact"
    excluded_channel_ids: list[str] = Field(default_factory=list)
    excluded_category_ids: list[str] = Field(default_factory=list)
    participation_mode: DiscordParticipationMode
    version_label: str
    status: Literal["active"]
    identity_mode: DiscordIdentityMode = "webhook"
    identity_display_name: str
    identity_avatar_url: str = ""
    webhook_status: DiscordWebhookStatus = "pending"
    webhook_id: str | None = None
    webhook_token: str | None = None


class DiscordCatalogChannel(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    category_id: str = Field(default="", max_length=200)
    category_name: str = Field(default="", max_length=160)
    type: str = Field(default="text", max_length=40)


class DiscordCatalogServer(BaseModel):
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(min_length=1, max_length=160)
    channels: list[DiscordCatalogChannel] = Field(default_factory=list, max_length=1000)


class DiscordServerCatalogSync(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    servers: list[DiscordCatalogServer] = Field(default_factory=list, max_length=200)


class DiscordWebhookRegistration(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    deployment_id: str = Field(min_length=1, max_length=64)
    workspace_id: str = Field(default="", max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    category_id: str = Field(default="", max_length=200)
    webhook_id: str = Field(min_length=1, max_length=200)
    webhook_token: str = Field(min_length=1, max_length=500)


class DiscordWebhookRegistrationView(BaseModel):
    binding_id: str
    webhook_id: str
    webhook_token: str
    status: Literal["active"] = "active"


class DiscordWebhookStatusReport(BaseModel):
    deployment_id: str = Field(min_length=1, max_length=64)
    status: DiscordWebhookStatus
    last_error: str = Field(default="", max_length=2000)


class DiscordMessageRouteRegistration(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    deployment_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(default="", max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    webhook_id: str = Field(default="", max_length=200)
    message_ids: list[str] = Field(min_length=1, max_length=20)


class DiscordMessageRouteView(BaseModel):
    message_id: str
    deployment_id: str
    character_card_id: str
    channel_id: str
    thread_id: str


class DiscordMessageRouteLookup(BaseModel):
    route: DiscordMessageRouteView | None = None


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
    deployment_id: str = Field(min_length=1, max_length=64)
    message_id: str = Field(min_length=1, max_length=200)
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(default="", max_length=160)
    channel_id: str = Field(min_length=1, max_length=200)
    channel_name: str = Field(default="", max_length=160)
    category_id: str = Field(default="", max_length=200)
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
