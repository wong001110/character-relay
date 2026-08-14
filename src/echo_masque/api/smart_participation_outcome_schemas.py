"""Bounded connector-to-server outcome contract for V4 derived/durable state."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SmartParticipationOutcomeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(default="", max_length=128)
    channel_id: str = Field(default="", max_length=128)
    thread_id: str = Field(default="", max_length=128)
    message_id: str = Field(default="", max_length=200)
    burst_id: str = Field(default="", max_length=80)
    author_id: str = Field(default="", max_length=200)
    reply_to_message_id: str = Field(default="", max_length=200)
    selected_deployment_ids: list[str] = Field(default_factory=list, max_length=3)
    candidate_deployment_ids: list[str] = Field(default_factory=list, max_length=24)


class SmartParticipationOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded: bool
    selected_count: int = 0
    graph_edge_count: int = 0
    learned_evidence_count: int = 0
    durable_recorded: bool = False


__all__ = ["SmartParticipationOutcomeObservation", "SmartParticipationOutcomeView"]
