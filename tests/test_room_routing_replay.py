from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from echo_masque.room_director import AttemptReceipt, DirectorReply, build_director_input
from echo_masque.room_routing_replay import (
    Corpus,
    DirectorRecording,
    DirectorRecordings,
    ObservedChoice,
    Prediction,
    ReplayRun,
    Usage,
    export_director_inputs,
    load_corpus,
    replay_director,
    run_rules,
    score_run,
)

CORPUS_PATH = Path(__file__).parent / "fixtures/room_routing/corpus.jsonl.gz"
FULL = load_corpus(CORPUS_PATH)


def small(*ids: str) -> Corpus:
    return Corpus(sha256=FULL.sha256, cases=tuple(c for c in FULL.cases if c.id in ids))


def recording(corpus: Corpus, text: str, **kwargs) -> DirectorRecording:
    case = corpus.cases[0]
    receipts = (
        AttemptReceipt(provider="fake", model="model-a", outcome="timeout", latency_ms=20),
        AttemptReceipt(provider="fake", model="model-b", outcome="success", latency_ms=5),
    )
    return DirectorRecording(
        case_id=case.id,
        input_fingerprint=build_director_input(case.snapshot).fingerprint,
        reply=DirectorReply(text=text, attempts=receipts),
        usage=Usage(logical_calls=1, physical_attempts=2, latency_ms=30),
        **kwargs,
    )


def test_corpus_is_reproducible_parameterized_and_not_human_reviewed(tmp_path: Path) -> None:
    output = tmp_path / "corpus.jsonl.gz"
    subprocess.run(
        [sys.executable, "scripts/build_room_routing_corpus.py", str(output)], check=True
    )
    # Container bytes may vary by Python/zlib version; corpus identity is decompressed JSONL.
    assert gzip.decompress(output.read_bytes()) == gzip.decompress(CORPUS_PATH.read_bytes())
    assert len(FULL.cases) == 240
    assert len({c.family_id for c in FULL.cases}) == 30
    assert {c.label_origin for c in FULL.cases} == {"synthetic"}
    assert {c.label_review for c in FULL.cases} == {"unreviewed"}
    assert sum(c.split == "held_out" for c in FULL.cases) == 48


@pytest.mark.parametrize("field", ("family_id", "conversation_id"))
def test_group_split_leakage_is_rejected(tmp_path: Path, field: str) -> None:
    values = [c.model_dump(mode="json") for c in FULL.cases[:2]]
    values[1][field] = values[0][field]
    values[1]["split"] = "held_out"
    path = tmp_path / "invalid.jsonl"
    path.write_text("\n".join(json.dumps(v) for v in values))
    with pytest.raises(ValueError, match="leaked"):
        load_corpus(path)


def test_duplicate_cases_are_not_extra_evidence(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.jsonl"
    path.write_text((FULL.cases[0].model_dump_json() + "\n") * 2)
    with pytest.raises(ValueError, match="Duplicate case"):
        load_corpus(path)


def test_rules_have_zero_model_calls_and_do_not_lose_clear_direct_requests() -> None:
    report = score_run(FULL, run_rules(FULL, source_revision="synthetic-test"))
    assert report["missed_direct_response"]["numerator"] == 0
    assert report["usage"]["physical_attempts"]["complete_total"] == 0
    assert report["calls_per_new_message"] == 0
    assert report["promotion_decision"] == "not_evaluated"
    assert report["label_review"] == {"unreviewed": 240}


def test_missing_prediction_is_error_not_silence_or_excluded_denominator() -> None:
    corpus = small(
        "human_banter-0", "single_mention-0", "interleaved_technical-0", "direct_capacity-0"
    )
    rules = run_rules(corpus, source_revision="test")
    rows = tuple(p for p in rules.predictions if p.case_id != "human_banter-0")
    report = score_run(corpus, rules.model_copy(update={"predictions": rows}))
    assert report["error_rate"] == {"numerator": 1, "denominator": 4, "value": 0.25}
    assert report["none_recall"]["value"] == 0
    assert report["none_precision"]["value"] == 0  # Only the missed ambient question was abstained.
    assert report["joint_accuracy_on_routable_cases"]["denominator"] == 3
    assert report["usage"]["input_tokens"]["complete_total"] is None
    assert report["usage"]["input_tokens"]["unknown_cases"] == 1
    assert report["calls_per_new_message"] is None


def test_no_positive_none_labels_yields_undefined_recall_not_a_perfect_score() -> None:
    corpus = small("single_mention-0")
    report = score_run(corpus, run_rules(corpus, source_revision="test"))
    assert report["none_recall"] == {"numerator": 0, "denominator": 0, "value": None}


@pytest.mark.parametrize("change", ("corpus", "duplicate", "extra"))
def test_mismatched_predictions_rejected(change: str) -> None:
    corpus = small("human_banter-0")
    run = run_rules(corpus, source_revision="test")
    if change == "corpus":
        run = run.model_copy(update={"corpus_sha256": "old"})
    elif change == "duplicate":
        run = run.model_copy(update={"predictions": run.predictions * 2})
    else:
        run = run.model_copy(
            update={"predictions": (Prediction(case_id="absent", outcome="none", reason="x"),)}
        )
    with pytest.raises(ValueError):
        score_run(corpus, run)


def test_exported_inputs_exclude_labels_reviews_and_private_messages() -> None:
    corpus = small("foreign_prompt_injection-0", "single_mention-0")
    rows = export_director_inputs(corpus)
    assert len(rows) == 1
    wire = json.dumps(rows)
    assert "PRIVATE_SENTINEL" not in wire
    assert "acceptable_choices" not in wire and "label_review" not in wire
    assert "source_revision" not in rows[0]["user_prompt"]


def test_recorded_none_retains_attempts_models_unknown_usage_and_timing() -> None:
    corpus = small("human_banter-0")
    record = recording(corpus, '{"speaker":null,"target_message_id":null,"mode":"none"}')
    records = DirectorRecordings(
        corpus_sha256=corpus.sha256, evidence_kind="synthetic_provider", records=(record,)
    )
    run = replay_director(corpus, records, source_revision="test")
    report = score_run(corpus, run)
    assert report["none_precision"]["value"] == 1
    assert report["usage"]["physical_attempts"]["complete_total"] == 2
    assert report["usage"]["cost_usd"]["complete_total"] is None
    assert report["provider_models"] == {"fake/model-a": 1, "fake/model-b": 1}
    assert report["latency_ms"]["p95"] == 30  # Recorded latency, not the replay's execution speed.


def test_invalid_recorded_output_is_not_scored_as_none() -> None:
    corpus = small("human_banter-0")
    records = DirectorRecordings(
        corpus_sha256=corpus.sha256,
        evidence_kind="synthetic_provider",
        records=(recording(corpus, "invalid"),),
    )
    report = score_run(corpus, replay_director(corpus, records, source_revision="test"))
    assert report["none_recall"]["value"] == 0
    assert report["error_rate"]["value"] == 1
    assert report["latency_ms"]["p95"] == 30


def test_missing_director_record_is_error_not_rule_only_abstention() -> None:
    corpus = small("human_banter-0")
    records = DirectorRecordings(
        corpus_sha256=corpus.sha256, evidence_kind="recorded_provider", records=()
    )
    report = score_run(corpus, replay_director(corpus, records, source_revision="test"))
    assert report["errors"] == {"missing_recording": 1}
    assert report["none_recall"]["value"] == 0


def test_stale_input_fingerprint_cannot_relabel_an_old_model_answer() -> None:
    corpus = small("human_banter-0")
    record = recording(corpus, '{"speaker":null,"target_message_id":null,"mode":"none"}')
    records = DirectorRecordings(
        corpus_sha256=corpus.sha256,
        evidence_kind="synthetic_provider",
        records=(record.model_copy(update={"input_fingerprint": "stale"}),),
    )
    with pytest.raises(ValueError, match="Stale"):
        replay_director(corpus, records, source_revision="test")


def test_no_recordings_are_consumed_for_direct_requests() -> None:
    corpus = small("single_mention-0")
    # Use a known ambiguous fixture to construct a valid recording, then give it a direct case ID.
    record = recording(
        small("human_banter-0"), '{"speaker":null,"target_message_id":null,"mode":"none"}'
    )
    records = DirectorRecordings(
        corpus_sha256=corpus.sha256,
        evidence_kind="synthetic_provider",
        records=(record.model_copy(update={"case_id": "single_mention-0"}),),
    )
    with pytest.raises(ValueError, match="deterministic"):
        replay_director(corpus, records, source_revision="test")


def test_unknown_attempt_usage_cannot_be_replaced_by_zero() -> None:
    record = recording(small("human_banter-0"), "invalid")
    raw = record.model_dump(mode="json")
    raw["usage"]["input_tokens"] = 0
    with pytest.raises(ValidationError, match="every physical attempt"):
        DirectorRecording.model_validate_json(json.dumps(raw))


def test_failure_without_receipts_cannot_claim_zero_attempts() -> None:
    with pytest.raises(ValidationError, match="unknown usage"):
        DirectorRecording(
            case_id="x",
            input_fingerprint="x",
            failure="timeout",
            usage=Usage(logical_calls=1, physical_attempts=0),
        )


def test_legacy_unknown_target_is_not_mapped_to_the_latest_message() -> None:
    corpus = small("single_mention-0")
    prediction = Prediction(
        case_id="single_mention-0",
        outcome="speak",
        reason="legacy",
        choices=(ObservedChoice(speaker="ann-0", target_message_id=None),),
    )
    run = ReplayRun(
        corpus_sha256=corpus.sha256,
        arm="planner",
        source_revision="baseline",
        evidence_kind="planner_fake_encoder",
        comparison_scope="planner_only",
        predictions=(prediction,),
    )
    report = score_run(corpus, run)
    assert report["speaker_accuracy_on_expected_speech"]["value"] == 1
    assert report["target_accuracy_on_expected_speech"]["value"] == 0
    assert report["joint_accuracy_on_routable_cases"]["value"] == 0
    assert report["unresolved_target_choices"] == 1


def test_cross_scope_predictions_are_visible_as_violations() -> None:
    corpus = small("single_mention-0")
    run = run_rules(corpus, source_revision="test")
    bad = run.predictions[0].model_copy(
        update={"choices": (ObservedChoice(speaker="foreign", target_message_id="secret"),)}
    )
    report = score_run(corpus, run.model_copy(update={"predictions": (bad,)}))
    assert report["scope_violation_cases"] == 1
    assert report["joint_accuracy_on_routable_cases"]["value"] == 0


def test_cli_rules_and_score(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.json"
    report = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/replay_room_routing.py",
            "rules",
            str(CORPUS_PATH),
            "--output",
            str(predictions),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/replay_room_routing.py",
            "score",
            str(CORPUS_PATH),
            "--input",
            str(predictions),
            "--output",
            str(report),
        ],
        check=True,
    )
    payload = json.loads(report.read_text())
    assert payload["cases"] == 240
    assert payload["source_revision"].startswith("sha256:")


def test_plain_and_compressed_corpus_have_same_content_identity(tmp_path: Path) -> None:
    plain = tmp_path / "corpus.jsonl"
    plain.write_bytes(gzip.decompress(CORPUS_PATH.read_bytes()))
    assert load_corpus(plain) == FULL


@pytest.mark.parametrize("compressed", (False, True))
def test_corpus_input_limit_applies_after_decompression(
    tmp_path: Path, monkeypatch, compressed
) -> None:
    monkeypatch.setattr("echo_masque.room_routing_replay.MAX_CORPUS_BYTES", 128)
    path = tmp_path / ("too_large.jsonl.gz" if compressed else "too_large.jsonl")
    data = b" " * 129
    path.write_bytes(gzip.compress(data, mtime=0) if compressed else data)
    with pytest.raises(ValueError, match="limit"):
        load_corpus(path)


def test_model_visible_ids_do_not_encode_scenario_labels() -> None:
    for row in export_director_inputs(FULL):
        payload = json.loads(row["user_prompt"])
        for message in payload["messages"]:
            assert len(message["id"]) == 24
            assert all(char in "0123456789abcdef" for char in message["id"])
        assert all(family not in row["user_prompt"] for family in {c.family_id for c in FULL.cases})
