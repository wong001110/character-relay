# Project state

Updated: **2026-09-30**. This is the only current progress and takeover record.

## Current scope and authority

| Item | Current state |
| --- | --- |
| Repository | `wong001110/character-relay` (GitHub repository ID 1311579094) |
| Verified main baseline | `2812d79b314b25aa31fe0632dcbdd7da205b0bf0`, PR #207 |
| Active direction | [Lightweight Room Director refactor](docs/plans/discord-group-chat-core.md), accepted 2026-09-30 |
| User instruction | Commit direction first, then develop in coherent phases using Agent Continuity |
| Mode | Execution: source, tests, ordinary documentation and a review branch/PR authorized |
| Merge / deployment | Not authorized by this instruction; do not merge or deploy |
| Data direction | Old conversation/derived data need not survive; preserve authored card content where practical without legacy-schema coupling |
| Actual production reset | Not performed; requires a separately scoped cutover, draining/quarantining uncertain work and a card export/import rehearsal |
| External reuse | Prefer existing libraries/patterns; no second orchestration platform or unapproved paid infrastructure |
| Initiative | **IN PROGRESS; target architecture is not yet implemented** |

The active plan supersedes the previous implementation strategy, while preserving A01-A22 and
security/product requirements. Do not finish old missing P3-P6 merely because old checkboxes exist.

## Source and continuity reconciliation

GitHub main was read again on 2026-09-30 and still points to `2812d79b...`. PR #207 delivered only
the foundation/P2a checkpoint. The previously reported unpushed P3-P6 source remains unavailable.
Old 1084-test/150-test/14-mutant logs do not attest absent code and are not evidence for this work.

AGENTS.md was read. Agent Continuity v0.4.0 and its execution/security/publication protocol were
read from the user's Library. Assignment state, scope/check mapping and recovery evidence live
outside the entire checkout, not in the repository. Git/CI remain implementation truth.
The current sandbox cannot resolve github.com for a direct clone. Connected GitHub reads/writes
are available; local subset checks must not be represented as full-checkout verification.

## Refactor phase status

These are new phases from the current plan, not renamed completion claims for the old initiative.

| Phase | Status / next evidence |
| --- | --- |
| P0 direction | This documentation-only checkpoint records accepted boundaries, replacement map, preserved acceptance and reset/card policy before source changes |
| P1 replay and contracts | NEXT: implement strict proposal/outcome contracts, direct-only routing and three-arm replay mechanics; live/human quality remains unverified |
| P2 source/routing integration | Pending; source persistence, permissions, Free Token Pool adapter and real entry wiring |
| P3 character/context retirement | Pending; semantic participation, post-admission Turn Director and mandatory semantic structure still present |
| P4 notes/retrieval/expressions | Pending; numerical relationships, Belief/automatic writers and existing embedding consumers still present |
| P5 continuation/freshness/Portal | Pending; preserve all independent A01-A22 protections |
| P6 integrated retirement/cutover rehearsal | Pending; no production data changes, deployment or completion claim |

A P1 fixture/stub pass will not authorize ambient production enablement. Required future evidence:
human-reviewed heldout labels, comparable real-provider runs, full current-path baseline A,
rules-only B and Director C, actual latency/usage/errors, end-to-end turns and safety regression
checks. Missing inputs/arms/usage must stay visible. The plan permits independent implementation
while those gates remain open; it does not waive them.

## Railway inspection

The connected Railway plugin is usable. Read-only discovery found the existing Character Relay
project with production services `character-relay`, `discord-connector` and `pgvector`.
The backend service is sourced from this repository's `main`, not the new refactor branch.
No variables, services, source branches, deployments or database rows were changed. Variable names
were visible through service config; no secret values were requested or stored.
Do not confuse successful plugin reads with healthy/live acceptance of the new source.

## Baseline capabilities and retained limitations

Existing foundation retains bounded deep-copied room snapshots, edit/delete invalidation, stable
source metadata and selected-source persistence failure handling. Partial/uncertain delivery keeps
confirmed receipts and avoids whole-answer replay. Default provider tracing is metadata-first.
These do not prove complete ancestor fetching/restart recovery, short A-B-A, fresh drafts, simplified
notes, Room Director or physical removal of the old runtime.

Baseline receipts remain [foundation](docs/reviews/group-chat-foundation-2026-09-21.md),
[P2a](docs/reviews/group-chat-transport-2026-09-21.md), and
[PR #207 checkpoint](docs/reviews/group-chat-checkpoint-2026-09-22.md). Their tests attest their own
source identities only. New results and exact commit/CI receipts will be recorded here and on the PR.

## Next concrete action

After publishing the documentation-only commit, implement P1 as a coherent tested source batch.
Use strict data-only proposals and separate success/failure outcomes; preserve direct requests,
validate target visibility and prevent failure-as-NONE benchmark inflation. Reconcile the actual
branch/HEAD before writes. Continue independent in-scope work where gates permit. Do not merge,
deploy, reset live data or claim real-model superiority from synthetic tests.
