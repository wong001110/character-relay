"""Conversation-aware Smart Participation V4 connector contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.participation_admission_policy import resolve_admission_limit


class SmartParticipationBurstMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(min_length=1, max_length=200)
    author_id: str = Field(min_length=1, max_length=200)
    author_display_name: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=4_000)
    created_at: str = Field(default="", max_length=80)
    reply_to_message_id: str = Field(default="", max_length=200)


class SmartParticipationMediaDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=220)
    kind: str = Field(min_length=1, max_length=32)
    state: str = Field(min_length=1, max_length=32)
    label: str = Field(default="", max_length=300)
    subject: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=1200)
    source_key: str = Field(default="", max_length=500)
    source_url: str = Field(default="", max_length=3000)
    topic_evidence: bool = False


class SmartParticipationResolveCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str = Field(min_length=1, max_length=64)
    eligible: bool = True
    deterministic_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    minimum_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    signals: dict[str, float] = Field(default_factory=dict, max_length=24)


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
    minimum_margin: float = Field(default=2.0, ge=0.0, le=100.0)
    max_participants: int = Field(default=2, ge=1, le=10)
    admission_limit_reason: str = Field(default="", max_length=80)
    admission_group_invitation: bool = False
    channel_cooldown_seconds: int = Field(default=45, ge=0, le=86_400)
    window_seconds: int = Field(default=600, ge=1, le=86_400)
    max_replies_per_window: int = Field(default=3, ge=1, le=100)
    media_descriptors: list[SmartParticipationMediaDescriptor] = Field(
        default_factory=list,
        max_length=6,
    )
    media_dependency: Literal["required", "optional", "none"] = "none"
    media_dependency_locked: bool = False
    candidates: list[SmartParticipationResolveCandidate] = Field(
        min_length=1,
        max_length=24,
    )

    @model_validator(mode="after")
    def resolve_dynamic_admission_limit(self) -> SmartParticipationResolveRequest:
        decision = resolve_admission_limit(
            message=self.message,
            burst_messages=self.burst_messages,
            eligible_candidate_count=sum(1 for item in self.candidates if item.eligible),
            requested_max=self.max_participants,
        )
        self.max_participants = decision.limit
        self.admission_limit_reason = decision.reason
        self.admission_group_invitation = decision.group_invitation
        return self


class SmartParticipationResolveCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str
    character_card_id: str
    eligible: bool
    deterministic_score: float
    minimum_score: float
    deterministic_signals: dict[str, float] = Field(default_factory=dict, max_length=24)
    raw_e5_relevance: float = 0.0
    profile_ready: bool = False
    semantic_points: float = 0.0
    shadow_final_score: float = 0.0
    shadow_selected: bool = False
    graph_evidence_count: int = 0
    learned_state_evidence_count: int = 0
    utility_adjustment: float = 0.0


class SmartParticipationSpeakerPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str
    turn_role: str = "participant"
    reason: str = ""
    guidance: str = Field(default="", max_length=240)


class SmartParticipationResolveView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolver_version: str = "conversation-intelligence-v4-shadow-2"
    available: bool
    reason: str
    model: str = ""
    dimension: int = 0
    burst_id: str = ""
    burst_message_count: int = 0
    analysis_chars: int = 0
    candidates: list[SmartParticipationResolveCandidateView] = Field(default_factory=list)
    speaker_plan: list[SmartParticipationSpeakerPlanItem] = Field(default_factory=list)
    shadow_speaker_plan: list[SmartParticipationSpeakerPlanItem] = Field(default_factory=list)
    speaker_plan_authoritative: bool = False
    conversation_plan_version: str = ""
    conversation_planner_used: bool = False
    conversation_planner_accepted: bool = False
    conversation_planner_authoritative: bool = False
    conversation_planner_rollout_bucket: int = Field(default=0, ge=0, le=99)
    conversation_planner_rollout_percent: int = Field(default=0, ge=0, le=100)
    conversation_planner_shadow_plan: list[SmartParticipationSpeakerPlanItem] = Field(
        default_factory=list
    )
    graph_shadow_observed: bool = False
    graph_shadow_node_count: int = 0
    graph_shadow_edge_count: int = 0
    topic_graph_shadow_observed: bool = False
    topic_graph_shadow_owner_count: int = 0
    topic_graph_shadow_topic_count: int = 0
    topic_graph_shadow_node_count: int = 0
    topic_graph_shadow_edge_count: int = 0
    graph_used: bool = False
    learned_state_used: bool = False
    utility_used: bool = False


__all__ = [
    "SmartParticipationBurstMessage",
    "SmartParticipationMediaDescriptor",
    "SmartParticipationResolveCandidate",
    "SmartParticipationResolveCandidateView",
    "SmartParticipationResolveRequest",
    "SmartParticipationResolveView",
    "SmartParticipationSpeakerPlanItem",
]
