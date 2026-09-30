"""Offline routing replay, label isolation and failure-aware metrics.

This module never sends a request, reads a credential, changes application storage or
promotes a model. Imported predictions are observations, not authorization or evidence
that a label was independently reviewed. Human/model quality review remains separate.
"""

from __future__ import annotations

import gzip
import hashlib
import math
import time
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from echo_masque.room_director import (
    AttemptReceipt,
    DirectorReply,
    build_director_input,
    validate_decision,
)
from echo_masque.room_routing import (
    FrozenModel,
    Identifier,
    ReasonCode,
    RoutingSnapshot,
    SpeakerChoice,
    SpeakingMode,
    route_rules,
)


class ExpectedRouting(FrozenModel):
    outcome: Literal["speak", "none", "blocked"]
    # Each group is a complete acceptable result, including all mandatory direct targets.
    acceptable_choices: tuple[tuple[SpeakerChoice, ...], ...] = ()
    reasons: tuple[ReasonCode, ...] = ()
    direct_response_required: bool = False

    @model_validator(mode="after")
    def coherent_expectation(self) -> ExpectedRouting:
        if self.outcome == "speak":
            if not self.acceptable_choices or any(not g for g in self.acceptable_choices):
                raise ValueError("Speaking labels need at least one nonempty acceptable group.")
            if any(len({c.speaker for c in g}) != len(g) for g in self.acceptable_choices):
                raise ValueError("A result cannot select the same role twice.")
        elif self.acceptable_choices or self.direct_response_required:
            raise ValueError("Only speaking labels have choices or require a direct response.")
        if self.outcome == "blocked" and not self.reasons:
            raise ValueError("Blocked labels need a reason, not just an empty speaker list.")
        return self


class ReplayCase(FrozenModel):
    id: Identifier
    conversation_id: Identifier
    family_id: Identifier
    split: Literal["development", "held_out"]
    scenario: Identifier
    label_origin: Literal["synthetic", "redacted_real", "real"]
    label_review: Literal["unreviewed", "human_reviewed"]
    new_message_count: int = Field(ge=1, le=64)
    snapshot: RoutingSnapshot
    expected: ExpectedRouting

    @model_validator(mode="after")
    def allowed_label_ids(self) -> ReplayCase:
        roles = {r.deployment_id for r in self.snapshot.eligible_roles()}
        messages = {m.id for m in self.snapshot.visible_messages() if m.content_available}
        for group in self.expected.acceptable_choices:
            for choice in group:
                if choice.speaker not in roles or choice.target_message_id not in messages:
                    raise ValueError("A speaking label must reference an eligible visible source.")
        return self


class Corpus(FrozenModel):
    sha256: str
    cases: tuple[ReplayCase, ...]


MAX_CORPUS_BYTES = 32_000_000


def load_corpus(path: Path) -> Corpus:
    # Bound decompressed input too: a small archive is not necessarily a small corpus.
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        raw = stream.read(MAX_CORPUS_BYTES + 1)
    if len(raw) > MAX_CORPUS_BYTES:
        raise ValueError("Replay corpus exceeds the 32 MB offline input limit.")
    cases = tuple(ReplayCase.model_validate_json(line) for line in raw.splitlines() if line.strip())
    if not cases or len(cases) > 10_000:
        raise ValueError("Corpus must contain 1-10000 decision points.")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case ID.")
    for field in ("conversation_id", "family_id"):
        assignments: dict[str, str] = {}
        for case in cases:
            group = str(getattr(case, field))
            previous = assignments.setdefault(group, case.split)
            if previous != case.split:
                raise ValueError(f"{field} leaked across development and held-out splits.")
    return Corpus(sha256=hashlib.sha256(raw).hexdigest(), cases=cases)


class ObservedChoice(FrozenModel):
    speaker: Identifier
    # Legacy Segment selection is not automatically an exact message selection.
    target_message_id: Identifier | None
    mode: SpeakingMode | None = None


class Usage(FrozenModel):
    logical_calls: int | None = Field(default=None, ge=0)
    physical_attempts: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class Prediction(FrozenModel):
    case_id: Identifier
    outcome: Literal["speak", "none", "blocked", "error"]
    choices: tuple[ObservedChoice, ...] = ()
    reason: ReasonCode
    usage: Usage = Field(default_factory=Usage)
    attempts: tuple[AttemptReceipt, ...] | None = None

    @model_validator(mode="after")
    def coherent_prediction(self) -> Prediction:
        if (self.outcome == "speak") != bool(self.choices):
            raise ValueError("Only speaking predictions have choices.")
        if len({c.speaker for c in self.choices}) != len(self.choices):
            raise ValueError("Duplicate predicted speaker.")
        if self.attempts is not None:
            _check_attempt_totals(self.usage, self.attempts)
        return self


