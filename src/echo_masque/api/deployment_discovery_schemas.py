"""Portal/API schemas for Deployment-scoped Character Discovery."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DiscoveryRolloutMode = Literal["off", "shadow", "review", "auto"]
DiscoveryPlatform = Literal["youtube", "bilibili"]


class DeploymentDiscoveryProfileUpdate(BaseModel):
    mode: DiscoveryRolloutMode = "off"
    youtube_enabled: bool = False
    bilibili_enabled: bool = False
    auto_share_enabled: bool = False
    daily_share_budget: int = Field(default=1, ge=0, le=8)
    share_cooldown_minutes: int = Field(default=180, ge=15, le=1440)


class DeploymentDiscoveryProfileView(BaseModel):
    deployment_id: str
    mode: str
    youtube_enabled: bool
    bilibili_enabled: bool
    bilibili_experimental_available: bool = False
    auto_share_enabled: bool = False
    auto_global_enabled: bool = False
    daily_share_budget: int = 1
    share_cooldown_minutes: int = 180


class DiscoveryItemView(BaseModel):
    id: str
    source: str
    canonical_key: str
    content_kind: str
    title: str
    creator: str
    url: str
    thumbnail_url: str
    published_at: datetime | None


class DeploymentDiscoveryExposureView(BaseModel):
    id: str
    deployment_id: str
    item: DiscoveryItemView
    attention_level: str
    interest_score: float
    subjective_reason: str
    exposure_count: int
    first_exposed_at: datetime
    last_exposed_at: datetime


class DeploymentDiscoveryDecisionView(BaseModel):
    id: str
    deployment_id: str
    item: DiscoveryItemView
    mode: str
    decision: str
    motivation: str
    confidence: float
    scores: dict[str, object] = Field(default_factory=dict)
    evidence: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class DeploymentDiscoveryExposureListView(BaseModel):
    items: list[DeploymentDiscoveryExposureView]


class DeploymentDiscoveryDecisionListView(BaseModel):
    items: list[DeploymentDiscoveryDecisionView]


class DiscoverySeedView(BaseModel):
    text: str
    weight: float
    source: str
    evidence_ref: str


class RankedDiscoveryCandidateView(BaseModel):
    item: DiscoveryItemView
    semantic_relevance: float
    sparse_relevance: float
    freshness: float
    novelty: float
    exploration: float
    final_score: float
    reason: str


class DeploymentDiscoveryShadowPreviewView(BaseModel):
    deployment_id: str
    queries: list[str]
    seeds: list[DiscoverySeedView]
    candidates: list[RankedDiscoveryCandidateView]
    sources: list[str] = Field(default_factory=list)
    source_errors: list[str] = Field(default_factory=list)
    side_effects: Literal[False] = False


class DeploymentDiscoveryBrowseShadowRequest(BaseModel):
    platform: DiscoveryPlatform | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=120)
    candidate_budget: int | None = Field(default=None, ge=3, le=30)
    open_budget: int | None = Field(default=None, ge=0, le=10)


class DeploymentActivitySessionView(BaseModel):
    id: str
    deployment_id: str
    activity_type: str
    platform: str
    status: str
    source: str
    local_date: str
    schedule_timezone: str
    scheduled_start_at: datetime | None
    latest_start_at: datetime | None
    planned_duration_minutes: int
    started_at: datetime | None
    expected_end_at: datetime | None
    ended_at: datetime | None
    candidate_budget: int
    open_budget: int
    watch_budget: int
    share_intent_budget: int
    exploration_percent: int
    candidate_count: int
    notice_count: int
    open_count: int
    watch_count: int
    engage_count: int
    reason: str
    error: str


class DeploymentActivitySessionItemView(BaseModel):
    rank_position: int
    attention_level: str
    score: float
    reason: str
    item: DiscoveryItemView


class DeploymentActivitySessionDetailView(BaseModel):
    session: DeploymentActivitySessionView
    items: list[DeploymentActivitySessionItemView]


class DeploymentActivitySessionListView(BaseModel):
    items: list[DeploymentActivitySessionView]


class DeploymentDiscoveryShareView(BaseModel):
    id: str
    deployment_id: str
    item: DiscoveryItemView
    mode: str
    status: str
    motivation: str
    confidence: float
    topic_id: str
    relationship_subject_key: str
    channel_id: str
    thread_id: str
    draft_text: str
    attempt_count: int
    last_error: str
    approved_at: datetime | None
    rejected_at: datetime | None
    queued_at: datetime | None
    delivered_at: datetime | None
    discord_message_id: str
    created_at: datetime


class DeploymentDiscoveryShareListView(BaseModel):
    items: list[DeploymentDiscoveryShareView]


__all__ = [
    "DeploymentActivitySessionDetailView",
    "DeploymentActivitySessionItemView",
    "DeploymentActivitySessionListView",
    "DeploymentActivitySessionView",
    "DeploymentDiscoveryBrowseShadowRequest",
    "DeploymentDiscoveryDecisionListView",
    "DeploymentDiscoveryDecisionView",
    "DeploymentDiscoveryExposureListView",
    "DeploymentDiscoveryExposureView",
    "DeploymentDiscoveryProfileUpdate",
    "DeploymentDiscoveryProfileView",
    "DeploymentDiscoveryShareListView",
    "DeploymentDiscoveryShareView",
    "DeploymentDiscoveryShadowPreviewView",
    "DiscoveryItemView",
    "DiscoveryPlatform",
    "DiscoveryRolloutMode",
    "DiscoverySeedView",
    "RankedDiscoveryCandidateView",
]
