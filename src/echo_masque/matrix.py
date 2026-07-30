"""Phase 14 experiment-matrix, prompt-version, and analytics contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from echo_masque.domain import JudgeMode, TestLanguage

TesterMode = Literal["benchmark", "adaptive"]
ExportFormat = Literal["json", "csv", "markdown"]
MAX_MATRIX_TASKS = 200


class MatrixStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MatrixTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MatrixSubjectSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_card_id: str = Field(min_length=1, max_length=64)
    prompt_version_ids: list[str] = Field(default_factory=list, max_length=20)


class MatrixDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[MatrixSubjectSelection] = Field(min_length=1, max_length=20)
    model_overrides: list[str] = Field(default_factory=list, max_length=20)
    temperatures: list[float] = Field(default_factory=list, max_length=20)
    test_pack_ids: list[str] = Field(min_length=1, max_length=20)
    test_languages: list[TestLanguage] = Field(min_length=1, max_length=2)
    tester_modes: list[TesterMode] = Field(min_length=1, max_length=2)
    judge_modes: list[JudgeMode] = Field(min_length=1, max_length=3)
    repeat_count: int = Field(default=1, ge=1, le=10)
    concurrency: int = Field(default=1, ge=1, le=4)
    max_attempts: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def normalize_combinations(self) -> MatrixDefinition:
        self.model_overrides = _unique_text(self.model_overrides)
        self.temperatures = _unique_numbers(self.temperatures)
        self.test_pack_ids = _unique_text(self.test_pack_ids)
        self.test_languages = list(dict.fromkeys(self.test_languages))
        self.tester_modes = list(dict.fromkeys(self.tester_modes))
        self.judge_modes = list(dict.fromkeys(self.judge_modes))
        seen_cards: set[str] = set()
        for subject in self.subjects:
            if subject.character_card_id in seen_cards:
                raise ValueError("A Character Card may appear only once in a Matrix definition.")
            seen_cards.add(subject.character_card_id)
            subject.prompt_version_ids = _unique_text(subject.prompt_version_ids)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subject_variant_count(self) -> int:
        return sum(max(1, len(item.prompt_version_ids)) for item in self.subjects)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def task_count(self) -> int:
        dimensions = (
            self.subject_variant_count,
            max(1, len(self.model_overrides)),
            max(1, len(self.temperatures)),
            len(self.test_pack_ids),
            len(self.test_languages),
            len(self.tester_modes),
            len(self.judge_modes),
            self.repeat_count,
        )
        total = 1
        for value in dimensions:
            total *= value
        return total


class MatrixFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=3000)
    definition: MatrixDefinition


class MatrixCreate(MatrixFields):
    pass


class MatrixUpdate(MatrixFields):
    pass


class MatrixLaunch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed_task_count: int = Field(ge=1, le=MAX_MATRIX_TASKS)


class MatrixPreview(BaseModel):
    task_count: int
    maximum_task_count: int = MAX_MATRIX_TASKS
    within_limit: bool
    requires_adaptive: bool
    requires_semantic: bool
    subject_variants: int
    model_variants: int
    temperature_variants: int
    pack_variants: int
    language_variants: int
    tester_variants: int
    judge_variants: int
    repeats: int


class PromptVersionView(BaseModel):
    id: str
    owner_id: str
    character_card_id: str
    version: int
    label: str
    provider: str
    base_url: str
    model: str
    system_prompt: str
    temperature: float
    config_hash: str
    is_active: bool
    is_production: bool
    created_at: datetime


class PromptVersionDiff(BaseModel):
    left: PromptVersionView
    right: PromptVersionView
    changed_fields: list[str]
    system_prompt_before: str
    system_prompt_after: str


class MatrixTaskCombination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_card_id: str
    prompt_version_id: str | None
    model_override: str | None
    temperature: float | None
    test_pack_id: str
    test_language: TestLanguage
    tester_mode: TesterMode
    judge_mode: JudgeMode
    repeat_index: int = Field(ge=1)


class MatrixTaskView(BaseModel):
    id: str
    matrix_id: str
    ordinal: int
    status: MatrixTaskStatus
    combination: MatrixTaskCombination
    run_id: str | None
    attempt_count: int
    max_attempts: int
    retry_count: int
    backoff_seconds: int
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class MatrixView(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str
    status: MatrixStatus
    definition: MatrixDefinition
    total_tasks: int
    pending_tasks: int
    running_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    is_baseline: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class MatrixListPage(BaseModel):
    items: list[MatrixView]
    page: int
    page_size: int
    total: int
    pages: int


class DistributionItem(BaseModel):
    key: str
    count: int


class MatrixVariantAnalytics(BaseModel):
    key: str
    label: str
    run_count: int
    mean_score: float | None
    minimum_score: float | None
    maximum_score: float | None
    standard_deviation: float | None
    pass_rate: float
    review_rate: float
    failure_rate: float
    input_tokens: int
    output_tokens: int
    latency_ms: int


class MatrixAnalytics(BaseModel):
    matrix_id: str
    matrix_name: str
    status: MatrixStatus
    total_tasks: int
    completed_runs: int
    failed_tasks: int
    cancelled_tasks: int
    mean_score: float | None
    minimum_score: float | None
    maximum_score: float | None
    variance: float | None
    standard_deviation: float | None
    pass_rate: float
    review_rate: float
    failure_rate: float
    input_tokens: int
    output_tokens: int
    latency_ms: int
    provider_errors: int
    retry_count: int
    failure_types: list[DistributionItem]
    breakpoints: list[DistributionItem]
    scenarios: list[MatrixVariantAnalytics]
    by_character: list[MatrixVariantAnalytics]
    by_prompt_version: list[MatrixVariantAnalytics]
    by_model: list[MatrixVariantAnalytics]
    by_temperature: list[MatrixVariantAnalytics]
    by_language: list[MatrixVariantAnalytics]
    by_tester: list[MatrixVariantAnalytics]
    by_judge: list[MatrixVariantAnalytics]


class MatrixComparison(BaseModel):
    baseline: MatrixAnalytics
    candidate: MatrixAnalytics
    compatible: bool
    incompatibilities: list[str]
    score_delta: float | None
    pass_rate_delta: float
    review_rate_delta: float
    failure_rate_delta: float
    latency_delta_ms: int
    input_token_delta: int
    output_token_delta: int
    classification: Literal["improved", "no_meaningful_change", "regression", "incompatible"]


def preview_for(definition: MatrixDefinition) -> MatrixPreview:
    return MatrixPreview(
        task_count=definition.task_count,
        within_limit=definition.task_count <= MAX_MATRIX_TASKS,
        requires_adaptive="adaptive" in definition.tester_modes,
        requires_semantic=any(
            item in {JudgeMode.SEMANTIC, JudgeMode.HYBRID}
            for item in definition.judge_modes
        ),
        subject_variants=definition.subject_variant_count,
        model_variants=max(1, len(definition.model_overrides)),
        temperature_variants=max(1, len(definition.temperatures)),
        pack_variants=len(definition.test_pack_ids),
        language_variants=len(definition.test_languages),
        tester_variants=len(definition.tester_modes),
        judge_variants=len(definition.judge_modes),
        repeats=definition.repeat_count,
    )


def _unique_text(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _unique_numbers(values: list[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        if not 0.0 <= value <= 2.0:
            raise ValueError("Matrix temperatures must be between 0 and 2.")
        normalized = round(float(value), 4)
        if normalized not in result:
            result.append(normalized)
    return result
