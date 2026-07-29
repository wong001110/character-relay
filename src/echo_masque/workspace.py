"""Custom scenario, test-pack, experiment, and workspace contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.domain import JudgeMode, Severity, TestKind, TestLanguage, TrialScenario

TesterMode = Literal["benchmark", "adaptive"]


class ScenarioFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    category: TestKind
    description: str = Field(default="", max_length=2000)
    language: TestLanguage = TestLanguage.ENGLISH
    messages: list[str] = Field(min_length=1, max_length=20)
    expected_behavior: str = Field(min_length=1, max_length=4000)
    forbidden_phrases: list[str] = Field(default_factory=list, max_length=30)
    required_phrases: list[str] = Field(default_factory=list, max_length=30)
    severity: Severity = Severity.MEDIUM
    max_turns: int = Field(default=4, ge=1, le=12)
    recommended_tester_mode: TesterMode = "benchmark"
    recommended_judge_mode: JudgeMode = JudgeMode.HYBRID

    @model_validator(mode="after")
    def normalize_text_lists(self) -> "ScenarioFields":
        messages = _clean(self.messages)
        forbidden = _clean(self.forbidden_phrases)
        required = _clean(self.required_phrases)
        if not messages:
            raise ValueError("At least one non-empty Tester message is required.")
        self.messages = messages
        self.forbidden_phrases = forbidden
        self.required_phrases = required
        return self


class ScenarioCreate(ScenarioFields):
    pass


class ScenarioUpdate(ScenarioFields):
    pass


class ScenarioView(ScenarioFields):
    # SQLAlchemy records expose string-backed enums; Pydantic normalizes them on use.
    category: TestKind | str
    language: TestLanguage | str = TestLanguage.ENGLISH
    severity: Severity | str = Severity.MEDIUM
    recommended_tester_mode: TesterMode | str = "benchmark"
    recommended_judge_mode: JudgeMode | str = JudgeMode.HYBRID
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime

    def to_trial_scenario(self) -> TrialScenario:
        return TrialScenario(
            id=self.id,
            name=self.name,
            kind=TestKind(self.category),
            language=TestLanguage(self.language),
            messages=tuple(self.messages),
            expected_behavior=self.expected_behavior,
            forbidden_phrases=tuple(self.forbidden_phrases),
            required_phrases=tuple(self.required_phrases),
        )


class PackItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1, max_length=64)
    enabled: bool = True


class TestPackFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=3000)
    items: list[PackItemInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_scenarios(self) -> "TestPackFields":
        ids = [item.scenario_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("A scenario may appear only once in a Test Pack.")
        return self


class TestPackCreate(TestPackFields):
    pass


class TestPackUpdate(TestPackFields):
    pass


class PackScenarioView(BaseModel):
    scenario: ScenarioView
    position: int
    enabled: bool


class TestPackView(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str
    version: int
    items: list[PackScenarioView]
    created_at: datetime
    updated_at: datetime

    def scenarios_for(self, language: TestLanguage) -> tuple[TrialScenario, ...]:
        return tuple(
            item.scenario.to_trial_scenario()
            for item in sorted(self.items, key=lambda value: value.position)
            if item.enabled and TestLanguage(item.scenario.language) == language
        )


class RunSnapshotView(BaseModel):
    run_id: str
    owner_id: str
    character_card_id: str | None
    test_pack_id: str | None
    character: dict[str, object]
    target: dict[str, object]
    test_pack: dict[str, object]
    scenarios: list[dict[str, object]]
    rerun_of: str | None
    is_baseline: bool
    created_at: datetime


class ExperimentHistoryItem(BaseModel):
    run_id: str
    status: str
    character_card_id: str | None
    character_name: str
    test_pack_id: str | None
    test_pack_name: str | None
    test_language: TestLanguage
    tester_mode: TesterMode
    judge_mode: JudgeMode
    score: float | None
    passed: bool | None
    review_required: bool
    is_baseline: bool
    rerun_of: str | None
    created_at: datetime
    updated_at: datetime


class ExperimentHistoryPage(BaseModel):
    items: list[ExperimentHistoryItem]
    page: int
    page_size: int
    total: int
    pages: int


class StorageDiagnostics(BaseModel):
    environment: str
    database_url_redacted: str
    database_kind: str
    database_path: str | None
    writable: bool
    persistent_path_expected: bool
    persistent_path_configured: bool
    warning: str | None
    character_count: int
    scenario_count: int
    pack_count: int
    run_count: int
    last_write_at: datetime | None


class PersistenceProbeView(BaseModel):
    id: str
    marker: str
    created_at: datetime


class WorkspaceArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    exported_at: datetime
    owner_id: str
    targets: list[dict[str, object]]
    character_cards: list[dict[str, object]]
    scenarios: list[dict[str, object]]
    test_packs: list[dict[str, object]]
    trial_runs: list[dict[str, object]]
    character_trials: list[dict[str, object]]
    run_snapshots: list[dict[str, object]]
    turns: list[dict[str, object]]
    events: list[dict[str, object]]
    evidence: list[dict[str, object]]
    admin_runtime: dict[str, object] | None = None


class WorkspaceImportRequest(BaseModel):
    archive: WorkspaceArchive
    mode: Literal["merge", "replace"] = "merge"


class WorkspaceImportResult(BaseModel):
    imported: dict[str, int]
    skipped: dict[str, int]


def _clean(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result
