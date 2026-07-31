"""Phase 16E rubric comparison and frozen Dataset coverage analytics."""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.calibration import CalibrationDatasetView, CoverageDimension
from echo_masque.evaluation_analytics import (
    ClassificationMetrics,
    JudgeEvaluationView,
    JudgePredictionView,
)
from echo_masque.persistence import CalibrationRepository, EvaluationRepository

CoverageStatus = Literal["missing", "weak", "covered"]
ComparisonClassification = Literal[
    "improved",
    "regressed",
    "mixed",
    "unchanged",
]

COVERAGE_DIMENSIONS: tuple[CoverageDimension, ...] = (
    "identity",
    "memory",
    "instruction_resistance",
    "capability_honesty",
    "persona",
    "language",
)
SEMANTIC_DIMENSION_MAP: dict[CoverageDimension, str] = {
    "identity": "identity_continuity",
    "memory": "memory_integrity",
    "instruction_resistance": "instruction_resistance",
    "capability_honesty": "capability_honesty",
    "persona": "persona_continuity",
    "language": "language_consistency",
}
MINIMUM_CASES_PER_DIMENSION = 3


class AuthoringGapSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: CoverageDimension
    risk_tags: list[str]
    scenario_categories: list[str]
    recommended_count: int = Field(ge=1, le=8)
    reason: str


class DimensionCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: CoverageDimension
    case_count: int
    pass_count: int
    fail_count: int
    review_count: int
    languages: dict[str, int]
    scenario_categories: dict[str, int]
    status: CoverageStatus
    semantic_prediction_count: int
    semantic_average_score: float | None


class DatasetCoverageReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_name: str
    dataset_version: int
    total_cases: int
    evaluation_id: str | None
    dimensions: list[DimensionCoverage]
    missing_dimensions: list[CoverageDimension]
    weak_dimensions: list[CoverageDimension]
    suggestions: list[AuthoringGapSuggestion]


class RubricComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_evaluation_id: str = Field(min_length=1, max_length=64)
    candidate_evaluation_id: str = Field(min_length=1, max_length=64)


class RubricDimensionDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    baseline_eligible: int
    candidate_eligible: int
    baseline_average: float | None
    candidate_average: float | None
    delta: float | None


class RubricPredictionChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    expected_verdict: str
    baseline_verdict: str | None
    candidate_verdict: str | None
    baseline_score: int | None
    candidate_score: int | None
    classification: ComparisonClassification


class RubricComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_name: str
    dataset_version: int
    baseline_evaluation_id: str
    candidate_evaluation_id: str
    baseline_rubric_version: str
    candidate_rubric_version: str
    baseline_metrics: ClassificationMetrics
    candidate_metrics: ClassificationMetrics
    accuracy_delta: float
    macro_f1_delta: float
    false_positive_rate_delta: float
    false_negative_rate_delta: float
    classification: ComparisonClassification
    dimension_deltas: list[RubricDimensionDelta]
    prediction_changes: list[RubricPredictionChange]


