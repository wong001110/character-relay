"""HTTP and Connector schemas for Server expression retrieval workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExpressionResourceType = Literal["emoji", "sticker"]
ExpressionAction = Literal["none", "inline", "reaction", "sticker"]
ExpressionNodeStatus = Literal["running", "completed", "failed", "skipped"]
ExpressionRunStatus = Literal["running", "completed", "failed", "skipped"]
ExpressionRetrievalBackend = Literal["hybrid_sparse_v1"]


def default_expression_actions() -> list[Literal["inline", "reaction", "sticker"]]:
    return ["inline", "reaction", "sticker"]


class ExpressionIntent(BaseModel):
    """Model describes meaning; only the runtime can resolve an actual guild resource."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["emoji", "sticker"]
    intent: str = Field(min_length=1, max_length=80)
    emotion: str = Field(default="", max_length=80)

    @field_validator("intent", "emotion")
    @classmethod
    def trim_meaning(cls, value: str, info: object) -> str:
        value = value.strip()
        if getattr(info, "field_name", "") == "intent" and not value:
            raise ValueError("expression intent must be nonblank")
        return value


class DiscordCatalogEmoji(BaseModel):
    emoji_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    animated: bool = False
    available: bool = True
    asset_url: str = Field(default="", max_length=2000)


class ExpressionSemanticCreate(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    resource_type: ExpressionResourceType
    resource_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)
    animated: bool = False
    available: bool = True
    enabled: bool = True
    semantic_intent: str = Field(default="", max_length=80)
    semantic_emotion: str = Field(default="", max_length=80)
    semantic_description: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    situations: list[str] = Field(default_factory=list, max_length=30)
    avoid_when: list[str] = Field(default_factory=list, max_length=30)
    allowed_actions: list[Literal["inline", "reaction", "sticker"]] = Field(
        default_factory=list,
        max_length=3,
    )


class ExpressionSemanticView(ExpressionSemanticCreate):
    id: str
    resource_key: str
    semantic_source: Literal["manual", "discord_metadata", "unknown"]
    semantic_confidence: float
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class ExpressionResolveRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    resource_type: ExpressionResourceType
    resource_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    animated: bool = False
    available: bool = True
    asset_url: str = Field(default="", max_length=2000)


class ExpressionContent(BaseModel):
    resource_key: str
    resource_type: ExpressionResourceType
    resource_id: str
    name: str
    animated: bool
    available: bool
    enabled: bool
    allowed_actions: list[Literal["inline", "reaction", "sticker"]]
    semantic_intent: str
    semantic_emotion: str
    semantic_description: str
    semantic_source: Literal["manual", "discord_metadata", "unknown"]
    semantic_confidence: float
    asset_url: str
    format_type: str


class ExpressionCandidate(ExpressionContent):
    score: float
    signals: dict[str, float] = Field(default_factory=dict)


class ExpressionDecision(BaseModel):
    action: ExpressionAction = "none"
    resource_key: str | None = Field(default=None, max_length=240)
    reason: str = Field(default="", max_length=300)
