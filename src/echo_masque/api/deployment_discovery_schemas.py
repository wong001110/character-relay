"""Portal/API schemas for Deployment-scoped Character Discovery."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DiscoveryRolloutMode = Literal["off", "shadow"]


class DeploymentDiscoveryProfileUpdate(BaseModel):
    mode: DiscoveryRolloutMode = "off"
    youtube_enabled: bool = False
    bilibili_enabled: bool = False

    @model_validator(mode="after")
    def block_unimplemented_bilibili(self) -> "DeploymentDiscoveryProfileUpdate":
        if self.bilibili_enabled:
            raise ValueError("Bilibili Discovery remains experimental and is not enabled yet.")
        return self


class DeploymentDiscoveryProfileView(BaseModel):
    deployment_id: str
    mode: str
    youtube_enabled: bool
    bilibili_enabled: bool


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
    side_effects: Literal[False] = False


class DeploymentDiscoveryBrowseShadowRequest(BaseModel):
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
    "DeploymentDiscoveryShadowPreviewView",
    "DiscoveryItemView",
    "DiscoverySeedView",
    "RankedDiscoveryCandidateView",
]
