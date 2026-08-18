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


__all__ = [
    "DeploymentDiscoveryDecisionListView",
    "DeploymentDiscoveryDecisionView",
    "DeploymentDiscoveryExposureListView",
    "DeploymentDiscoveryExposureView",
    "DeploymentDiscoveryProfileUpdate",
    "DeploymentDiscoveryProfileView",
    "DiscoveryItemView",
]
