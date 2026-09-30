from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from echo_masque.room_replay import ReplayCase, ReplayRecord, compare, run_rules, validate_cases
from echo_masque.room_routing import (
    ModelIdentity,
    ProviderAttempt,
    RoomDecision,
    RoomInput,
    RoomMessage,
    RoomRole,
    RoomScope,
    RoutingResult,
)

SHA = "a" * 40
SCOPE = RoomScope(owner_id="owner", connection_id="conn", guild_id="guild", channel_id="room")


def cases() -> tuple[ReplayCase, ...]:
    snapshot = RoomInput(
        scope=SCOPE, revision=1, trigger_message_id="m1",
        roles=(RoomRole(deployment_id="ann", scope=SCOPE, public_name="Ann"),),
        messages=(RoomMessage(
            message_id="m1", scope=SCOPE, author_id="human", text="Lunch?", visible_to=("ann",),
        ),),
    )
    return (
        ReplayCase(case_id="none", conversation_id="lunch", family_id="lunch",
                   split="calibration", source_kind="synthetic", snapshot=snapshot,
                   acceptable=((),)),
        ReplayCase(case_id="direct", conversation_id="request", family_id="request",
                   split="heldout", source_kind="synthetic",
                   snapshot=snapshot.model_copy(update={"action_deployment_ids": ("ann",)}),
                   acceptable=((RoomDecision(
                       speaker="ann", target_message_id="m1", mode="direct_answer",
                   ),),), required_direct=(RoomDecision(
                       speaker="ann", target_message_id="m1", mode="direct_answer",
                   ),)),
    )


def test_rules_baseline_executes_and_missing_arms_are_explicit() -> None:
    dataset = cases()
    records = run_rules(dataset, source_commit=SHA, run_id="test")
    report = compare(dataset, records)
    assert report["promotion_approved"] is False
    assert "unreviewed_labels" in report["promotion_blockers"]
    arm = report["arms"]["rules_only"]
    assert arm["joint_accuracy"] == 1.0 and arm["provider_attempts_observed"] == 0
    assert arm["input_tokens"] == 0 and arm["cost_usd"] == 0.0
    missing = report["arms"]["current_planner"]
    assert missing["missing"] == 2 and missing["joint_accuracy"] is None
    assert missing["input_tokens"] is None and missing["cost_usd"] is None


def test_failure_is_not_rewarded_as_none_and_direct_miss_is_counted() -> None:
    dataset = cases()
    records = run_rules(dataset, source_commit=SHA, run_id="test")
    failed = tuple(record.model_copy(update={
        "arm": "director", "execution": "stub",
        "outcome": RoutingResult(
            origin="director", status="error", reason="provider_failed", source_revision=1,
            attempts=(ProviderAttempt(
                identity=ModelIdentity(provider="test", model="small", tier="free"),
                status="error", latency_ms=5.0,
            ),),
        ),
    }) for record in records)
    report = compare(dataset, failed)
    arm = report["arms"]["director"]
    assert arm["joint_accuracy"] == 0 and arm["none_precision"] is None
    assert arm["none_recall"] == 0 and arm["faults"] == 2
    assert arm["direct_pairs_missed"] == 1
    assert arm["input_tokens"] is None and arm["cost_usd"] is None
    assert arm["provider_attempts_observed"] == 2
    assert "stub_predictions_are_not_real_provider_evidence" in report["promotion_blockers"]


@pytest.mark.parametrize("change", [
    {"case_id": "unknown"}, {"dataset_sha256": "f" * 64}, {"case_sha256": "b" * 64},
])
def test_reject_foreign_or_stale_records(change: dict[str, object]) -> None:
    dataset = cases()
    record = run_rules(dataset, source_commit=SHA, run_id="test")[0]
    with pytest.raises(ValueError):
        compare(dataset, (record.model_copy(update=change),))


def test_reject_stale_source_revision() -> None:
    dataset = cases()
    record = run_rules(dataset, source_commit=SHA, run_id="test")[0]
    with pytest.raises(ValueError):
        compare(dataset, (record.model_copy(update={
            "outcome": record.outcome.model_copy(update={"source_revision": 99}),
        }),))


def test_duplicate_case_and_record_not_treated_as_independent_evidence() -> None:
    dataset = cases()
    with pytest.raises(ValueError):
        validate_cases((dataset[0], dataset[0]))
    record = run_rules(dataset, source_commit=SHA, run_id="test")[0]
    with pytest.raises(ValueError):
        compare(dataset, (record, record))