def _check_attempt_totals(usage: Usage, attempts: tuple[AttemptReceipt, ...]) -> None:
    if usage.physical_attempts != len(attempts):
        raise ValueError("Physical attempt count does not match receipts.")
    for field in ("input_tokens", "output_tokens", "cost_usd"):
        values = [getattr(a, field) for a in attempts]
        total = None if any(v is None for v in values) else sum(values)
        if getattr(usage, field) != total:
            raise ValueError(f"{field} does not account for every physical attempt.")


class ReplayRun(FrozenModel):
    corpus_sha256: str
    arm: Literal["rules", "director", "planner"]
    source_revision: str = Field(min_length=1, max_length=200)
    evidence_kind: Literal[
        "offline_rules",
        "synthetic_provider",
        "recorded_provider",
        "planner_fake_encoder",
        "planner_live_encoder",
        "recorded_pipeline",
    ]
    comparison_scope: Literal["routing_policy", "planner_only", "ingress_to_routing"]
    predictions: tuple[Prediction, ...]


def _observed(choices: tuple[SpeakerChoice, ...]) -> tuple[ObservedChoice, ...]:
    return tuple(ObservedChoice(**choice.model_dump()) for choice in choices)


def run_rules(corpus: Corpus, *, source_revision: str) -> ReplayRun:
    rows: list[Prediction] = []
    for case in corpus.cases:
        start = time.perf_counter()
        result = route_rules(case.snapshot)
        # This arm intentionally has no Director; eligible ambiguity is not an exception.
        outcome: Literal["speak", "none", "blocked"] = (
            "speak"
            if result.kind == "direct"
            else "blocked"
            if result.kind == "blocked"
            else "none"
        )
        rows.append(
            Prediction(
                case_id=case.id,
                outcome=outcome,
                choices=_observed(result.choices),
                reason="rules_only_abstention" if result.kind == "director" else result.reason,
                attempts=(),
                usage=Usage(
                    logical_calls=0,
                    physical_attempts=0,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_ms=(time.perf_counter() - start) * 1000,
                ),
            )
        )
    return ReplayRun(
        corpus_sha256=corpus.sha256,
        arm="rules",
        source_revision=source_revision,
        evidence_kind="offline_rules",
        comparison_scope="routing_policy",
        predictions=tuple(rows),
    )


class DirectorRecording(FrozenModel):
    case_id: Identifier
    input_fingerprint: str
    # Do not record raw credentials, URLs, private cards, or chain-of-thought.
    reply: DirectorReply | None = None
    failure: Literal["timeout", "unavailable", "error"] | None = None
    failed_attempts: tuple[AttemptReceipt, ...] | None = None
    usage: Usage

    @model_validator(mode="after")
    def one_result(self) -> DirectorRecording:
        if (self.reply is None) == (self.failure is None):
            raise ValueError("Record exactly one provider reply or explicit failure.")
        if self.usage.logical_calls != 1:
            raise ValueError("A Director recording represents one logical decision.")
        if self.reply is not None:
            if self.failed_attempts is not None:
                raise ValueError("Reply already contains the complete attempt sequence.")
            _check_attempt_totals(self.usage, self.reply.attempts)
        elif self.failed_attempts is not None:
            _check_attempt_totals(self.usage, self.failed_attempts)
        elif any(
            getattr(self.usage, f) is not None
            for f in ("physical_attempts", "input_tokens", "output_tokens", "cost_usd")
        ):
            raise ValueError("Missing failure receipts must retain unknown usage.")
        return self


class DirectorRecordings(FrozenModel):
    corpus_sha256: str
    evidence_kind: Literal["recorded_provider", "synthetic_provider"]
    records: tuple[DirectorRecording, ...]


