"""Typed advisory contracts shared by Utility Gateway consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

UtilityHealth = Literal[
    "unknown",
    "healthy",
    "degraded",
    "unavailable",
    "cooling_down",
    "exhausted",
]
UtilityTier = Literal["free", "paid"]


class UtilityQuotaDimension(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    remaining: float | None = None
    limit: float | None = None
    unit: str = ""
    reset_at: datetime | None = None
    window_seconds: int | None = None
    source: str = "response_header"
    observed_at: datetime | None = None


class UtilityProviderSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_id: str
    provider: str
    model: str
    configured: bool
    status: UtilityHealth = "unknown"
    remaining_value: float | None = None
    remaining_unit: str = ""
    reset_at: datetime | None = None
    observation_source: str = "none"
    latency_ms: float = 0.0
    error_rate: float = 0.0
    cooldown_until: datetime | None = None
    last_error: str = ""
    last_observed_at: datetime | None = None
    quota_dimensions: tuple[UtilityQuotaDimension, ...] = ()


class UtilityGatewaySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool
    members: tuple[UtilityProviderSnapshot, ...]
    paid_fallback_enabled: bool
    daily_cost_usd: float = 0.0
    monthly_cost_usd: float = 0.0


class RagUtilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    need_knowledge: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str = Field(default="", max_length=80)


class MemoryUtilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["ignore", "create", "reinforce", "supersede", "merge"]
    confidence: float = Field(ge=0.0, le=1.0)
    memory_type: Literal[
        "preference",
        "fact",
        "relationship",
        "goal",
        "event",
        "other",
    ] = "other"
    content: str = Field(default="", max_length=1200)
    target_memory_id: str = Field(default="", max_length=64)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    reason_code: str = Field(default="", max_length=80)


class ContextCompileDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    include_topic: bool = True
    include_memory: bool = True
    include_knowledge: bool = False
    include_media_recall: bool = False
    conversation_budget: int = Field(default=700, ge=200, le=1800)
    knowledge_budget: int = Field(default=700, ge=0, le=1200)
    reason_code: str = Field(default="", max_length=80)


class ParticipationUtilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deployment_id: str = Field(default="", max_length=64)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str = Field(default="", max_length=80)


class TurnDirectorReadRequest(BaseModel):
    """A bounded request for Runtime-owned internal context only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: Literal["memory.search", "conversation.search", "knowledge.search"]
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=2, ge=1, le=4)


class TurnDirectorProposal(BaseModel):
    """Advisory plan for one already-admitted V3 Character turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response_mode: Literal["answer", "continue", "acknowledge", "clarify"]
    response_posture: Literal[
        "informed_response",
        "respond_to_challenge",
        "group_participant",
        "casual_peer",
        "role_peer",
        "cautious_peer",
    ]
    focus_message_ids: tuple[str, ...] = Field(default=(), max_length=3)
    read_requests: tuple[TurnDirectorReadRequest, ...] = Field(default=(), max_length=2)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str = Field(default="", max_length=80)


class ToolContinuationUtilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    continue_action: bool
    tool_id: str = Field(default="", max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str = Field(default="", max_length=80)


class SummaryUtilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=4000)
    open_loops: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


class WikiUtilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=12000)
    keywords: tuple[str, ...] = ()
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


@dataclass(frozen=True, slots=True)
class UtilityRoute:
    member_id: str
    provider: str
    model: str
    base_url: str
    tier: UtilityTier
    api_key: SecretStr
    reason: str


@dataclass(frozen=True, slots=True)
class UtilityInferenceResult:
    value: BaseModel
    route: UtilityRoute
    latency_ms: int
    attempts: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class UtilityGatewayUnavailable(RuntimeError):
    """No safe Utility provider path produced a valid advisory result."""


__all__ = [
    "ContextCompileDecision",
    "MemoryUtilityDecision",
    "ParticipationUtilityDecision",
    "RagUtilityDecision",
    "SummaryUtilityResult",
    "ToolContinuationUtilityDecision",
    "TurnDirectorProposal",
    "TurnDirectorReadRequest",
    "UtilityGatewaySnapshot",
    "UtilityGatewayUnavailable",
    "UtilityHealth",
    "UtilityInferenceResult",
    "UtilityProviderSnapshot",
    "UtilityQuotaDimension",
    "UtilityRoute",
    "UtilityTier",
    "WikiUtilityResult",
]