class CoverageAnalyticsService:
    def __init__(
        self,
        calibration_repository: CalibrationRepository,
        evaluation_repository: EvaluationRepository,
    ) -> None:
        self.calibration_repository = calibration_repository
        self.evaluation_repository = evaluation_repository

    def coverage(
        self,
        owner_id: str,
        dataset_id: str,
        evaluation_id: str | None = None,
    ) -> DatasetCoverageReport:
        dataset = self.calibration_repository.get_dataset(dataset_id, owner_id)
        if dataset is None:
            raise KeyError("Calibration Dataset not found.")
        if dataset.status != "approved":
            raise ValueError("Coverage requires an approved Calibration Dataset.")
        evaluation = None
        if evaluation_id is not None:
            evaluation = self.evaluation_repository.get(evaluation_id, owner_id)
            if evaluation is None:
                raise KeyError("Judge Evaluation Snapshot not found.")
            self._require_same_dataset(dataset, evaluation)

        dimensions = [
            self._dimension_coverage(dataset, dimension, evaluation)
            for dimension in COVERAGE_DIMENSIONS
        ]
        missing = [item.dimension for item in dimensions if item.status == "missing"]
        weak = [item.dimension for item in dimensions if item.status == "weak"]
        suggestions = [
            self._suggestion(item)
            for item in dimensions
            if item.status != "covered"
        ]
        return DatasetCoverageReport(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            total_cases=len(dataset.cases),
            evaluation_id=evaluation.id if evaluation is not None else None,
            dimensions=dimensions,
            missing_dimensions=missing,
            weak_dimensions=weak,
            suggestions=suggestions,
        )

    def compare_rubrics(
        self,
        owner_id: str,
        request: RubricComparisonRequest,
    ) -> RubricComparisonReport:
        baseline = self.evaluation_repository.get(
            request.baseline_evaluation_id,
            owner_id,
        )
        candidate = self.evaluation_repository.get(
            request.candidate_evaluation_id,
            owner_id,
        )
        if baseline is None or candidate is None:
            raise KeyError("Judge Evaluation Snapshot not found.")
        if (
            baseline.dataset_id != candidate.dataset_id
            or baseline.dataset_version != candidate.dataset_version
        ):
            raise ValueError(
                "Rubric comparison requires the same frozen Dataset ID and version."
            )
        baseline_metrics = baseline.metrics.by_mode["semantic"]
        candidate_metrics = candidate.metrics.by_mode["semantic"]
        if baseline_metrics.eligible == 0 or candidate_metrics.eligible == 0:
            raise ValueError(
                "Both Evaluation Snapshots require eligible Semantic predictions."
            )

        accuracy_delta = _delta(
            candidate_metrics.accuracy,
            baseline_metrics.accuracy,
        )
        macro_f1_delta = _delta(
            candidate_metrics.macro_f1,
            baseline_metrics.macro_f1,
        )
        false_positive_delta = _delta(
            candidate_metrics.false_positive_rate,
            baseline_metrics.false_positive_rate,
        )
        false_negative_delta = _delta(
            candidate_metrics.false_negative_rate,
            baseline_metrics.false_negative_rate,
        )
        return RubricComparisonReport(
            dataset_id=baseline.dataset_id,
            dataset_name=baseline.dataset_name,
            dataset_version=baseline.dataset_version,
            baseline_evaluation_id=baseline.id,
            candidate_evaluation_id=candidate.id,
            baseline_rubric_version=_rubric_version(baseline),
            candidate_rubric_version=_rubric_version(candidate),
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            accuracy_delta=accuracy_delta,
            macro_f1_delta=macro_f1_delta,
            false_positive_rate_delta=false_positive_delta,
            false_negative_rate_delta=false_negative_delta,
            classification=_overall_classification(
                accuracy_delta,
                macro_f1_delta,
                false_positive_delta,
                false_negative_delta,
            ),
            dimension_deltas=_dimension_deltas(baseline, candidate),
            prediction_changes=_prediction_changes(baseline, candidate),
        )

    @staticmethod
    def _require_same_dataset(
        dataset: CalibrationDatasetView,
        evaluation: JudgeEvaluationView,
    ) -> None:
        if (
            evaluation.dataset_id != dataset.id
            or evaluation.dataset_version != dataset.version
        ):
            raise ValueError(
                "Coverage Evaluation must use the same frozen Dataset ID and version."
            )

    @staticmethod
    def _dimension_coverage(
        dataset: CalibrationDatasetView,
        dimension: CoverageDimension,
        evaluation: JudgeEvaluationView | None,
    ) -> DimensionCoverage:
        cases = [
            item
            for item in dataset.cases
            if dimension in item.coverage_dimensions
        ]
        labels = Counter(item.expected_verdict for item in cases)
        languages = Counter(item.language for item in cases)
        categories = Counter(item.scenario_category for item in cases)
        scores: list[int] = []
        if evaluation is not None:
            case_ids = {item.id for item in cases}
            semantic_key = SEMANTIC_DIMENSION_MAP[dimension]
            scores = [
                item.dimensions[semantic_key]
                for item in evaluation.predictions
                if item.mode == "semantic"
                and item.case_id in case_ids
                and item.error is None
                and semantic_key in item.dimensions
            ]
        count = len(cases)
        status: CoverageStatus = (
            "missing"
            if count == 0
            else "weak"
            if count < MINIMUM_CASES_PER_DIMENSION
            else "covered"
        )
        return DimensionCoverage(
            dimension=dimension,
            case_count=count,
            pass_count=labels["PASS"],
            fail_count=labels["FAIL"],
            review_count=labels["REVIEW"],
            languages=dict(languages),
            scenario_categories=dict(categories),
            status=status,
            semantic_prediction_count=len(scores),
            semantic_average_score=(round(mean(scores), 4) if scores else None),
        )

    @staticmethod
    def _suggestion(item: DimensionCoverage) -> AuthoringGapSuggestion:
        mapping: dict[CoverageDimension, tuple[list[str], list[str]]] = {
            "identity": (["identity", "identity replacement"], ["identity_integrity"]),
            "memory": (["memory", "false shared memory"], ["false_memory"]),
            "instruction_resistance": (
                ["prompt injection", "instruction resistance"],
                ["prompt_injection"],
            ),
            "capability_honesty": (
                ["capability honesty", "unsupported capability"],
                ["capability_honesty"],
            ),
            "persona": (["persona drift", "tone continuity"], ["long_conversation_drift"]),
            "language": (
                ["multilingual consistency", "language switching"],
                ["language_consistency"],
            ),
        }
        risk_tags, categories = mapping[item.dimension]
        missing = max(1, MINIMUM_CASES_PER_DIMENSION - item.case_count)
        return AuthoringGapSuggestion(
            dimension=item.dimension,
            risk_tags=risk_tags,
            scenario_categories=categories,
            recommended_count=min(8, missing),
            reason=(
                f"{item.dimension} has {item.case_count} approved Cases; "
                f"at least {MINIMUM_CASES_PER_DIMENSION} are recommended."
            ),
        )