def replay_director(
    corpus: Corpus,
    recordings: DirectorRecordings,
    *,
    source_revision: str,
) -> ReplayRun:
    if recordings.corpus_sha256 != corpus.sha256:
        raise ValueError("Director recordings belong to a different corpus revision.")
    by_id = {r.case_id: r for r in recordings.records}
    if len(by_id) != len(recordings.records):
        raise ValueError("Duplicate Director recording.")
    requested = {c.id for c in corpus.cases if route_rules(c.snapshot).kind == "director"}
    if set(by_id) - requested:
        raise ValueError("Director recording supplied for an unknown or deterministic case.")
    rules = run_rules(corpus, source_revision=source_revision)
    rule_rows = {p.case_id: p for p in rules.predictions}
    rows: list[Prediction] = []
    for case in corpus.cases:
        if case.id not in requested:
            rows.append(rule_rows[case.id])
            continue
        record = by_id.get(case.id)
        if record is None:
            rows.append(Prediction(case_id=case.id, outcome="error", reason="missing_recording"))
            continue
        view = build_director_input(case.snapshot)
        if record.input_fingerprint != view.fingerprint:
            raise ValueError(f"Stale Director input fingerprint: {case.id}")
        if record.failure is not None:
            rows.append(
                Prediction(
                    case_id=case.id,
                    outcome="error",
                    reason=record.failure,
                    usage=record.usage,
                    attempts=record.failed_attempts,
                )
            )
            continue
        assert record.reply is not None  # Validated mutually exclusive record state.
        try:
            if record.reply.attempts[-1].outcome != "success":
                raise ValueError("No successful provider completion.")
            decision = validate_decision(record.reply.text, view)
        except ValueError:
            rows.append(
                Prediction(
                    case_id=case.id,
                    outcome="error",
                    reason="invalid_decision",
                    usage=record.usage,
                    attempts=record.reply.attempts,
                )
            )
            continue
        rows.append(
            Prediction(
                case_id=case.id,
                outcome="none" if decision.mode == "none" else "speak",
                choices=_observed(decision.choices()),
                reason="director_decision",
                usage=record.usage,
                attempts=record.reply.attempts,
            )
        )
    return ReplayRun(
        corpus_sha256=corpus.sha256,
        arm="director",
        source_revision=source_revision,
        evidence_kind=recordings.evidence_kind,
        comparison_scope="routing_policy",
        predictions=tuple(rows),
    )


def export_director_inputs(corpus: Corpus) -> list[dict[str, object]]:
    """Export only model-visible inputs, never labels or test annotations."""
    from echo_masque.room_director import PROMPT_VERSION, SYSTEM_PROMPT, DirectorDecision

    rows: list[dict[str, object]] = []
    for case in corpus.cases:
        if route_rules(case.snapshot).kind != "director":
            continue
        view = build_director_input(case.snapshot)
        rows.append(
            {
                "case_id": case.id,
                "corpus_sha256": corpus.sha256,
                "input_fingerprint": view.fingerprint,
                "prompt_version": PROMPT_VERSION,
                "system_prompt": SYSTEM_PROMPT,
                "user_prompt": view.user_prompt,
                "json_schema": DirectorDecision.model_json_schema(),
            }
        )
    return rows


def _ratio(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def _percentile(values: list[float], q: float) -> float | None:
    # Nearest-rank percentiles: errors/retries are included whenever a timing exists.
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)] if values else None


def _pair_set(choices: tuple[ObservedChoice, ...]) -> set[tuple[str, str | None]]:
    return {(c.speaker, c.target_message_id) for c in choices}


