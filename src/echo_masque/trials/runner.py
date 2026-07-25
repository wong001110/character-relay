"""Trial execution service with observable event hooks."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from echo_masque.domain import (
    TrialResult,
    TrialScenario,
    TrialStatus,
    TrialSuiteResult,
    TrialTurn,
)
from echo_masque.judges import RuleJudge
from echo_masque.targets.base import TargetAdapter

type TrialObserver = Callable[[str, dict[str, object]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class TrialPacing:
    """Delays between visible trial beats."""

    scenario_open_seconds: float = 0
    after_tester_seconds: float = 0
    typing_seconds: float = 0
    after_subject_seconds: float = 0
    after_judge_seconds: float = 0
    after_breakpoint_seconds: float = 0
    scenario_gap_seconds: float = 0


FAST_PACING = TrialPacing()
WATCH_PACING = TrialPacing(
    scenario_open_seconds=0.8,
    after_tester_seconds=0.7,
    typing_seconds=1.1,
    after_subject_seconds=0.75,
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
    ) -> TrialResult:
        await target.reset()
        await self._emit(
            observer,
            "scenario_started",
            {
                "scenario_id": scenario.id,
                "name": scenario.name,
                "kind": scenario.kind.value,
                "expected_behavior": scenario.expected_behavior,
            },
        )
        await self._pause(pacing.scenario_open_seconds)

        turns: list[TrialTurn] = []
        for index, message in enumerate(scenario.messages, start=1):
            context = {"scenario_id": scenario.id, "turn_index": index}
            await self._emit(
                observer,
                "tester_message",
                {**context, "message": message},
            )
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

        turn_tuple = tuple(turns)
        verdict = self.judge.judge(scenario, turn_tuple)
        breakpoint = min((item.turn_index for item in verdict.evidence), default=None)
        await self._emit(
            observer,
            "judge_result",
            {
                "scenario_id": scenario.id,
                "passed": verdict.passed,
                "score": verdict.score,
                "summary": verdict.summary,
                "severity": verdict.severity.value,
                "evidence": [
                    item.model_dump(mode="json") for item in verdict.evidence
                ],
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
                },
            )
            await self._pause(pacing.after_breakpoint_seconds)

        await self._emit(
            observer,
            "scenario_completed",
            {
                "scenario_id": scenario.id,
                "passed": verdict.passed,
                "score": verdict.score,
                "breakpoint": breakpoint,
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
        )

    async def run_suite(
        self,
        target: TargetAdapter,
        scenarios: tuple[TrialScenario, ...],
        *,
        observer: TrialObserver | None = None,
        pacing: TrialPacing = FAST_PACING,
    ) -> TrialSuiteResult:
        await self._emit(
            observer,
            "session_started",
            {"target": target.summary.model_dump(mode="json"), "scenario_count": len(scenarios)},
        )
        results = [
            await self.run(
                target,
                scenario,
                observer=observer,
                pacing=pacing,
            )
            for scenario in scenarios
        ]
        result = TrialSuiteResult(target=target.summary, results=tuple(results))
        await self._emit(
            observer,
            "session_completed",
            {"average_score": result.average_score, "scenario_count": len(results)},
        )
        return result

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
