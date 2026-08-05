"""HTTP schemas for Interaction Sessions and the Discord Sticker Dictionary."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

InteractionStatus = Literal["active", "paused", "stopped", "completed"]
InteractionIntensity = Literal["light", "playful", "sharp"]


class InteractionTemplateCreate(BaseModel):
    server_profile_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    participant_character_card_ids: list[str] = Field(min_length=2, max_length=2)
    rounds_per_trigger: int = Field(default=1, ge=1, le=3)
    maximum_triggers: int = Field(default=1, ge=1, le=5)
    cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    duration_seconds: int = Field(default=600, ge=60, le=86400)
    intensity: InteractionIntensity = "playful"


class InteractionTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    participant_character_card_ids: list[str] | None = Field(
        default=None, min_length=2, max_length=2
    )
    rounds_per_trigger: int | None = Field(default=None, ge=1, le=3)
    maximum_triggers: int | None = Field(default=None, ge=1, le=5)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)
    duration_seconds: int | None = Field(default=None, ge=60, le=86400)
    intensity: InteractionIntensity | None = None


class InteractionTemplateView(BaseModel):
    id: str
    server_profile_id: str
    name: str
    template_type: Literal["roast"] = "roast"
    participant_character_card_ids: list[str]
    participant_names: list[str]
    rounds_per_trigger: int
    maximum_triggers: int
    maximum_replies_per_trigger: int
    cooldown_seconds: int
    duration_seconds: int
    intensity: InteractionIntensity
    created_at: datetime
    updated_at: datetime


class InteractionTemplateApply(BaseModel):
    channel_id: str = Field(min_length=1, max_length=200)
    target_user_id: str = Field(min_length=2, max_length=200)
    target_display_name: str = Field(default="", max_length=160)
    status: Literal["active", "paused"] = "paused"


class InteractionSessionCreate(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(default="", max_length=160)
    channel_id: str = Field(min_length=1, max_length=200)
    channel_name: str = Field(default="", max_length=160)
    category_id: str = Field(default="", max_length=200)
    target_user_id: str = Field(min_length=2, max_length=200)
    target_display_name: str = Field(default="", max_length=160)
    participant_deployment_ids: list[str] = Field(min_length=2, max_length=2)
    rounds_per_trigger: int = Field(default=1, ge=1, le=3)
    maximum_triggers: int = Field(default=1, ge=1, le=5)
    cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    duration_seconds: int = Field(default=600, ge=60, le=86400)
    intensity: InteractionIntensity = "playful"
    status: Literal["active", "paused"] = "paused"


class InteractionSessionStatusUpdate(BaseModel):
    status: InteractionStatus


class InteractionSessionView(BaseModel):
    id: str
    connection_id: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    category_id: str
    target_user_id: str
    target_display_name: str
    participant_deployment_ids: list[str]
    participant_names: list[str]
    session_type: Literal["roast"] = "roast"
    rounds_per_trigger: int
    maximum_triggers: int
    completed_triggers: int
    maximum_replies_per_trigger: int
    cooldown_seconds: int
    duration_seconds: int
    intensity: InteractionIntensity
    status: InteractionStatus
    started_at: datetime | None
    expires_at: datetime | None
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StickerSemanticCreate(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)
    semantic_intent: str = Field(default="sticker_reaction", max_length=80)
    semantic_emotion: str = Field(default="", max_length=80)
    semantic_description: str = Field(min_length=1, max_length=2000)


class StickerSemanticView(BaseModel):
    id: str
    connection_id: str
    guild_id: str
    sticker_id: str
    name: str
    description: str
    tags: list[str]
    format_type: str
    asset_url: str
    semantic_intent: str
    semantic_emotion: str
    semantic_description: str
    semantic_source: Literal["manual", "discord_metadata", "unknown"]
    semantic_confidence: float
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime
