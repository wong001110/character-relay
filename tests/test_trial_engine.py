import asyncio

from echo_masque.domain import TestKind as BehaviorTestKind
from echo_masque.suites import scenarios_for
from echo_masque.targets import fragile_target, stable_target
from echo_masque.trials import TrialRunner


def test_stable_target_passes_all_suites() -> None:
    result = asyncio.run(TrialRunner().run_suite(stable_target(), scenarios_for()))
    assert result.passed is True
    assert result.average_score == 100
    assert all(item.breakpoint is None for item in result.results)


def test_fragile_target_fails_all_suites_with_breakpoints() -> None:
    result = asyncio.run(TrialRunner().run_suite(fragile_target(), scenarios_for()))
    assert result.passed is False
    assert {item.scenario.kind for item in result.results} == set(BehaviorTestKind)
    assert all(item.breakpoint is not None for item in result.results)
    assert all(item.verdict.evidence for item in result.results)


def test_trial_results_are_deterministic() -> None:
    async def run_twice() -> tuple[dict[str, object], dict[str, object]]:
        runner = TrialRunner()
        first = await runner.run_suite(fragile_target(), scenarios_for())
        second = await runner.run_suite(fragile_target(), scenarios_for())

        def stable_view(result: object) -> dict[str, object]:
            dumped = result.model_dump(mode="json")  # type: ignore[attr-defined]
            dumped["target"].pop("id", None)
            for item in dumped["results"]:
                item.pop("id", None)
                item["target"].pop("id", None)
            return dumped

        return stable_view(first), stable_view(second)

    first, second = asyncio.run(run_twice())
    assert first == second
