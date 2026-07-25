"""Models for reproducible run comparison and regression gates."""

from pydantic import BaseModel, ConfigDict, Field


class RegressionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_score_drop: float = Field(default=5.0, ge=0)
    max_latency_increase_percent: float = Field(default=50.0, ge=0)
    allow_new_failures: bool = False


class ScenarioChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    baseline_score: int
    candidate_score: int
    score_delta: int
    baseline_breakpoint: int | None
    candidate_breakpoint: int | None
    baseline_passed: bool
    candidate_passed: bool
    evidence_delta: int


class ComparisonResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_score: float
    candidate_score: float
    score_delta: float
    baseline_average_latency_ms: float
    candidate_average_latency_ms: float
    latency_change_percent: float
    baseline_total_tokens: int
    candidate_total_tokens: int
    token_delta: int
    new_failures: tuple[str, ...]
    resolved_failures: tuple[str, ...]
    scenario_changes: tuple[ScenarioChange, ...]
    gate_passed: bool
    gate_violations: tuple[str, ...]
