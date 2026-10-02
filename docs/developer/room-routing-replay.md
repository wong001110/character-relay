# Room routing replay (R1 offline spike)

Scope/progress: [PROJECT_STATE.md](../../PROJECT_STATE.md). Acceptance:
[group-chat plan](../plans/discord-group-chat-core.md). This tool does not connect to Discord,
call a provider, read credentials, modify application data or promote an ambient model.

## Reproduce the rules arm

From the repository root with development dependencies installed:

```bash
PYTHONPATH=src python scripts/replay_room_routing.py validate tests/fixtures/room_routing/corpus.jsonl.gz
PYTHONPATH=src python scripts/replay_room_routing.py rules tests/fixtures/room_routing/corpus.jsonl.gz --output /tmp/rules.json
PYTHONPATH=src python scripts/replay_room_routing.py score tests/fixtures/room_routing/corpus.jsonl.gz --input /tmp/rules.json --output /tmp/rules-report.json
PYTHONPATH=src python scripts/build_room_routing_corpus.py /tmp/rebuilt-corpus.jsonl.gz
```

The checked-in corpus contains **30 synthetic families x 8 language/identifier variants** (240
rows); labels are unreviewed. Related variants stay together across the 192/48 split. These are
contract regressions, not 240 independent human conversations. Do not tune a model on the reserved
families and then call their score an unseen test. Human quality assessment needs separately
attested reviewed labels, broader real/redacted context, uncertainty and full-turn observations.

Corpus identity hashes decompressed JSONL, not the gzip wrapper. Regeneration is tested across
plain/gzip forms; parsing is capped after decompression as well. Duplicate case IDs and family or
conversation leakage across splits are rejected. Model-visible message IDs are opaque hashes,
not scenario names that disclose expected answers. Exact expected choice groups can contain all
required direct targets or multiple alternative valid complete results.

## Director inputs and recorded observations

```bash
PYTHONPATH=src python scripts/replay_room_routing.py export-director tests/fixtures/room_routing/corpus.jsonl.gz --output /tmp/director-inputs.jsonl
PYTHONPATH=src python scripts/replay_room_routing.py director tests/fixtures/room_routing/corpus.jsonl.gz --input /tmp/director-recordings.json --output /tmp/director-run.json
PYTHONPATH=src python scripts/replay_room_routing.py score tests/fixtures/room_routing/corpus.jsonl.gz --input /tmp/director-run.json --output /tmp/director-report.json
```

`export-director` emits only ambiguous, eligible cases. Send only `system_prompt`, `user_prompt`
and `json_schema` to a future authorized collector; case IDs, corpus hashes, labels/review status
and scenario metadata must stay out of the model conversation. Private/cross-scope/deleted source
text and private character-card fields are not included. Budget overflow is an explicit input
error, not silent JSON truncation. The spike accepts only same-scope messages; a future permitted
cross-scope ancestor adapter must preserve provenance and evidence, not relabel scope to fit.

No Free Token Pool collector is installed in this checkpoint. Use the strict `DirectorRecordings`
model in `room_routing_replay.py` for external observations. It contains `corpus_sha256`, a declared
`recorded_provider` or `synthetic_provider` evidence kind and `records`. Each recording binds a
case to its exported input fingerprint and exactly one reply or failure. `DirectorReply` contains
the raw short decision plus every provider attempt (provider/model/outcome/latency/optional usage).
`Usage` contains one logical call, total physical attempts, tokens/costs and observed elapsed time
including queue/retry. Missing token or cost values are null, not invented zeros. An unsuccessful
collection with no receipts cannot claim zero provider attempts. Synthetic observations must not
be relabelled as provider evidence.

A future collector must reuse the existing pool with an evaluated candidate set, a total deadline,
bounded attempts and no paid fallback. This injected callback does not enforce those external
policies. The current utility caller's permissive JSON salvage and unknown-usage-to-zero behavior
must not be reused silently. Never export credentials or chain-of-thought with observations.

Replay revalidates decisions against the exact supplied message/role set and input fingerprint.
Duplicate keys, inconsistent nulls, extra explanation fields, prose/markdown wrappers, ineligible
speakers and absent targets are rejected. Invalid, missing, timed-out and unavailable observations
remain errors, not successful NONE. No repair-until-valid loop is installed. Deterministic cases
use the rules result and reject extraneous Director recordings.

## Current Planner arm

`scripts/replay_legacy_planner.py` provides `replay_planner(...)` for the actual native
`ParticipationPlannerV3` class with its payload/deployment/candidate/Segment objects and an
explicitly supplied semantic service. Its tests use the existing deterministic fake service.
This is **Planner-stage-only**, not a full Connector -> semantic structure -> selection baseline.
Real FastEmbed and complete pipeline observations are still required for a product comparison.

Preserve actual selected-response-source links from the old pipeline. A Segment is not an exact
message target: without an actual link the adapter records null target, not the latest message.
The adapter rejects a supplied link outside the selected Segment and retains upstream failures
as errors. It hashes actual Planner source. Once the old runtime is retired, run baseline capture
against its pinned checkout; never import this adapter into production as a fallback.

## Report interpretation

Reports preserve explicit numerators/denominators, undefined metrics as null, unknown usage counts,
missing predictions, operational blocks, scope violations and unresolved legacy targets. Speaking
accuracy is measured on expected-speaking cases; NONE precision/recall do not discard failures.
Joint accuracy keeps speaker-target pairing. Direct-response loss is tracked independently of
being quieter. Physical attempts differ from logical calls, and calls/message use new messages,
not repeatedly included context. Percentiles use known recorded timings, including failed calls;
missing timings remain visible. Policy timing is not end-to-end Discord or Character latency.

A report's `promotion_decision` is always `not_evaluated`. Correlated synthetic variants do not
support a population-quality confidence claim. Per-scenario counts and actual provider/model
identities support later reviews; they do not prove reviewed labels or model fitness. See the
[R1 evidence](../reviews/room-director-r1-2026-10-01.md) for what was actually run.

## Focused validation

```bash
python -m pytest tests/test_room_routing.py tests/test_room_routing_replay.py tests/test_room_routing_legacy_replay.py tests/test_participation_planner_v3.py tests/test_smart_participation_v3_route.py tests/test_provider_trace_metadata_default.py
python -m ruff check .
python -m mypy src
mutmut run '*room_routing*route_rules*' '*room_routing*visible_messages*' '*room_routing*eligible_roles*' '*room_director*validate_decision*' '*room_director*_unique_object*' --max-children 2
```

Use the repository's normal environment and mutation instructions. Fresh test-selection profiling
is required after adding assertions; a stale mutation cache can hide whether new checks run.
R1 contracts accept runtime-normalized data, not public authority. R2/R3 still need authenticated
normalization, per-effect grants, request persistence, source freshness and real delivery tests.
