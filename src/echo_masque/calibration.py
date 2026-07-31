"""Human-controlled calibration dataset contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CalibrationDatasetStatus = Literal["draft", "approved", "archived"]
CalibrationVerdict = Literal["PASS", "FAIL", "REVIEW"]
CalibrationSource = Literal["manual", "run"]
CalibrationLanguage = Literal["en", "zh-CN"]
CoverageDimension = Literal[
    "identity",
    "memory",
    "instruction_resistance",
    "capability_honesty",
    "persona",
    "language",
]


class CalibrationDatasetFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class CalibrationDatasetCreate(CalibrationDatasetFields):
    pass


class CalibrationDatasetUpdate(CalibrationDatasetFields):
    pass


class CalibrationCaseFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str | None = Field(default=None, max_length=120)
    character_card_id: str | None = Field(default=None, max_length=64)
    scenario_name: str = Field(min_length=1, max_length=160)
    scenario_category: str = Field(min_length=1, max_length=80)
    language: CalibrationLanguage
    turn_index: int | None = Field(default=None, ge=0)
    tester_message: str = Field(default="", max_length=12000)
    subject_response: str = Field(min_length=1, max_length=30000)
    expected_verdict: CalibrationVerdict
    failure_type: str = Field(default="", max_length=100)
    evidence_excerpt: str = Field(default="", max_length=8000)
    coverage_dimensions: list[CoverageDimension] = Field(
        default_factory=list,
        max_length=6,
    )
    notes: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def validate_grounding(self) -> CalibrationCaseFields:
        self.failure_type = self.failure_type.strip()
        self.evidence_excerpt = self.evidence_excerpt.strip()
        self.coverage_dimensions = list(dict.fromkeys(self.coverage_dimensions))
        if self.expected_verdict in {"FAIL", "REVIEW"}:
            if not self.failure_type:
                raise ValueError("FAIL and REVIEW cases require a failure type.")
            if not self.evidence_excerpt:
                raise ValueError("FAIL and REVIEW cases require grounded evidence.")
        if self.evidence_excerpt and self.evidence_excerpt not in self.subject_response:
            raise ValueError(
                "Evidence must be an exact contiguous excerpt of the Subject response."
            )
        return self


class CalibrationCaseCreate(CalibrationCaseFields):
    pass


class CalibrationCaseUpdate(CalibrationCaseFields):
    pass


class CalibrationRunImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=64)
    scenario_id: str = Field(min_length=1, max_length=120)
    turn_index: int = Field(ge=0)
    expected_verdict: CalibrationVerdict
    failure_type: str = Field(default="", max_length=100)
    evidence_excerpt: str = Field(default="", max_length=8000)
    coverage_dimensions: list[CoverageDimension] = Field(
        default_factory=list,
        max_length=6,
    )
    notes: str = Field(default="", max_length=8000)


class CalibrationCaseView(CalibrationCaseFields):
    id: str
    dataset_id: str
    owner_id: str
    position: int
    source: CalibrationSource
    run_id: str | None
    created_at: datetime
    updated_at: datetime


class CalibrationDatasetView(CalibrationDatasetFields):
    id: str
    owner_id: str
    lineage_id: str
    parent_dataset_id: str | None
    version: int
    status: CalibrationDatasetStatus
    cases: list[CalibrationCaseView]
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    archived_at: datetime | None


class CalibrationArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    exported_at: datetime
    owner_id: str
    datasets: list[CalibrationDatasetView]


class CalibrationArchiveImport(BaseModel):
    archive: CalibrationArchive
    mode: Literal["merge", "replace"] = "merge"


class CalibrationImportResult(BaseModel):
    imported: dict[str, int]
    skipped: dict[str, int]
