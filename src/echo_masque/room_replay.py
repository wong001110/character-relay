"""Offline routing replay with explicit missing arms, failures and unknown measurements.

Usage: python -m echo_masque.room_replay rules CASES OUTPUT
       python -m echo_masque.room_replay compare CASES RECORDS [RECORDS ...]

Captured current-planner/Director records must be produced by their real adapters;
this harness never substitutes expected labels or fabricated baseline predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from echo_masque.room_routing import (
    Contract,
    Identifier,
    RoomDecision,
    RoomInput,
    RoutingResult,
    route_rules_only,
)

Arm = Literal["current_planner", "rules_only", "director"]
ARMS: tuple[Arm, ...] = ("current_planner", "rules_only", "director")
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Commit = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class ReplayCase(Contract):
    case_id: Identifier
    conversation_id: Identifier
    family_id: Identifier
    split: Literal["calibration", "heldout"]
    source_kind: Literal["synthetic", "redacted", "public"]
    reviewed_by: Identifier | None = None
    snapshot: RoomInput
    # Each alternative is a complete acceptable speaker/target set. Empty means NONE.
    acceptable: Annotated[tuple[tuple[RoomDecision, ...], ...], Field(min_length=1)]
    required_direct: tuple[RoomDecision, ...] = ()
    tags: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def valid_labels(self) -> Self:
        for alternative in (*self.acceptable, self.required_direct):
            if any(decision.mode == "none" for decision in alternative):
                raise ValueError("Represent NONE as an empty alternative")
            pairs = {(decision.speaker, decision.target_message_id) for decision in alternative}
            if len(pairs) != len(alternative):
                raise ValueError("Duplicate label pairs")
        for alternative in self.acceptable:
            required = _pairs(self.required_direct)
            if not required.issubset(_pairs(alternative)):
                raise ValueError("Accepted alternatives cannot omit a required direct request")
        return self


class ReplayRecord(Contract):
    case_id: Identifier
    arm: Arm
    run_id: Identifier
    source_commit: Commit
    dataset_sha256: Digest
    case_sha256: Digest
    execution: Literal["rules", "captured", "stub"]
    outcome: RoutingResult
    # Total measured routing latency, including local planning/queueing as captured.
    latency_ms: Annotated[float, Field(ge=0)] | None = None
    # External compute/cost not represented by Director attempts (e.g. legacy embedding).
    auxiliary_cost_usd: Annotated[float, Field(ge=0)] | None = None
    auxiliary_input_tokens: Annotated[int, Field(ge=0)] | None = None
    auxiliary_output_tokens: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def execution_matches_arm(self) -> Self:
        if self.arm == "rules_only":
            if self.execution != "rules" or self.outcome.origin == "director":
                raise ValueError("Rules arm cannot claim model execution")
        elif self.execution == "rules":
            raise ValueError("Other arms require captured or explicitly stubbed results")
        return self


def _pairs(decisions: tuple[RoomDecision, ...]) -> frozenset[tuple[str | None, str | None]]:
    return frozenset((decision.speaker, decision.target_message_id) for decision in decisions)


def validate_cases(cases: tuple[ReplayCase, ...]) -> str:
    if not cases:
        raise ValueError("Empty replay dataset")
    seen: set[str] = set()
    splits: dict[tuple[str, str], str] = {}
    for case in cases:
        if case.case_id in seen:
            raise ValueError("Duplicate case_id")
        seen.add(case.case_id)
        for kind, key in (("conversation", case.conversation_id), ("family", case.family_id)):
            group = (kind, key)
            if group in splits and splits[group] != case.split:
                raise ValueError("Conversation/family leakage between calibration and heldout")
            splits[group] = case.split
    return fingerprint([
        case.model_dump(mode="json") for case in sorted(cases, key=lambda c: c.case_id)
    ])


def run_rules(
    cases: tuple[ReplayCase, ...], *, source_commit: str, run_id: str,
) -> tuple[ReplayRecord, ...]:
    digest = validate_cases(cases)
    records: list[ReplayRecord] = []
    for case in cases:
        start = time.monotonic()
        outcome = route_rules_only(case.snapshot)
        records.append(ReplayRecord(
            case_id=case.case_id, arm="rules_only", run_id=run_id, source_commit=source_commit,
            dataset_sha256=digest, case_sha256=fingerprint(case.model_dump(mode="json")),
            execution="rules", outcome=outcome, latency_ms=(time.monotonic() - start) * 1000,
            auxiliary_cost_usd=0.0, auxiliary_input_tokens=0, auxiliary_output_tokens=0,
        ))
    return tuple(records)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def compare(
    cases: tuple[ReplayCase, ...], records: tuple[ReplayRecord, ...],
) -> dict[str, object]:
    """Strict single-run-per-arm comparison. Repetitions require separate reports."""
    digest = validate_cases(cases)
    by_id = {case.case_id: case for case in cases}
    by_arm: dict[Arm, dict[str, ReplayRecord]] = {arm: {} for arm in ARMS}
    runs: dict[Arm, tuple[str, str, str]] = {}
    for record in records:
        case = by_id.get(record.case_id)
        if case is None:
            raise ValueError("Unknown case in replay records")
        if record.dataset_sha256 != digest:
            raise ValueError("Record uses a different dataset revision")
        if record.case_sha256 != fingerprint(case.model_dump(mode="json")):
            raise ValueError("Record uses a different case revision")
        if record.outcome.source_revision != case.snapshot.revision:
            raise ValueError("Stale source revision")
        if record.case_id in by_arm[record.arm]:
            raise ValueError("Duplicate arm/case prediction")
        run = (record.run_id, record.source_commit, record.execution)
        if record.arm in runs and runs[record.arm] != run:
            raise ValueError("Mixed source/run/execution identities within one arm")
        runs[record.arm] = run
        by_arm[record.arm][record.case_id] = record
    arm_reports: dict[str, object] = {}
    for arm in ARMS:
        available = by_arm[arm]
        joint = speaker = targets_correct = speaking_cases = 0
        true_none = predicted_none = required_none = none_optional = 0
        wrong_topic = required_direct = missed_direct = faults = 0
        logical_calls = attempts_count = 0
        known_input = known_output = 0
        unknown_usage = 0
        unknown_cost = 0
        known_cost = 0.0
        latencies: list[float] = []
        identities: set[tuple[str, str]] = set()
        for case in cases:
            alternatives = [_pairs(alternative) for alternative in case.acceptable]
            must_none = all(not alternative for alternative in alternatives)
            may_none = any(not alternative for alternative in alternatives)
            required_none += int(must_none)
            none_optional += int(may_none and not must_none)
            required = _pairs(case.required_direct)
            required_direct += len(required)
            record = available.get(case.case_id)
            if record is None:
                missed_direct += len(required)
                continue
            outcome = record.outcome
            success = outcome.status in {"selected", "partial", "none"}
            predicted = _pairs(outcome.decisions) if success else frozenset()
            missed_direct += len(required - predicted)
            faults += int(not success)
            if success:
                joint += int(predicted in alternatives)
                actual_speakers = {pair[0] for pair in predicted}
                speaker += int(any(
                    actual_speakers == {pair[0] for pair in alt} for alt in alternatives
                ))
                if predicted:
                    speaking_cases += 1
                    actual_targets = {pair[1] for pair in predicted}
                    targets_correct += int(any(
                        actual_targets == {pair[1] for pair in alt} for alt in alternatives
                    ))
                    valid_pairs: set[tuple[str | None, str | None]] = set().union(*alternatives)
                    wrong_topic += sum(pair not in valid_pairs for pair in predicted)
                # Cases admitting BOTH silence and speech are excluded from binary NONE scores.
                if outcome.status == "none" and not (may_none and not must_none):
                    predicted_none += 1
                    true_none += int(must_none)
            logical_calls += int(outcome.origin == "director")
            attempts_count += len(outcome.attempts)
            for attempt in outcome.attempts:
                identities.add((attempt.identity.provider, attempt.identity.model))
                known_input += attempt.input_tokens or 0
                known_output += attempt.output_tokens or 0
                unknown_usage += int(attempt.input_tokens is None or attempt.output_tokens is None)
                if attempt.cost_usd is None:
                    unknown_cost += 1
                else:
                    known_cost += attempt.cost_usd
            known_input += record.auxiliary_input_tokens or 0
            known_output += record.auxiliary_output_tokens or 0
            unknown_usage += int(
                record.auxiliary_input_tokens is None or record.auxiliary_output_tokens is None
            )
            if record.auxiliary_cost_usd is None:
                unknown_cost += 1
            else:
                known_cost += record.auxiliary_cost_usd
            if record.latency_ms is not None:
                latencies.append(record.latency_ms)
        complete = len(available) == len(cases)
        arm_reports[arm] = {
            "records": len(available), "missing": len(cases) - len(available),
            "coverage": _ratio(len(available), len(cases)), "faults": faults,
            "joint_accuracy": _ratio(joint, len(cases)) if available else None,
            "speaker_accuracy": _ratio(speaker, len(cases)) if available else None,
            "target_accuracy_given_speech": _ratio(targets_correct, speaking_cases),
            "none_precision": _ratio(true_none, predicted_none),
            "none_recall": _ratio(true_none, required_none) if available else None,
            "none_optional_cases_excluded": none_optional,
            "unacceptable_speaker_target_pairs": wrong_topic,
            "direct_pairs_required": required_direct, "direct_pairs_missed": missed_direct,
            "logical_director_decisions_observed": logical_calls,
            "provider_attempts_observed": attempts_count,
            "provider_attempts_per_decision_point": (
                attempts_count / len(cases) if complete else None
            ),
            "buffered_events": sum(case.snapshot.buffered_event_count for case in cases),
            "provider_attempts_per_event": (
                attempts_count / sum(case.snapshot.buffered_event_count for case in cases)
                if complete else None
            ),
            "input_tokens": known_input if complete and not unknown_usage else None,
            "output_tokens": known_output if complete and not unknown_usage else None,
            "usage_unknown_components": unknown_usage,
            "cost_usd": known_cost if complete and not unknown_cost else None,
            "known_cost_usd_subtotal": known_cost, "unknown_cost_components": unknown_cost,
            "latency_samples": len(latencies),
            "latency_p50_ms_observed": _percentile(latencies, 0.5),
            "latency_p95_ms_observed": _percentile(latencies, 0.95),
            "model_identities": sorted(identities), "run_identity": runs.get(arm),
        }
    blockers = ["manual_quality_latency_cost_and_end_to_end_review_required"]
    if any(len(by_arm[arm]) != len(cases) for arm in ARMS):
        blockers.append("missing_comparison_records")
    if any(case.reviewed_by is None for case in cases):
        blockers.append("unreviewed_labels")
    if not any(case.split == "heldout" for case in cases):
        blockers.append("no_heldout_cases")
    if any(record.execution == "stub" for record in records):
        blockers.append("stub_predictions_are_not_real_provider_evidence")
    return {
        "schema_version": 1, "dataset_sha256": digest, "case_count": len(cases),
        "human_reviewed_cases": sum(case.reviewed_by is not None for case in cases),
        "arms": arm_reports, "promotion_approved": False, "promotion_blockers": blockers,
        "scope": "routing only; selection is not successful Character response or delivery",
    }


def _read_lines(path: Path) -> list[str]:
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Replay file exceeds 32 MiB bound")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) > 10000:
        raise ValueError("Too many replay records")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    rules = commands.add_parser("rules")
    rules.add_argument("cases", type=Path)
    rules.add_argument("output", type=Path)
    rules.add_argument("--source-commit", required=True)
    rules.add_argument("--run-id", required=True)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("cases", type=Path)
    compare_parser.add_argument("records", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        cases = tuple(ReplayCase.model_validate_json(line) for line in _read_lines(args.cases))
        if args.command == "rules":
            records = run_rules(cases, source_commit=args.source_commit, run_id=args.run_id)
            args.output.write_text(
                "".join(record.model_dump_json() + "\n" for record in records), encoding="utf-8",
            )
        else:
            records = tuple(
                ReplayRecord.model_validate_json(line)
                for path in args.records for line in _read_lines(path)
            )
            print(json.dumps(compare(cases, records), indent=2, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        # Do not print Pydantic input dumps or private raw captures in diagnostics.
        parser.exit(2, f"Replay input rejected ({type(exc).__name__}); validate local files.\n")


if __name__ == "__main__":
    main()
