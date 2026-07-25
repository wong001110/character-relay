"""Trial execution service with observable event hooks."""

import asyncio
from collections.abc import Awaitable, Callable

from echo_masque.domain import (
    TrialResult,
    TrialScenario,
    TrialStatus,
    TrialSuiteResult,
    TrialTurn,
)
from echo_masque.judges import RuleJudge
from echo_masque.targets.base import TargetAdapter

TrialObserver = Callable[[str, dict[str, object]], Awaitable[None]]


class TrialRunner:
    def __init__(self, judge: RuleJudge | None = None) -> None:
        self.judge = judge or RuleJudge()

    async def run(
        self,
        target: TargetAdapter,
        scenario: TrialScenario,
        *,
        observer: TrialObserver | None = None,
        delay_seconds: float = 0,
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
        turns: list[TrialTurn] = []
        for index, message in enumerate(scenario.messages, start=1):
            context = {"scenario_id": scenario.id, "turn_index": index}
            await self._emit(
                observer,
                "tester_message",
                {**context, "message": message},
            )
            await self._emit(observer, "subject_typing", context)
            if delay_seconds:
                await asyncio.sleep(delay_seconds)
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
            if delay_seconds:
                await asyncio.sleep(delay_seconds / 2)

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
        delay_seconds: float = 0,
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
                delay_seconds=delay_seconds,
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
    async def _emit(
        observer: TrialObserver | None,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if observer is not None:
            await observer(event_type, payload)
