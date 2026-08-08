"""HTTP schemas for Smart Participation profiles, semantics, previews, and feedback."""

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from echo_masque.persistence.smart_participation_models import (
    SmartParticipationFeedbackRecord,
    SmartParticipationProfileRecord,
)
from echo_masque.persistence.smart_participation_repository import decode_strings

ParticipationStyle = Literal["quiet", "balanced", "active"]
ParticipationGroupRole = Literal["primary", "secondary", "independent"]
ParticipationFeedbackLabel = Literal[
    "correct",
    "should_speak",
    "should_stay_silent",
]
SemanticProfileStatus = Literal[
    "disabled",
    "not_created",
    "ready",
    "stale",
    "invalid",
]


class SmartParticipationProfileUpdate(BaseModel):
    enabled: bool = True
    style: ParticipationStyle = "balanced"
    group_role: ParticipationGroupRole = "independent"
    topics: list[str] = Field(default_factory=list, max_length=80)
    keywords: list[str] = Field(default_factory=list, max_length=120)
    trigger_phrases: list[str] = Field(default_factory=list, max_length=80)
    avoid_phrases: list[str] = Field(default_factory=list, max_length=80)
    cooldown_seconds: int = Field(default=120, ge=0, le=86400)
    preferred_follow_up_character_card_id: str = Field(default="", max_length=64)
    follow_up_window_seconds: int = Field(default=30, ge=1, le=600)


class SmartParticipationProfileView(SmartParticipationProfileUpdate):
    character_card_id: str
    configured: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def default(cls, character_card_id: str) -> "SmartParticipationProfileView":
        return cls(character_card_id=character_card_id, configured=False)

    @classmethod
    def from_record(
        cls, record: SmartParticipationProfileRecord
    ) -> "SmartParticipationProfileView":
        return cls(
            character_card_id=record.character_card_id,
            configured=True,
            enabled=record.enabled,
            style=cast(ParticipationStyle, record.style),
            group_role=cast(ParticipationGroupRole, record.group_role),
            topics=decode_strings(record.topics_json),
            keywords=decode_strings(record.keywords_json),
            trigger_phrases=decode_strings(record.trigger_phrases_json),
            avoid_phrases=decode_strings(record.avoid_phrases_json),
            cooldown_seconds=record.cooldown_seconds,
            preferred_follow_up_character_card_id=record.preferred_follow_up_character_card_id,
            follow_up_window_seconds=record.follow_up_window_seconds,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class SmartParticipationGeneratedProfile(SmartParticipationProfileUpdate):
    preferred_follow_up_character_name: str = ""
    rationale: str = ""
    provider_model: str
    correction_used: bool = False


class SmartParticipationSemanticProfileView(BaseModel):
    character_card_id: str
    status: SemanticProfileStatus
    enabled: bool
    created: bool
    model_name: str
    dimension: int
    embedding_bytes: int
    source_hash: str
    semantic_text: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    rebuilt: bool = False


class SmartParticipationSemanticScoreRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=10000)
    deployment_ids: list[str] = Field(default_factory=list, min_length=1, max_length=100)


class SmartParticipationSemanticCandidateView(BaseModel):
    deployment_id: str
    character_card_id: str
    semantic_relevance: float
    profile_ready: bool


class SmartParticipationSemanticScoreView(BaseModel):
    available: bool
    reason: str
    model: str = ""
    dimension: int = 0
    candidates: list[SmartParticipationSemanticCandidateView] = Field(default_factory=list)


class SmartParticipationPlaygroundRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    previous_character_card_id: str = Field(default="", max_length=64)
    profile_override: SmartParticipationProfileUpdate | None = None


class SmartParticipationPlaygroundView(BaseModel):
    character_card_id: str
    decision: Literal["participate", "silent"]
    reason: str
    score: float
    minimum_score: float
    signals: dict[str, float]
    matched_topics: list[str]
    matched_keywords: list[str]
    matched_trigger_phrases: list[str]
    matched_avoid_phrases: list[str]
    follow_up_eligible: bool
    follow_up_reason: str


class SmartParticipationFeedbackCreate(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    previous_character_card_id: str = Field(default="", max_length=64)
    predicted_decision: Literal["participate", "silent"]
    predicted_reason: str = Field(min_length=1, max_length=64)
    score: float
    minimum_score: float
    signals: dict[str, object] = Field(default_factory=dict, max_length=20)
    feedback_label: ParticipationFeedbackLabel


class SmartParticipationFeedbackView(BaseModel):
    id: str
    character_card_id: str
    feedback_label: ParticipationFeedbackLabel
    created_at: datetime

    @classmethod
    def from_record(
        cls, record: SmartParticipationFeedbackRecord
    ) -> "SmartParticipationFeedbackView":
        return cls(
            id=record.id,
            character_card_id=record.character_card_id,
            feedback_label=cast(ParticipationFeedbackLabel, record.feedback_label),
            created_at=record.created_at,
        )


def feedback_signals(record: SmartParticipationFeedbackRecord) -> dict[str, object]:
    try:
        value = json.loads(record.signals_json)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
