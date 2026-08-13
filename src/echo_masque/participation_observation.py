"""Bounded Connector-to-Runtime participation diagnostics."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ParticipationTurnObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deployment_id: str = Field(min_length=1, max_length=64)
    role: str = Field(default="primary", max_length=40)
    order: int = Field(default=1, ge=1, le=10)


class ParticipationCandidateObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deployment_id: str = Field(min_length=1, max_length=64)
    character_card_id: str = Field(default="", max_length=64)
    character_name: str = Field(default="", max_length=160)
    score: float | None = None
    minimum_score: float = 0.0
    eligible: bool = False
    semantic_relevance: float | None = None
    signals: dict[str, float] = Field(default_factory=dict, max_length=20)
    matched_topics: list[str] = Field(default_factory=list, max_length=12)
    matched_keywords: list[str] = Field(default_factory=list, max_length=12)
    matched_trigger_phrases: list[str] = Field(default_factory=list, max_length=12)
    matched_avoid_phrases: list[str] = Field(default_factory=list, max_length=12)


class ParticipationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["smart", "explicit", "lightweight"] = "smart"
    reason: str = Field(default="", max_length=80)
    selected_deployment_ids: list[str] = Field(default_factory=list, max_length=8)
    turns: list[ParticipationTurnObservation] = Field(default_factory=list, max_length=8)
    candidates: list[ParticipationCandidateObservation] = Field(default_factory=list, max_length=12)
    minimum_margin: float | None = None


__all__ = [
    "ParticipationCandidateObservation",
    "ParticipationObservation",
    "ParticipationTurnObservation",
]
