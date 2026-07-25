"""HTTP request and response schemas."""

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.domain import TestKind, TrialStatus, TrialSuiteResult
from echo_masque.persistence.models import (
    CharacterCardRecord,
    TargetRecord,
    TrialEventRecord,
    TrialRunRecord,
    TurnRecord,
)
from echo_masque.security import redact
from echo_masque.targets import HttpTargetConfig
from echo_masque.transcripts import TranscriptFormat


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_kind: str = Field(pattern="^(stable|fragile|http)$")
    config: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self) -> "TargetCreate":
        if self.target_kind == "http":
            HttpTargetConfig.model_validate(self.config)
        return self


class TargetView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    target_kind: str
    config: dict[str, object]
    created_at: datetime

    @classmethod
    def from_record(cls, record: TargetRecord) -> "TargetView":
        return cls(
            id=record.id,
            name=record.name,
            target_kind=record.target_kind,
            config=_safe_config(record.config_json),
            created_at=record.created_at,
        )


class CharacterCardCreate(BaseModel):
    target_id: str
    display_name: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=180)
    subject_type: str = Field(default="custom", pattern="^(companion|npc|assistant|custom)$")
    persona_summary: str = Field(default="", max_length=2000)
    traits: list[str] = Field(default_factory=list, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=12)
    expected_tone: str | None = Field(default=None, max_length=500)
    forbidden_behaviors: list[str] = Field(default_factory=list, max_length=20)
    memory_summary: str | None = Field(default=None, max_length=2000)
    preferred_suites: list[TestKind] = Field(default_factory=lambda: list(TestKind))
    portrait_variant: str = Field(default="lavender", pattern="^(lavender|rose|mint|night)$")


class CharacterCardView(BaseModel):
    id: str
    owner_id: str
    target_id: str
    display_name: str
    subtitle: str
    subject_type: str
    persona_summary: str
    traits: list[str]
    tags: list[str]
    expected_tone: str | None
    forbidden_behaviors: list[str]
    memory_summary: str | None
    preferred_suites: list[TestKind]
    portrait_variant: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: CharacterCardRecord) -> "CharacterCardView":
        return cls(
            id=record.id,
            owner_id=record.owner_id,
            target_id=record.target_id,
            display_name=record.display_name,
            subtitle=record.subtitle,
            subject_type=record.subject_type,
            persona_summary=record.persona_summary,
            traits=_string_list(record.traits_json),
            tags=_string_list(record.tags_json),
            expected_tone=record.expected_tone,
            forbidden_behaviors=_string_list(record.forbidden_behaviors_json),
            memory_summary=record.memory_summary,
            preferred_suites=[
                TestKind(item) for item in _string_list(record.preferred_suites_json)
            ],
            portrait_variant=record.portrait_variant,
            created_at=record.created_at,
        )


class TrialStart(BaseModel):
    target_id: str | None = None
    character_card_id: str | None = None
    suite: list[TestKind] = Field(default_factory=lambda: list(TestKind))
    mode: Literal["watch", "fast"] = "watch"

    @model_validator(mode="after")
    def require_target(self) -> "TrialStart":
        if self.target_id is None and self.character_card_id is None:
            raise ValueError("target_id or character_card_id is required")
        return self


class TrialRunView(BaseModel):
    id: str
    target_id: str
    status: TrialStatus
    suite: list[TestKind]
    result: TrialSuiteResult | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: TrialRunRecord) -> "TrialRunView":
        return cls(
            id=record.id,
            target_id=record.target_id,
            status=TrialStatus(record.status),
            suite=[TestKind(item) for item in json.loads(record.suite_json)],
            result=(
                TrialSuiteResult.model_validate_json(record.result_json)
                if record.result_json
                else None
            ),
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class TrialEventView(BaseModel):
    sequence: int
    event_type: str
    scenario_id: str | None
    turn_index: int | None
    payload: dict[str, object]
    created_at: datetime

    @classmethod
    def from_record(cls, record: TrialEventRecord) -> "TrialEventView":
        return cls(
            sequence=record.sequence,
            event_type=record.event_type,
            scenario_id=record.scenario_id,
            turn_index=record.turn_index,
            payload=cast(dict[str, object], redact(json.loads(record.payload_json))),
            created_at=record.created_at,
        )


class ReplayTurn(BaseModel):
    scenario_id: str
    turn_index: int
    tester_message: str
    target_response: str
    latency_ms: int | None
    trace: dict[str, object]

    @classmethod
    def from_record(cls, record: TurnRecord) -> "ReplayTurn":
        return cls(
            scenario_id=record.scenario_id,
            turn_index=record.turn_index,
            tester_message=record.tester_message,
            target_response=record.target_response,
            latency_ms=record.latency_ms,
            trace=json.loads(record.trace_json),
        )


class TranscriptAnalyzeRequest(BaseModel):
    format: TranscriptFormat
    content: str = Field(min_length=1)
    subject_name: str = Field(default="Imported subject", min_length=1, max_length=120)
    suite: list[TestKind] = Field(default_factory=lambda: list(TestKind))


def _string_list(raw: str) -> list[str]:
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return cast(list[str], value)


def _safe_config(raw: str) -> dict[str, object]:
    value = redact(json.loads(raw))
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, object], value)


class ComparisonRequest(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    max_score_drop: float = Field(default=5.0, ge=0)
    max_latency_increase_percent: float = Field(default=50.0, ge=0)
    allow_new_failures: bool = False
