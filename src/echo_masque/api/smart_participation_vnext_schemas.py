"""Smart Participation vNext read model: Burst Segments + concurrent Semantic Threads."""

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


class SmartParticipationResolveVNextView(SmartParticipationResolveView):
    model_config = ConfigDict(extra="forbid")

    resolver_version: str = "conversation-intelligence-vnext"
    segmentation_used: bool = False
    segmentation_source: str = ""
    conversation_segments: list[ConversationSegmentRouteView] = Field(default_factory=list)
    reply_targets: list[ReplyTargetRouteView] = Field(default_factory=list)


__all__ = [
    "ConversationSegmentRouteView",
    "ReplyTargetRouteView",
    "SmartParticipationResolveVNextView",
]
