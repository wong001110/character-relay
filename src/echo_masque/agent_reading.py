"""Bounded Agent reading contracts; references to collected current state, never replay."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentReadingReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str
    source_revision: int
    room_revision: int
    change: Literal["new", "edited", "deleted", "unavailable"]


class AgentReadingItem(AgentReadingReference):
    state: Literal["current", "changed", "removed"]
    message: dict[str, Any] | None


class AgentReadingBatch(BaseModel):
    id: str
    from_revision: int
    to_revision: int
    gap_generation: int
    needs_reread: bool
    items: list[AgentReadingItem]


class AgentReadingStatus(BaseModel):
    room_id: str
    profile_id: str
    cursor_revision: int
    observed_revision: int
    pending_count: int
    needs_reread: bool
    gap_generation: int
    history_scope: Literal["recorded_current_state"] = "recorded_current_state"
    batch: AgentReadingBatch | None


class AgentReadingGap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class AgentReadingComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str = Field(min_length=1, max_length=64)


class AgentReadingStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