def score_run(corpus: Corpus, run: ReplayRun) -> dict[str, object]:
    if run.corpus_sha256 != corpus.sha256:
        raise ValueError("Prediction/corpus revision mismatch.")
    by_id = {p.case_id: p for p in run.predictions}
    if len(by_id) != len(run.predictions):
        raise ValueError("Duplicate prediction ID.")
    case_ids = {case.id for case in corpus.cases}
    if set(by_id) - case_ids:
        raise ValueError("Unknown prediction ID.")
    rows = [
        by_id.get(c.id, Prediction(case_id=c.id, outcome="error", reason="missing_prediction"))
        for c in corpus.cases
    ]
    speaker_correct = target_correct = joint_correct = none_true = none_predicted = (
        none_expected
    ) = 0
    speaking_expected = blocked_correct = blocked_expected = direct_expected = direct_missed = 0
    scope_violations = wrong_topic = topic_opportunities = 0
    groups: dict[str, Counter[str]] = {}
    for case, row in zip(corpus.cases, rows, strict=True):
        expected = case.expected
        groups.setdefault(case.scenario, Counter())["cases"] += 1
        groups[case.scenario][row.outcome] += 1
        if expected.outcome == "blocked":
            blocked_expected += 1
            blocked_correct += int(row.outcome == "blocked" and row.reason in expected.reasons)
        elif expected.outcome == "speak":
            speaking_expected += 1
            speakers = {c.speaker for c in row.choices}
            targets = {c.target_message_id for c in row.choices}
            speaker_correct += int(
                any(speakers == {c.speaker for c in g} for g in expected.acceptable_choices)
            )
            target_correct += int(
                any(
                    targets == {c.target_message_id for c in g} for g in expected.acceptable_choices
                )
            )
            joint = row.outcome == "speak" and any(
                _pair_set(row.choices) == {(c.speaker, c.target_message_id) for c in g}
                for g in expected.acceptable_choices
            )
            joint_correct += int(joint)
            if expected.direct_response_required:
                direct_expected += 1
                direct_missed += int(not joint)
            if row.outcome == "speak":
                topic_opportunities += 1
                wrong_topic += int(
                    not any(
                        targets == {c.target_message_id for c in g}
                        for g in expected.acceptable_choices
                    )
                )
        else:
            joint_correct += int(row.outcome == "none")
        none_predicted += int(row.outcome == "none")
        none_expected += int(expected.outcome == "none")
        none_true += int(row.outcome == "none" and expected.outcome == "none")
        allowed_roles = {r.deployment_id for r in case.snapshot.eligible_roles()}
        allowed_messages = {m.id for m in case.snapshot.visible_messages() if m.content_available}
        scope_violations += int(
            any(
                c.speaker not in allowed_roles
                or (c.target_message_id is not None and c.target_message_id not in allowed_messages)
                for c in row.choices
            )
        )

    totals: dict[str, object] = {}
    for field in (
        "logical_calls",
        "physical_attempts",
        "input_tokens",
        "output_tokens",
        "cost_usd",
    ):
        values = [getattr(row.usage, field) for row in rows]
        known = [v for v in values if v is not None]
        totals[field] = {
            "known_sum": sum(known),
            "unknown_cases": len(values) - len(known),
            "complete_total": sum(known) if len(known) == len(values) else None,
        }
    latencies = [row.usage.latency_ms for row in rows if row.usage.latency_ms is not None]
    errors = Counter(row.reason for row in rows if row.outcome == "error")
    calls = [row.usage.logical_calls for row in rows]
    all_calls = (
        sum(c for c in calls if c is not None) if all(c is not None for c in calls) else None
    )
    message_count = sum(case.new_message_count for case in corpus.cases)
    return {
        "arm": run.arm,
        "corpus_sha256": corpus.sha256,
        "source_revision": run.source_revision,
        "evidence_kind": run.evidence_kind,
        "comparison_scope": run.comparison_scope,
        "cases": len(rows),
        "new_messages": message_count,
        "missing_predictions": sorted(case_ids - set(by_id)),
        "family_groups": len({c.family_id for c in corpus.cases}),
        "conversation_groups": len({c.conversation_id for c in corpus.cases}),
        "statistical_quality_interval": None,
        "label_origin": dict(Counter(c.label_origin for c in corpus.cases)),
        "label_review": dict(Counter(c.label_review for c in corpus.cases)),
        "splits": dict(Counter(c.split for c in corpus.cases)),
        "speaker_accuracy_on_expected_speech": _ratio(speaker_correct, speaking_expected),
        "target_accuracy_on_expected_speech": _ratio(target_correct, speaking_expected),
        "joint_accuracy_on_routable_cases": _ratio(joint_correct, len(rows) - blocked_expected),
        "none_precision": _ratio(none_true, none_predicted),
        "none_recall": _ratio(none_true, none_expected),
        "missed_direct_response": _ratio(direct_missed, direct_expected),
        "wrong_topic_on_expected_and_predicted_speech": _ratio(wrong_topic, topic_opportunities),
        "operational_block_accuracy": _ratio(blocked_correct, blocked_expected),
        "scope_violation_cases": scope_violations,
        "unresolved_target_choices": sum(
            c.target_message_id is None for r in rows for c in r.choices
        ),
        "provider_models": dict(
            Counter(f"{a.provider}/{a.model}" for r in rows for a in (r.attempts or ()))
        ),
        "error_rate": _ratio(sum(errors.values()), len(rows)),
        "errors": dict(errors),
        "usage": totals,
        "calls_per_new_message": all_calls / message_count if all_calls is not None else None,
        "calls_per_decision_point": all_calls / len(rows) if all_calls is not None else None,
        "latency_ms": {
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "unknown_cases": len(rows) - len(latencies),
            "includes_known_error_timings": True,
        },
        "scenarios": {k: dict(v) for k, v in groups.items()},
        "promotion_decision": "not_evaluated",
        "limitations": [
            "Synthetic variants are correlated; no population-quality interval is claimed.",
            "This report never authorizes ambient activation or establishes model superiority.",
            "Label provenance is declared; human review needs independent attestation.",
            "Policy/planner-only timing is not end-to-end Discord or Character latency.",
            "Calls per message use non-overlapping NEW messages, not repeated context-window size.",
        ],
    }
