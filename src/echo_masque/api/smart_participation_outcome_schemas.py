"""Bounded connector-to-server Intelligence Core v3 participation outcome contracts."""

from __future__ import annotations

from typing import Literal

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
    author_display_name: str = Field(default="", max_length=160)
    author_global_name: str = Field(default="", max_length=160)
    author_username: str = Field(default="", max_length=160)
    author_avatar_url: str = Field(default="", max_length=2000)
    author_is_bot: bool = False
    reply_to_message_id: str = Field(default="", max_length=200)
    selected_deployment_ids: list[str] = Field(default_factory=list, max_length=10)
    candidate_deployment_ids: list[str] = Field(default_factory=list, max_length=24)


class SmartParticipationOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded: bool
    selected_count: int = 0
    graph_edge_count: int = 0
    learned_evidence_count: int = 0
    durable_recorded: bool = False


class SmartParticipationRecentSpeakerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(default="", max_length=128)
    channel_id: str = Field(default="", max_length=128)
    thread_id: str = Field(default="", max_length=128)
    maximum_age_seconds: int = Field(default=90, ge=1, le=3600)
    allowed_deployment_ids: list[str] = Field(min_length=1, max_length=24)


class SmartParticipationLearnedEvidenceRequest(BaseModel):
    """Explicit Behavior State evidence only; Character prose is never implicit proof."""

    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    deployment_id: str = Field(min_length=1, max_length=64)
    state_type: Literal["expertise", "stance"]
    subject_type: Literal["thread", "concept", "event", "media"]
    subject_key: str = Field(min_length=1, max_length=240)
    delta: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: Literal[
        "runtime_tool_success",
        "knowledge_verification",
        "explicit_member_feedback",
    ]
    source_message_id: str = Field(default="", max_length=200)
    source_burst_id: str = Field(default="", max_length=80)
    reason_code: str = Field(default="", max_length=120)


class SmartParticipationLearnedEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded: bool
    state_type: str = ""
    subject_key: str = ""
    value: float = 0.0
    confidence: float = 0.0
    evidence_count: int = 0


__all__ = [
    "SmartParticipationLearnedEvidenceRequest",
    "SmartParticipationLearnedEvidenceView",
    "SmartParticipationOutcomeObservation",
    "SmartParticipationOutcomeView",
    "SmartParticipationRecentSpeakerRequest",
    "SmartParticipationRecentSpeakerView",
]
