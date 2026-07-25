"""HTTP request and response schemas."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.domain import TestKind, TrialStatus, TrialSuiteResult
from echo_masque.persistence.models import TargetRecord, TrialRunRecord, TurnRecord


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_kind: str = Field(pattern="^(stable|fragile)$")
    config: dict[str, object] = Field(default_factory=dict)


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
            config=json.loads(record.config_json),
            created_at=record.created_at,
        )


class TrialStart(BaseModel):
    target_id: str
    suite: list[TestKind] = Field(default_factory=lambda: list(TestKind))


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
