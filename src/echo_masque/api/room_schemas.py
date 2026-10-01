"""Authenticated Connector transport, not model-owned routing authority."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from echo_masque.room_director import AttemptReceipt
from echo_masque.room_sources import SourceMessage


class RoomLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    category_id: str = Field(default="", max_length=200)


class RoomEventsRequest(RoomLocation):
    messages: list[SourceMessage] = Field(default_factory=list, max_length=64)
    # Only an adapter's current effective platform permission observation may set this.
    readable: bool = True
    permission_checked_at: AwareDatetime

    @field_validator("permission_checked_at")
    @classmethod
    def recent_platform_observation(cls, value: datetime) -> datetime:
        age = datetime.now(UTC) - value
        if not timedelta(seconds=-10) <= age <= timedelta(minutes=5):
            raise ValueError("A current platform permission observation is required.")
        return value


class RoomRoutingRequest(RoomEventsRequest):
    request_id: str = Field(min_length=1, max_length=200)
    trigger_message_id: str = Field(min_length=1, max_length=200)
    deployment_ids: list[str] = Field(min_length=1, max_length=24)
    # Platform mentions or unambiguous explicit address syntax, not semantic scores.
    explicit_deployment_ids: list[str] = Field(default_factory=list, max_length=24)
    action_actor_id: str = Field(default="", max_length=200)
    action_target_message_id: str = Field(default="", max_length=200)
    ambient_requested: bool = False


class RoomChoiceView(BaseModel):
    deployment_id: str
    target_message_id: str
    selection_id: str
    mode: str


class RoomRoutingView(BaseModel):
    outcome: Literal["direct", "decision", "none", "blocked", "unavailable", "invalid"]
    reason: str
    choices: list[RoomChoiceView] = Field(default_factory=list, max_length=24)
    route_id: str = ""
    attempts: list[AttemptReceipt] = Field(default_factory=list, max_length=8)
    snapshot_revision: int = 0
    prompt_version: str = ""
    input_fingerprint: str = ""


class DraftPreflightRequest(RoomEventsRequest):
    operation_id: str = Field(min_length=32, max_length=64)
    step_id: str = Field(min_length=32, max_length=64)
    writable: bool
