"""Immutable Judge evaluation contracts and metric calculation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvaluationMode = Literal["rules", "semantic", "hybrid"]
EvaluationVerdict = Literal["PASS", "FAIL", "REVIEW"]
EvaluationStatus = Literal["completed", "partial", "failed"]
ContractSource = Literal["run_snapshot", "current_character", "generic"]


def _default_evaluation_modes() -> list[EvaluationMode]:
    return ["rules", "semantic", "hybrid"]


class JudgeEvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=64)
    modes: list[EvaluationMode] = Field(
        default_factory=_default_evaluation_modes,
        min_length=1,
        max_length=3,
    )

    @field_validator("modes")
    @classmethod
    def unique_modes(cls, values: list[EvaluationMode]) -> list[EvaluationMode]:
        return list(dict.fromkeys(values))


class JudgePredictionView(BaseModel):
    id: str
    evaluation_id: str
    case_id: str
    mode: EvaluationMode
    expected_verdict: EvaluationVerdict
    predicted_verdict: EvaluationVerdict | None
    score: int | None
    confidence: float | None
    failure_types: list[str]
    dimensions: dict[str, int]
    evidence: list[dict[str, object]]
    contract_source: ContractSource
    error: str | None
    created_at: datetime


class ClassificationMetrics(BaseModel):
    eligible: int
    correct: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    false_positive_count: int
    false_positive_rate: float
    false_negative_count: int
    false_negative_rate: float
    confusion: dict[str, dict[str, int]]
    per_class: dict[str, dict[str, float]]


class JudgeAgreementMetrics(BaseModel):
    eligible: int
    agreements: int
    disagreements: int
    agreement_rate: float


class JudgeEvaluationMetrics(BaseModel):
    by_mode: dict[str, ClassificationMetrics]
    rules_semantic_agreement: JudgeAgreementMetrics
    by_failure_type: dict[str, dict[str, ClassificationMetrics]]
    by_language: dict[str, dict[str, ClassificationMetrics]]
    by_scenario_category: dict[str, dict[str, ClassificationMetrics]]
    by_character: dict[str, dict[str, ClassificationMetrics]]


class JudgeEvaluationView(BaseModel):
    id: str
    owner_id: str
    dataset_id: str
    dataset_version: int
    dataset_name: str
    modes: list[EvaluationMode]
    judge_config: dict[str, object]
    metrics: JudgeEvaluationMetrics
    status: EvaluationStatus
    predictions: list[JudgePredictionView]
    created_at: datetime


class EvaluationCaseMetadata(BaseModel):
    case_id: str
    failure_type: str
    language: str
    scenario_category: str
    character_key: str


def classification_metrics(
    predictions: list[JudgePredictionView],
) -> ClassificationMetrics:
    labels: tuple[EvaluationVerdict, ...] = ("PASS", "FAIL", "REVIEW")
    eligible = [
        item
        for item in predictions
        if item.predicted_verdict is not None and item.error is None
    ]
    confusion: dict[str, dict[str, int]] = {
        expected: {predicted: 0 for predicted in labels}
        for expected in labels
    }
    for item in eligible:
        predicted = item.predicted_verdict
        if predicted is None:
            continue
        confusion[item.expected_verdict][predicted] += 1

    correct = sum(confusion[label][label] for label in labels)
    per_class: dict[str, dict[str, float]] = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(
            confusion[other][label]
            for other in labels
            if other != label
        )
        false_negative = sum(
            confusion[label][other]
            for other in labels
            if other != label
        )
        precision = _ratio(true_positive, true_positive + false_positive)
        recall = _ratio(true_positive, true_positive + false_negative)
        f1 = _ratio(2 * precision * recall, precision + recall)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(sum(confusion[label].values())),
        }

    false_positive_count = sum(
        1
        for item in eligible
        if item.expected_verdict != "FAIL" and item.predicted_verdict == "FAIL"
    )
    false_positive_denominator = sum(
        1 for item in eligible if item.expected_verdict != "FAIL"
    )
    false_negative_count = sum(
        1
        for item in eligible
        if item.expected_verdict == "FAIL" and item.predicted_verdict != "FAIL"
    )
    false_negative_denominator = sum(
        1 for item in eligible if item.expected_verdict == "FAIL"
    )
    return ClassificationMetrics(
        eligible=len(eligible),
        correct=correct,
        accuracy=_ratio(correct, len(eligible)),
        macro_precision=_mean([per_class[label]["precision"] for label in labels]),
        macro_recall=_mean([per_class[label]["recall"] for label in labels]),
        macro_f1=_mean([per_class[label]["f1"] for label in labels]),
        false_positive_count=false_positive_count,
        false_positive_rate=_ratio(
            false_positive_count,
            false_positive_denominator,
        ),
        false_negative_count=false_negative_count,
        false_negative_rate=_ratio(
            false_negative_count,
            false_negative_denominator,
        ),
        confusion=confusion,
        per_class=per_class,
    )


def evaluation_metrics(
    predictions: list[JudgePredictionView],
    metadata: dict[str, EvaluationCaseMetadata],
) -> JudgeEvaluationMetrics:
    modes: tuple[EvaluationMode, ...] = ("rules", "semantic", "hybrid")
    by_mode: dict[str, ClassificationMetrics] = {
        mode: classification_metrics(
            [item for item in predictions if item.mode == mode]
        )
        for mode in modes
    }
    rules_by_case = {
        item.case_id: item
        for item in predictions
        if item.mode == "rules"
        and item.predicted_verdict is not None
        and item.error is None
    }
    semantic_by_case = {
        item.case_id: item
        for item in predictions
        if item.mode == "semantic"
        and item.predicted_verdict is not None
        and item.error is None
    }
    shared = sorted(set(rules_by_case) & set(semantic_by_case))
    agreements = sum(
        rules_by_case[case_id].predicted_verdict
        == semantic_by_case[case_id].predicted_verdict
        for case_id in shared
    )
    agreement = JudgeAgreementMetrics(
        eligible=len(shared),
        agreements=agreements,
        disagreements=len(shared) - agreements,
        agreement_rate=_ratio(agreements, len(shared)),
    )
    return JudgeEvaluationMetrics(
        by_mode=by_mode,
        rules_semantic_agreement=agreement,
        by_failure_type=_breakdown(predictions, metadata, "failure_type"),
        by_language=_breakdown(predictions, metadata, "language"),
        by_scenario_category=_breakdown(
            predictions,
            metadata,
            "scenario_category",
        ),
        by_character=_breakdown(predictions, metadata, "character_key"),
    )


def _breakdown(
    predictions: list[JudgePredictionView],
    metadata: dict[str, EvaluationCaseMetadata],
    field: Literal[
        "failure_type",
        "language",
        "scenario_category",
        "character_key",
    ],
) -> dict[str, dict[str, ClassificationMetrics]]:
    values = sorted(
        {
            getattr(item, field) or "unclassified"
            for item in metadata.values()
        }
    )
    modes: tuple[EvaluationMode, ...] = ("rules", "semantic", "hybrid")
    result: dict[str, dict[str, ClassificationMetrics]] = {}
    for value in values:
        case_ids = {
            case_id
            for case_id, item in metadata.items()
            if (getattr(item, field) or "unclassified") == value
        }
        result[value] = {
            mode: classification_metrics(
                [
                    item
                    for item in predictions
                    if item.mode == mode and item.case_id in case_ids
                ]
            )
            for mode in modes
        }
    return result


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
