"""Run existing Rules, Semantic, and Hybrid Judges against frozen calibration Cases."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, cast

from echo_masque.calibration import CalibrationCaseView
from echo_masque.domain import TestKind, TestLanguage, TrialScenario, TrialTurn
from echo_masque.evaluation_analytics import (
    EvaluationCaseMetadata,
    EvaluationMode,
    JudgeEvaluationCreate,
    JudgeEvaluationView,
    JudgePredictionView,
    evaluation_metrics,
)
from echo_masque.judges import RuleJudge, SemanticJudge
from echo_masque.persistence import (
    CalibrationRepository,
    EvaluationRepository,
    Repository,
    WorkspaceRepository,
)
from echo_masque.providers import ChatProvider, OpenAICompatibleProvider
from echo_masque.services.runtime import RuntimeService

ContractSource = Literal["run_snapshot", "current_character", "generic"]


class EvaluationConflict(RuntimeError):
    """Raised when a Dataset cannot be evaluated without changing its authority."""


class JudgeEvaluationService:
    def __init__(
        self,
        calibration_repository: CalibrationRepository,
        evaluation_repository: EvaluationRepository,
        repository: Repository,
        workspace_repository: WorkspaceRepository,
        runtime_service: RuntimeService,
        provider_factory: Callable[[], ChatProvider | None] | None = None,
    ) -> None:
        self.calibration_repository = calibration_repository
        self.evaluation_repository = evaluation_repository
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.runtime_service = runtime_service
        self.provider_factory = provider_factory or self._semantic_provider

    async def evaluate(
        self,
        owner_id: str,
        request: JudgeEvaluationCreate,
    ) -> JudgeEvaluationView:
        dataset = self.calibration_repository.get_dataset(
            request.dataset_id,
            owner_id,
        )
        if dataset is None:
            raise KeyError("Calibration Dataset not found.")
        if dataset.status != "approved":
            raise EvaluationConflict(
                "Only an approved Calibration Dataset can be evaluated."
            )
        effective_modes = list(request.modes)
        if "hybrid" in effective_modes:
            for dependency in ("rules", "semantic"):
                if dependency not in effective_modes:
                    effective_modes.append(cast(EvaluationMode, dependency))

        semantic_judge = self._semantic_judge()
        predictions: list[JudgePredictionView] = []
        metadata: dict[str, EvaluationCaseMetadata] = {}
        for case in dataset.cases:
            metadata[case.id] = EvaluationCaseMetadata(
                case_id=case.id,
                failure_type=case.failure_type or "none",
                language=case.language,
                scenario_category=case.scenario_category,
                character_key=case.character_card_id or "unbound",
            )
            scenario, turn, context, contract_source = self._case_context(
                owner_id,
                case,
            )
            by_mode: dict[str, JudgePredictionView] = {}
            if "rules" in effective_modes:
                by_mode["rules"] = self._rules_prediction(
                    case.id,
                    case.expected_verdict,
                    scenario,
                    turn,
                    contract_source,
                )
            if "semantic" in effective_modes:
                by_mode["semantic"] = await self._semantic_prediction(
                    case.id,
                    case.expected_verdict,
                    scenario,
                    turn,
                    context,
                    contract_source,
                    semantic_judge,
                )
            if "hybrid" in effective_modes:
                by_mode["hybrid"] = self._hybrid_prediction(
                    case.id,
                    case.expected_verdict,
                    by_mode.get("rules"),
                    by_mode.get("semantic"),
                    contract_source,
                )
            predictions.extend(by_mode.values())

        metrics = evaluation_metrics(predictions, metadata)
        errors = sum(item.error is not None for item in predictions)
        status = (
            "completed"
            if errors == 0
            else "failed"
            if errors == len(predictions)
            else "partial"
        )
        return self.evaluation_repository.save(
            owner_id=owner_id,
            dataset_id=dataset.id,
            dataset_version=dataset.version,
            dataset_name=dataset.name,
            modes=effective_modes,
            judge_config=self._judge_config_snapshot(),
            metrics=metrics,
            status=status,
            predictions=predictions,
        )

    def _semantic_provider(self) -> ChatProvider | None:
        profile = self.runtime_service.config().judge
        credential, _ = self.runtime_service.credential("judge")
        if not profile.enabled or credential is None:
            return None
        return OpenAICompatibleProvider(
            base_url=profile.base_url,
            api_key=credential,
            timeout_seconds=45,
            max_retries=1,
        )

    def _semantic_judge(self) -> SemanticJudge | None:
        provider = self.provider_factory()
        if provider is None:
            return None
        profile = self.runtime_service.config().judge
        if not profile.enabled:
            return None
        return SemanticJudge(config=profile, provider=provider)

    def _judge_config_snapshot(self) -> dict[str, object]:
        profile = self.runtime_service.config().judge
        status = self.runtime_service.status().judge
        return {
            "rules": {"implementation": "RuleJudge"},
            "semantic": {
                "enabled": profile.enabled,
                "provider": profile.provider,
                "base_url": profile.base_url,
                "model": profile.model,
                "system_prompt": profile.system_prompt,
                "temperature": profile.temperature,
                "rubric_version": profile.rubric_version,
                "credential_source": status.credential_source,
                "configured": status.configured,
            },
            "hybrid": {"disagreement": "REVIEW"},
        }

    def _case_context(
        self,
        owner_id: str,
        case: CalibrationCaseView,
    ) -> tuple[TrialScenario, TrialTurn, str, ContractSource]:
        scenario_id = case.scenario_id or case.id
        scenario_name = case.scenario_name
        category = case.scenario_category
        language = case.language
        tester_message = case.tester_message
        expected_behavior = case.notes or "Evaluate the frozen response."
        required: tuple[str, ...] = ()
        forbidden: tuple[str, ...] = ()
        context = "No Character Card snapshot was available."
        source: ContractSource = "generic"

        if case.run_id:
            snapshot = self.workspace_repository.get_run_snapshot(
                case.run_id,
                owner_id,
            )
            if snapshot is not None:
                source = "run_snapshot"
                context = json.dumps(snapshot.character, ensure_ascii=False)
                raw = next(
                    (
                        item
                        for item in snapshot.scenarios
                        if str(item.get("id", "")) == scenario_id
                    ),
                    None,
                )
                if raw is not None:
                    scenario_name = str(raw.get("name", scenario_name))
                    category = str(raw.get("category", raw.get("kind", category)))
                    language = str(raw.get("language", language))
                    expected_behavior = str(
                        raw.get("expected_behavior", expected_behavior)
                    )
                    required = tuple(
                        str(item) for item in raw.get("required_phrases", [])
                    )
                    forbidden = tuple(
                        str(item) for item in raw.get("forbidden_phrases", [])
                    )
        elif case.character_card_id:
            card = self.repository.get_character_card(
                case.character_card_id,
                owner_id,
            )
            if card is not None:
                source = "current_character"
                context = json.dumps(
                    {
                        "display_name": card.display_name,
                        "persona_summary": card.persona_summary,
                        "traits": json.loads(card.traits_json),
                        "expected_tone": card.expected_tone,
                        "forbidden_behaviors": json.loads(
                            card.forbidden_behaviors_json
                        ),
                        "memory_summary": card.memory_summary,
                    },
                    ensure_ascii=False,
                )

        try:
            kind = TestKind(category)
            test_language = TestLanguage(language)
        except ValueError as exc:
            raise EvaluationConflict(
                f"Calibration Case {case.id} has an unsupported category or language."
            ) from exc
        scenario = TrialScenario(
            id=scenario_id,
            name=scenario_name,
            kind=kind,
            language=test_language,
            messages=(tester_message or "Calibration evaluation",),
            expected_behavior=expected_behavior,
            required_phrases=required,
            forbidden_phrases=forbidden,
        )
        turn = TrialTurn(
            index=max(1, case.turn_index or 1),
            tester_message=tester_message,
            target_response=case.subject_response,
        )
        return scenario, turn, context, source

    @staticmethod
    def _rules_prediction(
        case_id: str,
        expected: str,
        scenario: TrialScenario,
        turn: TrialTurn,
        contract_source: ContractSource,
    ) -> JudgePredictionView:
        verdict = RuleJudge().judge(scenario, (turn,))
        return _prediction(
            case_id=case_id,
            mode="rules",
            expected=expected,
            predicted="PASS" if verdict.passed else "FAIL",
            score=verdict.score,
            confidence=1.0,
            failure_types=(
                [verdict.failure_type]
                if verdict.failure_type is not None
                else []
            ),
            evidence=[item.model_dump(mode="json") for item in verdict.evidence],
            contract_source=contract_source,
        )

    @staticmethod
    async def _semantic_prediction(
        case_id: str,
        expected: str,
        scenario: TrialScenario,
        turn: TrialTurn,
        context: str,
        contract_source: ContractSource,
        judge: SemanticJudge | None,
    ) -> JudgePredictionView:
        if judge is None:
            return _prediction(
                case_id=case_id,
                mode="semantic",
                expected=expected,
                contract_source=contract_source,
                error="Semantic Judge Runtime is not configured.",
            )
        try:
            result = await judge.judge(
                scenario,
                (turn,),
                character_context=context,
            )
        except Exception as exc:
            return _prediction(
                case_id=case_id,
                mode="semantic",
                expected=expected,
                contract_source=contract_source,
                error=str(exc),
            )
        verdict = result.verdict
        return _prediction(
            case_id=case_id,
            mode="semantic",
            expected=expected,
            predicted="PASS" if verdict.passed else "FAIL",
            score=verdict.score,
            confidence=result.metadata.confidence,
            failure_types=(
                verdict.failure_type.split(",")
                if verdict.failure_type
                else []
            ),
            dimensions=result.metadata.dimensions,
            evidence=[item.model_dump(mode="json") for item in verdict.evidence],
            contract_source=contract_source,
        )

    @staticmethod
    def _hybrid_prediction(
        case_id: str,
        expected: str,
        rules: JudgePredictionView | None,
        semantic: JudgePredictionView | None,
        contract_source: ContractSource,
    ) -> JudgePredictionView:
        if rules is None or semantic is None:
            return _prediction(
                case_id=case_id,
                mode="hybrid",
                expected=expected,
                contract_source=contract_source,
                error="Hybrid dependencies were unavailable.",
            )
        if rules.error or semantic.error:
            return _prediction(
                case_id=case_id,
                mode="hybrid",
                expected=expected,
                contract_source=contract_source,
                error=rules.error or semantic.error,
            )
        predicted = (
            rules.predicted_verdict
            if rules.predicted_verdict == semantic.predicted_verdict
            else "REVIEW"
        )
        scores = [
            item
            for item in (rules.score, semantic.score)
            if item is not None
        ]
        return _prediction(
            case_id=case_id,
            mode="hybrid",
            expected=expected,
            predicted=predicted,
            score=round(sum(scores) / len(scores)) if scores else None,
            confidence=semantic.confidence,
            failure_types=list(
                dict.fromkeys(rules.failure_types + semantic.failure_types)
            ),
            dimensions=semantic.dimensions,
            evidence=rules.evidence + semantic.evidence,
            contract_source=contract_source,
        )


def _prediction(
    *,
    case_id: str,
    mode: EvaluationMode,
    expected: str,
    contract_source: ContractSource,
    predicted: str | None = None,
    score: int | None = None,
    confidence: float | None = None,
    failure_types: list[str] | None = None,
    dimensions: dict[str, int] | None = None,
    evidence: list[dict[str, object]] | None = None,
    error: str | None = None,
) -> JudgePredictionView:
    return JudgePredictionView(
        id="pending",
        evaluation_id="pending",
        case_id=case_id,
        mode=mode,
        expected_verdict=expected,
        predicted_verdict=predicted,
        score=score,
        confidence=confidence,
        failure_types=failure_types or [],
        dimensions=dimensions or {},
        evidence=evidence or [],
        contract_source=contract_source,
        error=error,
        created_at=datetime.now(UTC),
    )
