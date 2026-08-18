"""Portal schemas for Deployment-scoped Presence state and rhythm."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PresenceState = Literal["sleeping", "idle", "browsing", "busy"]


class DeploymentPresenceUpdate(BaseModel):
    state: PresenceState
    activity_type: str = Field(default="", max_length=40)
    reason: str = Field(default="", max_length=1000)
    expected_end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_activity(self) -> "DeploymentPresenceUpdate":
        if self.state == "browsing" and not self.activity_type.strip():
            raise ValueError("Browsing Presence requires an activity_type.")
        if self.state != "browsing" and self.activity_type.strip():
            raise ValueError("activity_type is only valid while Presence is browsing.")
        return self


class DeploymentPresenceView(BaseModel):
    deployment_id: str
    state: PresenceState
    activity_type: str
    source: str
    reason: str
    version: int
    started_at: datetime
    expected_end_at: datetime | None
    updated_at: datetime
    persisted: bool
    available_for_character_runtime: bool
    discovery_allowed: bool


class DeploymentPresenceRhythmUpdate(BaseModel):
    enabled: bool = False
    preferred_sleep_start_minute: int = Field(default=60, ge=0, le=1439)
    sleep_duration_min_minutes: int = Field(default=420, ge=60, le=960)
    sleep_duration_max_minutes: int = Field(default=540, ge=60, le=960)
    variation_minutes: int = Field(default=45, ge=0, le=180)

    @model_validator(mode="after")
    def validate_duration_range(self) -> "DeploymentPresenceRhythmUpdate":
        if self.sleep_duration_max_minutes < self.sleep_duration_min_minutes:
            raise ValueError("Maximum sleep duration must be >= minimum sleep duration.")
        return self


class DeploymentPresenceRhythmView(BaseModel):
    deployment_id: str
    enabled: bool
    preferred_sleep_start_minute: int
    sleep_duration_min_minutes: int
    sleep_duration_max_minutes: int
    variation_minutes: int
    config_version: int
    schedule_local_date: str
    schedule_timezone: str
    scheduled_sleep_at: datetime | None
    scheduled_wake_at: datetime | None
    next_transition_at: datetime | None
    next_state: str
    last_transition_at: datetime | None
    last_transition_reason: str


__all__ = [
    "DeploymentPresenceRhythmUpdate",
    "DeploymentPresenceRhythmView",
    "DeploymentPresenceUpdate",
    "DeploymentPresenceView",
    "PresenceState",
]
