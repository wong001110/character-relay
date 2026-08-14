"""Internal schemas used by managed and local platform connectors."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.expression_schemas import (
    DiscordCatalogEmoji,
    ExpressionCandidate,
    ExpressionContent,
    ExpressionDecision,
)
from echo_masque.config import LangGraphMode
from echo_masque.context_layer import CharacterContextTraceView
from echo_masque.smart_output import (
    DiscordActionParticipant,
    DiscordSmartOutputView,
)
from echo_masque.tool_runtime import ToolExecutionTrace

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
    address_aliases: list[str] = Field(default_factory=list, max_length=20)
    webhook_status: DiscordWebhookStatus = "pending"
    webhook_id: str | None = None
    webhook_token: str | None = None
    orchestration_mode: LangGraphMode = "off"


class DiscordCatalogChannel(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    category_id: str = Field(default="", max_length=200)
    category_name: str = Field(default="", max_length=160)
    type: str = Field(default="text", max_length=40)


class DiscordCatalogSticker(BaseModel):
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)


class DiscordCatalogServer(BaseModel):
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(min_length=1, max_length=160)
    channels: list[DiscordCatalogChannel] = Field(default_factory=list, max_length=1000)
    emojis: list[DiscordCatalogEmoji] = Field(default_factory=list, max_length=1000)
    stickers: list[DiscordCatalogSticker] = Field(default_factory=list, max_length=1000)


class DiscordServerCatalogSync(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    servers: list[DiscordCatalogServer] = Field(default_factory=list, max_length=200)


class DiscordWebhookRegistration(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    deployment_id: str = Field(min_length=1, max_length=64)
    workspace_id: str = Field(default="", max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    category_id: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=200)
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
    replica_region: str = Field(default="", max_length=120)
    replica_id: str = Field(default="", max_length=200)
    gateway_ready: bool = False
    state_synchronized: bool = False
    visible_server_count: int = Field(default=0, ge=0, le=10000)
    event_log_pending_count: int = Field(default=0, ge=0, le=10000)
    event_log_last_error: str = Field(default="", max_length=2000)
    event_log_last_success_at: str = Field(default="", max_length=64)
    event_log_last_recorded_at: str = Field(default="", max_length=64)
    event_log_last_recorded_type: str = Field(default="", max_length=80)
    event_log_sent_count: int = Field(default=0, ge=0)
    last_gateway_message_at: str = Field(default="", max_length=64)
    last_gateway_message_id: str = Field(default="", max_length=200)
    last_gateway_mentioned_bot: bool = False


class DiscordConnectorEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    level: Literal["info", "warning", "error"]
    event_type: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)
    guild_id: str = Field(default="", max_length=200)
    guild_name: str = Field(default="", max_length=160)
    channel_id: str = Field(default="", max_length=200)
    channel_name: str = Field(default="", max_length=160)
    thread_id: str = Field(default="", max_length=200)
    thread_name: str = Field(default="", max_length=160)
    source_message_id: str = Field(default="", max_length=200)
    deployment_id: str = Field(default="", max_length=64)
    character_name: str = Field(default="", max_length=160)
    details: dict[str, object] = Field(default_factory=dict, max_length=40)


class DiscordConnectorEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    events: list[DiscordConnectorEventItem] = Field(min_length=1, max_length=100)


class DiscordStickerContent(BaseModel):
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)
    semantic_intent: str = Field(default="sticker_reaction", max_length=80)
    semantic_emotion: str = Field(default="", max_length=80)
    semantic_description: str = Field(default="", max_length=2000)
    semantic_source: Literal["manual", "discord_metadata", "unknown"] = "unknown"
    semantic_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DiscordStickerObservation(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)


class DiscordInteractionSessionConnectorView(BaseModel):
    id: str
    participant_deployment_ids: list[str] = Field(min_length=2, max_length=2)
    rounds_per_trigger: int = Field(ge=1, le=3)
    intensity: Literal["light", "playful", "sharp"]
    target_user_id: str
    target_display_name: str


class DiscordInteractionClaimRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    target_user_id: str = Field(min_length=1, max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)


class DiscordInteractionClaimView(BaseModel):
    claimed: bool = False
    run_id: str | None = None
    session: DiscordInteractionSessionConnectorView | None = None


class DiscordInteractionRunComplete(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    status: Literal["completed", "failed"]
    reply_count: int = Field(default=0, ge=0, le=30)
    stop_reason: str = Field(default="", max_length=2000)


class DiscordAttachmentContent(BaseModel):
    """Attachment metadata supplied by the Discord Connector without raw bytes."""

    attachment_id: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=3000)
    proxy_url: str = Field(default="", max_length=3000)
    filename: str = Field(default="attachment", max_length=255)
    content_type: str = Field(default="", max_length=160)
    size_bytes: int | None = Field(default=None, ge=0, le=2_147_483_647)
    width: int | None = Field(default=None, ge=0, le=100_000)
    height: int | None = Field(default=None, ge=0, le=100_000)


class DiscordEmbedContent(BaseModel):
    """Human-visible Discord link preview metadata used before deciding to inspect content."""

    embed_type: str = Field(default="", max_length=80)
    url: str = Field(default="", max_length=3000)
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=2000)
    provider_name: str = Field(default="", max_length=200)
    author_name: str = Field(default="", max_length=200)


class DiscordContextMessage(BaseModel):
    message_id: str = Field(min_length=1, max_length=200)
    author_id: str = Field(min_length=1, max_length=200)
    author_display_name: str = Field(min_length=1, max_length=160)
    text: str = Field(default="", max_length=10000)
    emojis: list[ExpressionContent] = Field(default_factory=list, max_length=20)
    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)
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
    emojis: list[ExpressionContent] = Field(default_factory=list, max_length=20)
    mentioned_bot: bool = False
    replied_to_bot: bool = False
    reply_to_message_id: str = Field(default="", max_length=200)
    smart_candidate: bool = False
    author_is_bot: bool = False
    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)
    attachments: list[DiscordAttachmentContent] = Field(default_factory=list, max_length=10)
    embeds: list[DiscordEmbedContent] = Field(default_factory=list, max_length=10)
    burst_media_message_ids: list[str] = Field(default_factory=list, max_length=3)
    available_characters: list[str] = Field(default_factory=list, max_length=30)
    mentionable_participants: list[DiscordActionParticipant] = Field(
        default_factory=list, max_length=20
    )
    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)
    interaction_session_id: str = Field(default="", max_length=64)
    interaction_type: str = Field(default="", max_length=32)
    interaction_intensity: str = Field(default="", max_length=24)
    interaction_round: int = Field(default=0, ge=0, le=10)
    interaction_total_rounds: int = Field(default=0, ge=0, le=10)
    interaction_position: int = Field(default=0, ge=0, le=10)
    interaction_participant_count: int = Field(default=0, ge=0, le=10)
    interaction_target_user_id: str = Field(default="", max_length=200)
    interaction_target_display_name: str = Field(default="", max_length=160)
    expression_run_id: str = Field(default="", max_length=64)
    expression_candidates: list[ExpressionCandidate] = Field(default_factory=list, max_length=10)
    runtime_operation_id: str = Field(default="", max_length=64)
    runtime_step_id: str = Field(default="", max_length=64)


class DiscordConnectorReplyView(BaseModel):
    action: Literal["silent", "reply", "expression"]
    reason: str
    deployment_id: str | None = None
    character_display_name: str | None = None
    text: str | None = None
    reply_to_message_id: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    expression: ExpressionDecision = Field(default_factory=ExpressionDecision)
    smart_output: DiscordSmartOutputView | None = None
    context_trace: CharacterContextTraceView | None = None
    tool_calls: list[ToolExecutionTrace] = Field(default_factory=list, max_length=8)
    generated_artifact_ids: list[str] = Field(default_factory=list, max_length=4)
