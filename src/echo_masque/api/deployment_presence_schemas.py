"""Portal schemas for Deployment-scoped Presence state."""

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


__all__ = ["DeploymentPresenceUpdate", "DeploymentPresenceView", "PresenceState"]
