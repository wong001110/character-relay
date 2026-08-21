"""Smart Participation vNext read model for Conversation Structure v3."""

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.smart_participation_v4_schemas import SmartParticipationResolveView


class ConversationSegmentRouteView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    message_ids: list[str] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    kind: str
    summary: str
    semantic_thread_id: str
    thread_action: str
    thread_evidence: bool
    confidence: float
    source: str


class ReplyTargetRouteView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str
    segment_id: str
    semantic_thread_id: str
    score: float
    reason: str
    grounding_level: str = "context_only"
    context_sufficiency: str = ""


class SmartParticipationResolveVNextView(SmartParticipationResolveView):
    model_config = ConfigDict(extra="forbid")

    resolver_version: str = "conversation-intelligence-v3"
    segmentation_used: bool = False
    segmentation_source: str = ""
    conversation_segments: list[ConversationSegmentRouteView] = Field(default_factory=list)
    reply_targets: list[ReplyTargetRouteView] = Field(default_factory=list)
    participation_plan_reason: str = ""
    media_grounding_level: str = "context_only"
    media_grounding_reason: str = ""
    context_sufficiency: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "ConversationSegmentRouteView",
    "ReplyTargetRouteView",
    "SmartParticipationResolveVNextView",
]
