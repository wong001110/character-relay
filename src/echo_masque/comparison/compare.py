"""Evidence-aware comparison of two trial-suite results."""

from echo_masque.comparison.models import (
    ComparisonResult,
    RegressionPolicy,
    ScenarioChange,
)
from echo_masque.domain import TrialSuiteResult


def compare_results(
    baseline: TrialSuiteResult,
    candidate: TrialSuiteResult,
    policy: RegressionPolicy | None = None,
) -> ComparisonResult:
    """Compare matching scenarios and evaluate an explicit regression policy."""

    resolved_policy = policy or RegressionPolicy()
    baseline_map = {item.scenario.id: item for item in baseline.results}
    candidate_map = {item.scenario.id: item for item in candidate.results}
    shared_ids = sorted(baseline_map.keys() & candidate_map.keys())
    if not shared_ids:
        raise ValueError("Runs do not share any scenario identifiers.")

    changes: list[ScenarioChange] = []
    new_failures: list[str] = []
    resolved_failures: list[str] = []
    for scenario_id in shared_ids:
        before = baseline_map[scenario_id]
        after = candidate_map[scenario_id]
        if before.verdict.passed and not after.verdict.passed:
            new_failures.append(scenario_id)
        if not before.verdict.passed and after.verdict.passed:
            resolved_failures.append(scenario_id)
        changes.append(
            ScenarioChange(
                scenario_id=scenario_id,
                baseline_score=before.verdict.score,
                candidate_score=after.verdict.score,
                score_delta=after.verdict.score - before.verdict.score,
                baseline_breakpoint=before.breakpoint,
                candidate_breakpoint=after.breakpoint,
                baseline_passed=before.verdict.passed,
                candidate_passed=after.verdict.passed,
                evidence_delta=(
                    len(after.verdict.evidence) - len(before.verdict.evidence)
                ),
            )
        )

    baseline_score = _score_for(baseline, shared_ids)
    candidate_score = _score_for(candidate, shared_ids)
    score_delta = candidate_score - baseline_score
    baseline_latency = _average_latency(baseline, shared_ids)
    candidate_latency = _average_latency(candidate, shared_ids)
    latency_change = _percent_change(baseline_latency, candidate_latency)
    baseline_tokens = _total_tokens(baseline, shared_ids)
    candidate_tokens = _total_tokens(candidate, shared_ids)

    violations: list[str] = []
    if score_delta < -resolved_policy.max_score_drop:
        violations.append(
            f"Average score dropped by {abs(score_delta):.2f}, exceeding "
            f"{resolved_policy.max_score_drop:.2f}."
        )
    if new_failures and not resolved_policy.allow_new_failures:
        violations.append(f"New failing scenarios: {', '.join(new_failures)}.")
    if latency_change > resolved_policy.max_latency_increase_percent:
        violations.append(
            f"Average latency increased by {latency_change:.2f}%, exceeding "
            f"{resolved_policy.max_latency_increase_percent:.2f}%."
        )

    return ComparisonResult(
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        score_delta=score_delta,
        baseline_average_latency_ms=baseline_latency,
        candidate_average_latency_ms=candidate_latency,
        latency_change_percent=latency_change,
        baseline_total_tokens=baseline_tokens,
        candidate_total_tokens=candidate_tokens,
        token_delta=candidate_tokens - baseline_tokens,
        new_failures=tuple(new_failures),
        resolved_failures=tuple(resolved_failures),
        scenario_changes=tuple(changes),
        gate_passed=not violations,
        gate_violations=tuple(violations),
    )


def _score_for(result: TrialSuiteResult, scenario_ids: list[str]) -> float:
    scores = [
        item.verdict.score for item in result.results if item.scenario.id in scenario_ids
    ]
    return sum(scores) / len(scores)


def _average_latency(result: TrialSuiteResult, scenario_ids: list[str]) -> float:
    values = [
        turn.latency_ms
        for item in result.results
        if item.scenario.id in scenario_ids
        for turn in item.turns
        if turn.latency_ms is not None
    ]
    return sum(values) / len(values) if values else 0.0


def _total_tokens(result: TrialSuiteResult, scenario_ids: list[str]) -> int:
    total = 0
    for item in result.results:
        if item.scenario.id not in scenario_ids:
            continue
        for turn in item.turns:
            usage = turn.trace.get("usage")
            if isinstance(usage, dict):
                for key in ("input_tokens", "output_tokens"):
                    value = usage.get(key)
                    if isinstance(value, int):
                        total += value
    return total


def _percent_change(baseline: float, candidate: float) -> float:
    if baseline == 0:
        return 0.0 if candidate == 0 else 100.0
    return ((candidate - baseline) / baseline) * 100
