"""Conversation-aware Smart Participation V4 connector contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SmartParticipationBurstMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(min_length=1, max_length=200)
    author_id: str = Field(min_length=1, max_length=200)
    author_display_name: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=4_000)
    created_at: str = Field(default="", max_length=80)
    reply_to_message_id: str = Field(default="", max_length=200)


class SmartParticipationResolveCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str = Field(min_length=1, max_length=64)
    eligible: bool = True
    deterministic_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    minimum_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    signals: dict[str, float] = Field(default_factory=dict)


class SmartParticipationResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(default="", max_length=128)
    channel_id: str = Field(default="", max_length=128)
    thread_id: str = Field(default="", max_length=128)
    message_id: str = Field(default="", max_length=200)
    author_id: str = Field(default="", max_length=200)
    reply_to_message_id: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=4_000)
    burst_id: str = Field(default="", max_length=80)
    burst_messages: list[SmartParticipationBurstMessage] = Field(
        default_factory=list,
        max_length=5,
    )
    candidates: list[SmartParticipationResolveCandidate] = Field(
        min_length=1,
        max_length=24,
    )


class SmartParticipationResolveCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str
    character_card_id: str
    eligible: bool
    deterministic_score: float
    minimum_score: float
    raw_e5_relevance: float = 0.0
    profile_ready: bool = False
    graph_evidence_count: int = 0
    learned_state_evidence_count: int = 0
    utility_adjustment: float = 0.0


class SmartParticipationSpeakerPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str
    turn_role: str = "primary"
    reason: str = ""


class SmartParticipationResolveView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolver_version: str = "conversation-intelligence-v4-shadow-1"
    available: bool
    reason: str
    model: str = ""
    dimension: int = 0
    burst_id: str = ""
    burst_message_count: int = 0
    analysis_chars: int = 0
    candidates: list[SmartParticipationResolveCandidateView] = Field(default_factory=list)
    speaker_plan: list[SmartParticipationSpeakerPlanItem] = Field(default_factory=list)
    graph_shadow_observed: bool = False
    graph_shadow_node_count: int = 0
    graph_shadow_edge_count: int = 0
    graph_used: bool = False
    learned_state_used: bool = False
    utility_used: bool = False


__all__ = [
    "SmartParticipationBurstMessage",
    "SmartParticipationResolveCandidate",
    "SmartParticipationResolveCandidateView",
    "SmartParticipationResolveRequest",
    "SmartParticipationResolveView",
    "SmartParticipationSpeakerPlanItem",
]