"""Trial execution service."""

from echo_masque.domain import (
    TrialResult,
    TrialScenario,
    TrialStatus,
    TrialSuiteResult,
    TrialTurn,
)
from echo_masque.judges import RuleJudge
from echo_masque.targets.base import TargetAdapter


class TrialRunner:
    def __init__(self, judge: RuleJudge | None = None) -> None:
        self.judge = judge or RuleJudge()

    async def run(self, target: TargetAdapter, scenario: TrialScenario) -> TrialResult:
        await target.reset()
        turns: list[TrialTurn] = []
        for index, message in enumerate(scenario.messages, start=1):
            response = await target.send(message)
            turns.append(
                TrialTurn(
                    index=index,
                    tester_message=message,
                    target_response=response.text,
                    latency_ms=response.latency_ms,
                    trace=response.trace,
                )
            )

        turn_tuple = tuple(turns)
        verdict = self.judge.judge(scenario, turn_tuple)
        breakpoint = min((item.turn_index for item in verdict.evidence), default=None)
        return TrialResult(
            target=target.summary,
            scenario=scenario,
            status=TrialStatus.COMPLETED,
            turns=turn_tuple,
            verdict=verdict,
            breakpoint=breakpoint,
        )

    async def run_suite(
        self, target: TargetAdapter, scenarios: tuple[TrialScenario, ...]
    ) -> TrialSuiteResult:
        results = [await self.run(target, scenario) for scenario in scenarios]
        return TrialSuiteResult(target=target.summary, results=tuple(results))