@pytest.mark.parametrize("field", ["family_id", "conversation_id"])
def test_split_cannot_leak_conversation_or_template_family(field: str) -> None:
    dataset = cases()
    leaked = dataset[1].model_copy(update={field: getattr(dataset[0], field)})
    with pytest.raises(ValueError):
        validate_cases((dataset[0], leaked))


@pytest.mark.parametrize("change", [{"run_id": "other"}, {"source_commit": "b" * 40}])
def test_mixed_run_or_source_must_use_separate_report(change: dict[str, object]) -> None:
    dataset = cases()
    records = run_rules(dataset, source_commit=SHA, run_id="test")
    with pytest.raises(ValueError):
        compare(dataset, (records[0], records[1].model_copy(update=change)))


def test_partial_coverage_is_not_inflated_and_unknown_measurements_propagate() -> None:
    dataset = cases()
    records = run_rules(dataset, source_commit=SHA, run_id="test")
    report = compare(dataset, (records[1].model_copy(update={"latency_ms": None}),))
    arm = report["arms"]["rules_only"]
    assert arm["joint_accuracy"] == 0.5 and arm["coverage"] == 0.5
    assert arm["input_tokens"] is None and arm["provider_attempts_per_decision_point"] is None
    assert arm["latency_p95_ms_observed"] is None
    unknown = records[0].model_copy(update={
        "auxiliary_input_tokens": None, "auxiliary_output_tokens": None, "auxiliary_cost_usd": None,
    })
    arm = compare(dataset, (unknown, records[1]))["arms"]["rules_only"]
    assert arm["input_tokens"] is None and arm["cost_usd"] is None


def test_none_optional_is_excluded_from_binary_none_scores() -> None:
    sample = cases()[0]
    speaking = RoomDecision(speaker="ann", target_message_id="m1", mode="supplement")
    dataset = (sample.model_copy(update={"acceptable": ((), (speaking,))}),)
    records = run_rules(dataset, source_commit=SHA, run_id="test")
    arm = compare(dataset, records)["arms"]["rules_only"]
    assert arm["joint_accuracy"] == 1 and arm["none_optional_cases_excluded"] == 1
    assert arm["none_precision"] is None and arm["none_recall"] is None


def test_label_cannot_omit_required_direct_request() -> None:
    data = cases()[1].model_dump()
    data["acceptable"] = ((),)
    with pytest.raises(ValidationError):
        ReplayCase.model_validate(data)


def test_dataset_hash_is_order_independent_but_changes_with_text() -> None:
    dataset = cases()
    assert validate_cases(dataset) == validate_cases(tuple(reversed(dataset)))
    snapshot = dataset[0].snapshot
    changed = dataset[0].model_copy(update={"snapshot": snapshot.model_copy(update={
        "messages": (snapshot.messages[0].model_copy(update={"text": "Different"}),),
    })})
    assert validate_cases(dataset) != validate_cases((changed, dataset[1]))


def test_json_roundtrip_and_cli_rules_compare(tmp_path: Path) -> None:
    dataset = cases()
    source = tmp_path / "cases.jsonl"
    source.write_text("".join(case.model_dump_json() + "\n" for case in dataset))
    output = tmp_path / "rules.jsonl"
    subprocess.run([
        sys.executable, "-m", "echo_masque.room_replay", "rules", str(source), str(output),
        "--source-commit", SHA, "--run-id", "test",
    ], check=True, capture_output=True, text=True)
    readback = tuple(
        ReplayRecord.model_validate_json(line) for line in output.read_text().splitlines()
    )
    assert len(readback) == 2
    run = subprocess.run([
        sys.executable, "-m", "echo_masque.room_replay", "compare", str(source), str(output),
    ], check=True, capture_output=True, text=True)
    assert json.loads(run.stdout)["arms"]["rules_only"]["joint_accuracy"] == 1


def test_cli_rejects_malformed_input_without_echoing_private_data(tmp_path: Path) -> None:
    source = tmp_path / "bad.jsonl"
    source.write_text('{"private":"SECRET_TRANSCRIPT"}\n')
    run = subprocess.run([
        sys.executable, "-m", "echo_masque.room_replay", "rules",
        str(source), str(tmp_path / "out"),
        "--source-commit", SHA, "--run-id", "test",
    ], capture_output=True, text=True)
    assert run.returncode == 2 and "SECRET_TRANSCRIPT" not in run.stderr
