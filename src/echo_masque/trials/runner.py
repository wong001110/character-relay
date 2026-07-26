"""Trial execution service with observable event hooks."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from echo_masque.domain import (
    Evidence,
    JudgeMode,
    Severity,
    TrialResult,
    TrialScenario,
    TrialStatus,
    TrialSuiteResult,
    TrialTurn,
    Verdict,
)
from echo_masque.judges import RuleJudge, SemanticJudge
from echo_masque.targets.base import TargetAdapter
from echo_masque.testers import AdaptiveTester

type TrialObserver = Callable[[str, dict[str, object]], Awaitable[None]]
type PendingTesterMessage = tuple[str, str, dict[str, object]]


@dataclass(frozen=True, slots=True)
class TrialPacing:
    """Delays between visible trial beats."""

    scenario_open_seconds: float = 0
    after_tester_seconds: float = 0
    typing_seconds: float = 0
    after_subject_seconds: float = 0
    adaptive_thinking_seconds: float = 0
    after_judge_seconds: float = 0
    after_breakpoint_seconds: float = 0
    scenario_gap_seconds: float = 0


FAST_PACING = TrialPacing()
WATCH_PACING = TrialPacing(
    scenario_open_seconds=0.8,
    after_tester_seconds=0.7,
    typing_seconds=1.1,
    after_subject_seconds=0.75,
    adaptive_thinking_seconds=0.8,
    after_judge_seconds=0.9,
    after_breakpoint_seconds=1.0,
    scenario_gap_seconds=0.6,
)


class TrialRunner:
    def __init__(self, judge: RuleJudge | None = None) -> None:
        self.judge = judge or RuleJudge()

    async def run(
        self,
        target: TargetAdapter,
        scenario: TrialScenario,
        *,
        observer: TrialObserver | None = None,
        pacing: TrialPacing = FAST_PACING,
        adaptive_tester: AdaptiveTester | None = None,
        judge_mode: JudgeMode = JudgeMode.RULES,
        semantic_judge: SemanticJudge | None = None,
        character_context: str = "No Character Card profile was supplied.",
    ) -> TrialResult:
        await target.reset()
        await self._emit(
            observer,
            "scenario_started",
            {
                "scenario_id": scenario.id,
                "name": scenario.name,
                "kind": scenario.kind.value,
                "language": scenario.language.value,
                "expected_behavior": scenario.expected_behavior,
                "tester_mode": "adaptive" if adaptive_tester else "benchmark",
                "judge_mode": judge_mode.value,
            },
        )
        await self._pause(pacing.scenario_open_seconds)

        queue = self._initial_messages(scenario, adaptive_tester)
        turns: list[TrialTurn] = []
        index = 0
        while queue:
            index += 1
            message, source, tester_trace = queue.pop(0)
            context = {"scenario_id": scenario.id, "turn_index": index}
            tester_payload: dict[str, object] = {
                **context,
                "message": message,
                "source": source,
                "language": scenario.language.value,
            }
            if tester_trace:
                tester_payload["trace"] = tester_trace
            await self._emit(observer, "tester_message", tester_payload)
            await self._pause(pacing.after_tester_seconds)
            await self._emit(observer, "subject_typing", context)
            await self._pause(pacing.typing_seconds)

            response = await target.send(message)
            trace = dict(response.trace)
            trace["usage"] = {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
            turn = TrialTurn(
                index=index,
                tester_message=message,
                target_response=response.text,
                latency_ms=response.latency_ms,
                trace=trace,
            )
            turns.append(turn)
            await self._emit(
                observer,
                "subject_response",
                {
                    **context,
                    "message": response.text,
                    "latency_ms": response.latency_ms,
                    "trace": trace,
                },
            )
            await self._pause(pacing.after_subject_seconds)

            if adaptive_tester is None:
                continue
            if self._clear_forbidden_fracture(scenario, response.text):
                queue.clear()
                continue
            if index >= adaptive_tester.config.max_turns:
                queue.clear()
                continue

            next_context = {"scenario_id": scenario.id, "turn_index": index + 1}
            await self._emit(
                observer,
                "tester_thinking",
                {
                    **next_context,
                    "source": "adaptive",
                    "provider": adaptive_tester.config.provider,
                    "model": adaptive_tester.config.model,
                    "language": scenario.language.value,
                },
            )
            await self._pause(pacing.adaptive_thinking_seconds)
            reply = await adaptive_tester.next_message(scenario, tuple(turns))
            queue.append(
                (
                    reply.message,
                    "adaptive",
                    {
                        "provider": adaptive_tester.config.provider,
                        "model": reply.model,
                        "latency_ms": reply.latency_ms,
                        "usage": {
                            "input_tokens": reply.input_tokens,
                            "output_tokens": reply.output_tokens,
                        },
                    },
                )
            )

        turn_tuple = tuple(turns)
        rule_verdict = self.judge.judge(scenario, turn_tuple)
        semantic_verdict: Verdict | None = None
        semantic_metadata = None
        if judge_mode in {JudgeMode.SEMANTIC, JudgeMode.HYBRID}:
            if semantic_judge is None:
                raise ValueError("Semantic Judge is required for this Judge Mode.")
            await self._emit(
                observer,
                "judge_thinking",
                {
                    "scenario_id": scenario.id,
                    "judge_mode": judge_mode.value,
                    "provider": semantic_judge.config.provider,
                    "model": semantic_judge.config.model,
                },
            )
            semantic_result = await semantic_judge.judge(
                scenario,
                turn_tuple,
                character_context=character_context,
            )
            semantic_verdict = semantic_result.verdict
            semantic_metadata = semantic_result.metadata

        verdict, review_required = self._resolved_verdict(
            judge_mode,
            rule_verdict,
            semantic_verdict,
            scenario,
        )
        breakpoint = min((item.turn_index for item in verdict.evidence), default=None)
        await self._emit(
            observer,
            "judge_result",
            {
                "scenario_id": scenario.id,
                "passed": verdict.passed,
                "review_required": review_required,
                "decision": "review" if review_required else ("pass" if verdict.passed else "fail"),
                "score": verdict.score,
                "summary": verdict.summary,
                "severity": verdict.severity.value,
                "language": scenario.language.value,
                "judge_mode": judge_mode.value,
                "rule_score": rule_verdict.score,
                "semantic_score": semantic_verdict.score if semantic_verdict else None,
                "semantic_metadata": (
                    semantic_metadata.model_dump(mode="json") if semantic_metadata else None
                ),
                "evidence": [item.model_dump(mode="json") for item in verdict.evidence],
            },
        )
        await self._pause(pacing.after_judge_seconds)

        if breakpoint is not None:
            await self._emit(
                observer,
                "breakpoint_detected",
                {
                    "scenario_id": scenario.id,
                    "turn_index": breakpoint,
                    "evidence_count": len(verdict.evidence),
                    "severity": verdict.severity.value,
                    "language": scenario.language.value,
                    "review_required": review_required,
                },
            )
            await self._pause(pacing.after_breakpoint_seconds)

        await self._emit(
            observer,
            "scenario_completed",
            {
                "scenario_id": scenario.id,
                "passed": verdict.passed,
                "review_required": review_required,
                "score": verdict.score,
                "breakpoint": breakpoint,
                "language": scenario.language.value,
                "judge_mode": judge_mode.value,
            },
        )
        await self._pause(pacing.scenario_gap_seconds)

        return TrialResult(
            target=target.summary,
            scenario=scenario,
            status=TrialStatus.COMPLETED,
            turns=turn_tuple,
            verdict=verdict,
            breakpoint=breakpoint,
            judge_mode=judge_mode,
            rule_verdict=rule_verdict,
            semantic_verdict=semantic_verdict,
            semantic_metadata=semantic_metadata,
            review_required=review_required,
        )

    async def run_suite(
        self,
        target: TargetAdapter,
        scenarios: tuple[TrialScenario, ...],
        *,
        observer: TrialObserver | None = None,
        pacing: TrialPacing = FAST_PACING,
        adaptive_tester: AdaptiveTester | None = None,
        judge_mode: JudgeMode = JudgeMode.RULES,
        semantic_judge: SemanticJudge | None = None,
        character_context: str = "No Character Card profile was supplied.",
    ) -> TrialSuiteResult:
        language = scenarios[0].language.value if scenarios else "en"
        await self._emit(
            observer,
            "session_started",
            {
                "target": target.summary.model_dump(mode="json"),
                "scenario_count": len(scenarios),
                "tester_mode": "adaptive" if adaptive_tester else "benchmark",
                "judge_mode": judge_mode.value,
                "language": language,
            },
        )
        results = [
            await self.run(
                target,
                scenario,
                observer=observer,
                pacing=pacing,
                adaptive_tester=adaptive_tester,
                judge_mode=judge_mode,
                semantic_judge=semantic_judge,
                character_context=character_context,
            )
            for scenario in scenarios
        ]
        result = TrialSuiteResult(target=target.summary, results=tuple(results))
        await self._emit(
            observer,
            "session_completed",
            {
                "average_score": result.average_score,
                "scenario_count": len(results),
                "review_required": result.review_required,
                "judge_mode": judge_mode.value,
                "language": language,
            },
        )
        return result

    @classmethod
    def _resolved_verdict(
        cls,
        judge_mode: JudgeMode,
        rule_verdict: Verdict,
        semantic_verdict: Verdict | None,
        scenario: TrialScenario,
    ) -> tuple[Verdict, bool]:
        if judge_mode == JudgeMode.RULES:
            return rule_verdict, False
        if semantic_verdict is None:
            raise ValueError("Semantic Judge result is unavailable.")
        if judge_mode == JudgeMode.SEMANTIC:
            return semantic_verdict, False
        if rule_verdict.passed != semantic_verdict.passed:
            chinese = scenario.language.value == "zh-CN"
            evidence = cls._deduplicate_evidence(
                (*rule_verdict.evidence, *semantic_verdict.evidence)
            )
            return (
                Verdict(
                    passed=False,
                    score=round((rule_verdict.score + semantic_verdict.score) / 2),
                    failure_type="judge_disagreement",
                    severity=Severity.MEDIUM,
                    summary=(
                        "Rule Judge 与 Semantic Judge 结论不同，需要人工复核。"
                        if chinese
                        else "Rule Judge and Semantic Judge disagree; manual review is required."
                    ),
                    evidence=evidence,
                ),
                True,
            )
        evidence = cls._deduplicate_evidence(
            (*rule_verdict.evidence, *semantic_verdict.evidence)
        )
        return (
            Verdict(
                passed=rule_verdict.passed,
                score=round((rule_verdict.score + semantic_verdict.score) / 2),
                failure_type=(
                    semantic_verdict.failure_type or rule_verdict.failure_type
                    if not rule_verdict.passed
                    else None
                ),
                severity=cls._max_severity(rule_verdict.severity, semantic_verdict.severity),
                summary=semantic_verdict.summary,
                evidence=evidence,
            ),
            False,
        )

    @staticmethod
    def _deduplicate_evidence(items: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        seen: set[tuple[str, int, str]] = set()
        result: list[Evidence] = []
        for item in items:
            key = (item.code, item.turn_index, item.excerpt)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return tuple(result)

    @staticmethod
    def _max_severity(left: Severity, right: Severity) -> Severity:
        order = {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }
        return left if order[left] >= order[right] else right

    @staticmethod
    def _initial_messages(
        scenario: TrialScenario,
        adaptive_tester: AdaptiveTester | None,
    ) -> list[PendingTesterMessage]:
        messages = scenario.messages[:1] if adaptive_tester else scenario.messages
        return [(message, "benchmark", {}) for message in messages]

    @staticmethod
    def _clear_forbidden_fracture(scenario: TrialScenario, response: str) -> bool:
        lowered = response.lower()
        return any(phrase.lower() in lowered for phrase in scenario.forbidden_phrases)

    @staticmethod
    async def _pause(seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)

    @staticmethod
    async def _emit(
        observer: TrialObserver | None,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if observer is not None:
            await observer(event_type, payload)
