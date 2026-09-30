# Project state

Updated: **2026-09-30**. This is the only current progress and takeover record.

## Current scope and authority

| Item | Current state |
| --- | --- |
| Repository | `wong001110/character-relay` (GitHub repository ID 1311579094) |
| Verified main baseline | `2812d79b314b25aa31fe0632dcbdd7da205b0bf0`, PR #207 |
| Active direction | [Lightweight Room Director refactor](docs/plans/discord-group-chat-core.md), accepted 2026-09-30 |
| Branch / PR | `refactor/room-director-core`, draft PR #208 |
| Documentation-first commit | `24797e9377668594c806761f64bbc37dc783a83f` |
| First source checkpoint | `ef2e9b0b16359523f6212600cd91caca0dc554e6`; this follow-up repairs its lint/type/dependency diagnostics |
| User instruction | Commit direction first, then develop in coherent phases using Agent Continuity |
| Mode | Execution: source, tests, ordinary documentation and a review branch/PR authorized |
| Merge / deployment | Not authorized by this instruction; do not merge or deploy |
| Data direction | Old conversation/derived data need not survive; preserve authored card content where practical without legacy-schema coupling |
| Actual production reset | Not performed; requires a separately scoped cutover, draining/quarantining uncertain work and a card export/import rehearsal |
| External reuse | Existing Pydantic/stdlib and upstream selection/Reply patterns; no new runtime dependency or paid infrastructure |
| Initiative | **IN PROGRESS: P1 offline implementation checkpoint, not production replacement** |

The active plan supersedes the previous implementation strategy, while preserving A01-A22 and
security/product requirements. Do not finish old missing P3-P6 merely because old checkboxes exist.

## Source and continuity reconciliation

GitHub main was read again on 2026-09-30 and still points to `2812d79b...`. PR #207 delivered only
the foundation/P2a checkpoint. Previously reported unpushed P3-P6 source remains unavailable.
Old 1084-test/150-test/14-mutant logs do not attest absent code and are not evidence for this work.

AGENTS.md and Agent Continuity v0.4.0 execution/security/publication protocol were read. Assignment
state, scope/check mapping and recovery evidence live outside the entire checkout. Git/CI establish
published implementation. Local source is a partial mirror: sandbox DNS prevents a full GitHub
clone. Connected GitHub tree/commit writes preserve the full existing tree. Local subset checks
must not be represented as full-checkout, PostgreSQL, UI or production-path verification.

Source-map correction: `turn_director.py` does not exist at baseline. The existing graph calls
`DiscordConnectorRuntime.resolve_turn_director`; the actual runtime method/contracts remain
retirement targets. The architecture map now names that real boundary.

## Refactor phase status

| Phase | Status / required next evidence |
| --- | --- |
| P0 direction | COMPLETE: documentation committed before source work in `24797e9`; accepted plan, replacement map, preserved A01-A22 and card/reset boundaries |
| P1 replay and contracts | PARTIAL: executable contracts, rules-only runner, strict A/B/C capture comparison and synthetic seed tooling implemented/tested. Actual baseline/Free Token Pool capture adapters, 200-500-point human-reviewed corpus and real-model comparison remain |
| P2 source/routing integration | Pending: source persistence, permission projection, Free Token Pool adapter and real entry wiring |
| P3 character/context retirement | Pending: semantic participation, post-admission Turn Director and mandatory semantic structure still present |
| P4 notes/retrieval/expressions | Pending: numerical relationships, Belief/automatic writers and current embedding consumers still present |
| P5 continuation/freshness/Portal | Pending: preserve all independent A01-A22 protections |
| P6 integrated retirement/cutover rehearsal | Pending: no production data changes, deployment or completion claim |

## P1 implemented boundary and evidence

New source: `room_routing.py` (strict immutable data, explicit routing, public snapshot filtering,
qualified free-only bounded async provider seam, valid NONE vs faults); `room_replay.py` (actual
rules-only execution, normalized three-arm comparison, provenance/coverage/unknown-usage checks).
New tests: `test_room_routing.py`, `test_room_replay.py`.
Commands and adapter limitations: [replay guide](docs/developer/room-routing-replay.md).

