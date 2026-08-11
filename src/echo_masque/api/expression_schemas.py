"""HTTP and Connector schemas for Server expression retrieval workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ExpressionResourceType = Literal["emoji", "sticker"]
ExpressionAction = Literal["none", "inline", "reaction", "sticker"]
ExpressionNodeStatus = Literal["running", "completed", "failed", "skipped"]
ExpressionRunStatus = Literal["running", "completed", "failed", "skipped"]
ExpressionRetrievalBackend = Literal["hybrid_sparse_v1", "hybrid_dense_sparse_v2"]


def default_expression_actions() -> list[Literal["inline", "reaction", "sticker"]]:
    return ["inline", "reaction", "sticker"]


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


class ExpressionRetrieveRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)
    deployment_id: str = Field(min_length=1, max_length=64)
    query: str = Field(default="", max_length=4000)
    allowed_actions: list[Literal["inline", "reaction", "sticker"]] = Field(
        default_factory=default_expression_actions,
        min_length=1,
        max_length=3,
    )
    excluded_resource_keys: list[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=6, ge=1, le=10)
    run_id: str | None = Field(default=None, max_length=64)


class ExpressionRetrievalView(BaseModel):
    run_id: str
    attempt: int
    retrieval_backend: ExpressionRetrievalBackend = "hybrid_sparse_v1"
    candidates: list[ExpressionCandidate]

    @model_validator(mode="after")
    def infer_retrieval_backend(self) -> ExpressionRetrievalView:
        if any("dense" in item.signals for item in self.candidates):
            self.retrieval_backend = "hybrid_dense_sparse_v2"
        return self


class ExpressionNodeReport(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    node_name: str = Field(min_length=1, max_length=80)
    status: ExpressionNodeStatus
    input_summary: dict[str, object] = Field(default_factory=dict, max_length=40)
    output_summary: dict[str, object] = Field(default_factory=dict, max_length=40)
    error: str = Field(default="", max_length=2000)
    selected_action: ExpressionAction | None = None
    selected_resource_key: str | None = Field(default=None, max_length=240)
    final_status: ExpressionRunStatus | None = None


class ExpressionNodeView(BaseModel):
    id: str
    node_name: str
    node_index: int
    attempt: int
    status: ExpressionNodeStatus
    input_summary: dict[str, object]
    output_summary: dict[str, object]
    error: str
    started_at: datetime
    completed_at: datetime | None


class ExpressionRunView(BaseModel):
    id: str
    connection_id: str
    guild_id: str
    channel_id: str
    source_message_id: str
    deployment_id: str
    character_card_id: str
    status: ExpressionRunStatus
    current_node: str
    attempt_count: int
    selected_action: ExpressionAction
    selected_resource_key: str
    state: dict[str, object]
    last_error: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ExpressionRunDetail(ExpressionRunView):
    nodes: list[ExpressionNodeView]


class ExpressionDecision(BaseModel):
    action: ExpressionAction = "none"
    resource_key: str | None = Field(default=None, max_length=240)
    reason: str = Field(default="", max_length=300)
