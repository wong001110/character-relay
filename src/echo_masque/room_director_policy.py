"""Operator-reviewed evidence binding for ambient Room Director activation."""

from __future__ import annotations

from datetime import timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class DirectorQualification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=240)
    observed_model: str = Field(min_length=1, max_length=240)
    prompt_version: str = Field(min_length=1, max_length=100)
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int = Field(ge=200)
    expected_none_count: int = Field(ge=30)
    expected_contribution_count: int = Field(ge=30)
    labels_human_reviewed: bool = False
    labels_reviewed_by: str = Field(min_length=1, max_length=160)
    none_precision: float = Field(ge=0, le=1, allow_inf_nan=False)
    none_recall: float = Field(ge=0, le=1, allow_inf_nan=False)
    joint_speaker_target_accuracy: float = Field(ge=0, le=1, allow_inf_nan=False)
    missed_direct_responses: int = Field(ge=0)
    scope_violations: int = Field(ge=0)
    approved_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bounded_evidence_lifetime(self) -> DirectorQualification:
        if not self.approved_at < self.expires_at <= self.approved_at + timedelta(days=14):
            raise ValueError("Qualification must expire within fourteen days of approval.")
        if self.expected_none_count + self.expected_contribution_count > self.case_count:
            raise ValueError("Qualification strata exceed the measured corpus.")
        return self

    def meets_gate(self) -> bool:
        # Conservative starting gates, not empirical guarantees of natural conversation.
        return (
            self.labels_human_reviewed
            and self.none_precision >= 0.90
            and self.none_recall >= 0.80
            and self.joint_speaker_target_accuracy >= 0.85
            and self.missed_direct_responses == 0
            and self.scope_violations == 0
        )


class RoomDirectorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    deadline_seconds: float = Field(default=6.0, ge=0.5, le=10.0, allow_inf_nan=False)
    max_attempts: int = Field(default=2, ge=1, le=2)
    qualifications: tuple[DirectorQualification, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def unique_members(self) -> RoomDirectorPolicy:
        members = [item.member_id for item in self.qualifications]
        if len(members) != len(set(members)):
            raise ValueError("One current qualification per pool member is permitted.")
        return self