Executed locally on Python 3.13 / Pydantic 2.13.4:

- `PYTHONPATH=src python -m pytest -q tests/test_room_routing.py tests/test_room_replay.py`:
  **61 passed**, including JSON/CLI roundtrip and malformed-input diagnostics. Rerun after repairs.
- Eight bounded manual mutation checks killed: message scope, per-role visibility, free-only
  qualification, attempt limit, target validation, explicit capacity, dataset hash and heldout
  family isolation. Original source restored and 61 tests rerun successfully. This is implementing-
  agent self-review, not independent review or exhaustive configured mutation certification.
- Seed generation, rules execution and report CLI ran successfully. Seeds are **24 unreviewed
  synthetic calibration cases in eight families**, not independent/human/heldout benchmark data.
  Missing current-planner and real-Director arms remain explicit; no quality/savings claim.

### Initial CI findings and repair

CI run `36724704912` on `ef2e9b0...` passed the Portal, Discord Connector, PostgreSQL foundation
and Docker jobs, but Python checks reported three Ruff simplifications in `room_routing.py` and
one new mypy optional-variable assignment in `room_replay.py`. These are corrected in this batch.
No lint ignores or mypy error suppressions were added.

The same type report contained 18 errors in existing `provider_trace_repository.py` and
`media_singleflight.py` query annotations. The unconstrained `<3.0` dependency can resolve to
SQLAlchemy 2.1, whose PEP 646 query generics differ from 2.0 tuple-shaped annotations. Constrain
SQLAlchemy to `>=2.0,<2.1` for the current source; review a 2.1 migration as a separate change.
Reference: [SQLAlchemy 2.1 migration](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html).
The rest of pyproject.toml, including every existing lint/type policy, is unchanged.

Full repository Ruff/mypy/Python/Connector/Portal/PostgreSQL/Docker CI must be checked against the
corrected PR head. Local Ruff/mypy and full product dependencies are unavailable. This commit does
not pre-claim its future CI result; exact-head PR checks and the linked receipt are authoritative.
No production entry consumes these modules yet; no existing runtime or security tests were removed.
No new dependencies, CI/deployment configuration or database schema/data changes were introduced;
the only dependency change is the SQLAlchemy compatibility bound above.

## Railway inspection

The connected Railway plugin is usable. Read-only discovery found Character Relay production
services `character-relay`, `discord-connector` and `pgvector`. The backend source remains this
repository's `main`, not the refactor branch. No variables, services, source branches, deployments
or database rows changed. Only variable names were visible; no secret values were requested/stored.
Successful plugin reads do not establish healthy/live acceptance of new source.

## Retained baseline and open proof gaps

Existing PR #207 foundation retains bounded snapshots, edit/delete invalidation, stable source
metadata, selected-source persistence failure handling, partial/uncertain delivery receipts and
metadata-first tracing. It does not prove complete ancestor/restart recovery, short A-B-A, fresh
drafts, explicit note replacement, Room Director integration or old-runtime removal.
Baseline receipts: [foundation](docs/reviews/group-chat-foundation-2026-09-21.md),
[P2a](docs/reviews/group-chat-transport-2026-09-21.md),
[checkpoint](docs/reviews/group-chat-checkpoint-2026-09-22.md). They attest their own source only.

## Next concrete action

Inspect exact-head CI and repair any in-scope integration failures. Implement the production
Free Token Pool adapter and actual current-planner capture path with full-checkout dependencies;
expand the corpus and preserve honest source/run/model identities. Build P2 source/permission
projection against real connector/runtime contracts. Independent implementation can proceed,
but live ambient promotion still requires human-reviewed heldout and real A/B/C/end-to-end
quality/latency/cost evidence. Do not substitute stubs for that gate or resurrect a permanent old
planner fallback. Continue coherent commits, update this record, and keep recovery state external.
No merge, deployment or live reset follows from this checkpoint.