def _rubric_version(evaluation: JudgeEvaluationView) -> str:
    semantic = evaluation.judge_config.get("semantic")
    if isinstance(semantic, dict):
        value = semantic.get("rubric_version")
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _semantic_predictions(
    evaluation: JudgeEvaluationView,
) -> dict[str, JudgePredictionView]:
    return {
        item.case_id: item
        for item in evaluation.predictions
        if item.mode == "semantic" and item.error is None
    }


def _dimension_deltas(
    baseline: JudgeEvaluationView,
    candidate: JudgeEvaluationView,
) -> list[RubricDimensionDelta]:
    baseline_predictions = _semantic_predictions(baseline)
    candidate_predictions = _semantic_predictions(candidate)
    keys = sorted(
        {
            key
            for item in (*baseline_predictions.values(), *candidate_predictions.values())
            for key in item.dimensions
        }
    )
    results: list[RubricDimensionDelta] = []
    for key in keys:
        baseline_values = [
            item.dimensions[key]
            for item in baseline_predictions.values()
            if key in item.dimensions
        ]
        candidate_values = [
            item.dimensions[key]
            for item in candidate_predictions.values()
            if key in item.dimensions
        ]
        baseline_average = round(mean(baseline_values), 4) if baseline_values else None
        candidate_average = round(mean(candidate_values), 4) if candidate_values else None
        delta = (
            _delta(candidate_average, baseline_average)
            if candidate_average is not None and baseline_average is not None
            else None
        )
        results.append(
            RubricDimensionDelta(
                dimension=key,
                baseline_eligible=len(baseline_values),
                candidate_eligible=len(candidate_values),
                baseline_average=baseline_average,
                candidate_average=candidate_average,
                delta=delta,
            )
        )
    return results


def _prediction_changes(
    baseline: JudgeEvaluationView,
    candidate: JudgeEvaluationView,
) -> list[RubricPredictionChange]:
    baseline_predictions = _semantic_predictions(baseline)
    candidate_predictions = _semantic_predictions(candidate)
    shared = sorted(set(baseline_predictions) & set(candidate_predictions))
    changes: list[RubricPredictionChange] = []
    for case_id in shared:
        left = baseline_predictions[case_id]
        right = candidate_predictions[case_id]
        baseline_correct = left.predicted_verdict == left.expected_verdict
        candidate_correct = right.predicted_verdict == right.expected_verdict
        classification: ComparisonClassification = (
            "improved"
            if not baseline_correct and candidate_correct
            else "regressed"
            if baseline_correct and not candidate_correct
            else "unchanged"
            if left.predicted_verdict == right.predicted_verdict
            else "mixed"
        )
        changes.append(
            RubricPredictionChange(
                case_id=case_id,
                expected_verdict=left.expected_verdict,
                baseline_verdict=left.predicted_verdict,
                candidate_verdict=right.predicted_verdict,
                baseline_score=left.score,
                candidate_score=right.score,
                classification=classification,
            )
        )
    return changes


def _overall_classification(
    accuracy_delta: float,
    macro_f1_delta: float,
    false_positive_delta: float,
    false_negative_delta: float,
) -> ComparisonClassification:
    improvements = (
        accuracy_delta > 0,
        macro_f1_delta > 0,
        false_positive_delta < 0,
        false_negative_delta < 0,
    )
    regressions = (
        accuracy_delta < 0,
        macro_f1_delta < 0,
        false_positive_delta > 0,
        false_negative_delta > 0,
    )
    if any(improvements) and not any(regressions):
        return "improved"
    if any(regressions) and not any(improvements):
        return "regressed"
    if not any(improvements) and not any(regressions):
        return "unchanged"
    return "mixed"


def _delta(candidate: float, baseline: float) -> float:
    return round(candidate - baseline, 4)


__all__ = [
    "COVERAGE_DIMENSIONS",
    "CoverageAnalyticsService",
    "DatasetCoverageReport",
    "RubricComparisonReport",
    "RubricComparisonRequest",
]
