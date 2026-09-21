# Project state

Updated: **2026-09-21**. Single current progress and takeover record.

## Current execution

| Item | State |
| --- | --- |
| Repository | `wong001110/character-relay` |
| Merged runtime baseline | `3cd183d460812d16cfb0c6d8dbae305d8ef61363` (PR #205) |
| Accepted planning baseline | `be7a8c01e45662a8d68abbefccce46f07e6a7110`, open PR #206 |
| Implementation branch / PR | `feat/discord-group-chat-core-takeover` / Draft #207 |
| Authorization | User requested execution takeover after Work quota was exhausted |
| Policy / requirements | [AGENTS.md](AGENTS.md), [accepted plan](docs/plans/discord-group-chat-core.md) |
| Current checkpoint | Foundation plus P2a source/delivery integration; exact-head gates required |
| Merge / deployment | **NOT AUTHORIZED** |

At takeover, remote inventory contained no newer Work implementation or state commit. Unpushed
Work changes remain unknown, not assumed empty. Reconcile a later Work patch before integrating it.
This branch includes PR #206 as an ancestor; it does not alter main, the planning branch or PR #203.
The plan's original NOT_STARTED label describes its planning baseline; this file alone records
subsequent execution. All D01-D11 and A01-A22 remain required; this slice is not the full initiative.

## Phase state

| Phase | Status and remaining gate |
| --- | --- |
| P0 | Accepted documentation baseline available in PR #206 |
| P1 | IN_PROGRESS: three Connector defects reproduced; privacy negative cases added. Full group-chat characterization and live call/token baseline not complete |
| P2 | IN_PROGRESS: foundation plus Reply/edit/role metadata, live buffer changes and partial/uncertain delivery implemented; full integration, ancestor fetching, restart rehydration, response-source persistence and slow-job separation remain |
| P3 | NOT_STARTED: bounded A-B-A, attempt/room limits and send-time draft refresh still required |
| P4 | NOT_STARTED: explicit scoped notes, relationship replacement, writer/Discovery and Roast retirement still required |
| P5 | IN_PROGRESS: metadata-default trace slice moved forward as a small privacy prerequisite. Scoped expiring raw capture, unified observation and Portal work remain |
| P6 | NOT_STARTED: full integration, actual source decomposition and retirement audit remain |

The early P5 slice adds no new model calls, service, vendor or background task. Phase boundaries
are adaptive; it does not waive later privacy acceptance. Existing numerical relations, automatic
writers, Roast and unique-role guards still exist. No claim of full simplification or live readiness.

## Implemented foundation slice

- ContextBuffer replaces repeated/enriched messages in place and deep-copies both inputs and returned
  snapshots. A generation snapshot or renderer cannot mutate another consumer's room history.
- Mention aliases prioritize recent humans, then unambiguous known speaking roles, then other roles.
  Stable IDs distinguish same-named people; display names cannot identify a bot. Existing allowlist,
  self-mention and total-size restrictions remain. This is not full Reply/recipient pinning yet.
- Failed persistence of the selected participation source returns an authoritative empty plan with
  `reply_target_persistence_failed`, instead of admitting a turn that may reload a different source.
  The old regression demanding admission after failed persistence was intentionally replaced.
- Provider tracing defaults to metadata, including invalid/empty mode configuration; free-form
  request/response/error prose is not emitted by that default. Safe category and failed-tool counts
  are computed before dropping content; repository filtering retains those diagnostics.
- Trace categorization failure cannot stop generation; diagnostic incompleteness is explicit.
  Existing summary/content modes and their redaction tests remain explicit opt-ins. No production
  environment setting or historical stored trace was changed, and raw-capture expiry is not done.
- Removed the temporary source-acquisition workflow. No new enduring CI/bootstrap dependency remains.

## Verification and evidence

Receipt: [foundation verification](docs/reviews/group-chat-foundation-2026-09-21.md).
Checks are self-executed/self-reviewed, not independent review or production acceptance.

- Exact source artifact at `efb66eda828726cfda9cda6e3b952e0ad32153fd` was extracted; its local Git
  tree matched remote `11a048a950cb0bc9b2f10a2b08c1552b416fbe00` (1,066 source files).
- Baseline probes reproduced duplicate-message reorder, mutable snapshot aliasing and human alias
  crowding; all three reversed after fixes. Initial related Python baseline: 23 passed.
- Focused Python regression: **50 passed**, real source with synthetic data/HTTP transports.
- Standalone Node assertions against transpiled actual Connector modules: **12 passed**. These are
  not a substitute for the committed Vitest suite on the supported CI Node version.
- Focused TypeScript strict/noUncheckedIndexedAccess/exactOptionalPropertyTypes source check: passed.
- Eight manually selected mutation probes: eight assertion failures (killed). This is a bounded
  probe set, not a complete Stryker/mutmut run or general security certification.
- Full local route collection is blocked by missing `langgraph`; local Ruff/mypy/Vitest installation
  is unavailable because dependency-network resolution fails. Those gates require exact-head CI.
- `git diff --check` passed; tests do not call real Discord/providers, change live grants or spend
  model tokens. PostgreSQL, browser, live quality/cost and deployment checks were not run locally.

## P2a source and delivery batch

Reconciles a separately verified local patch with foundation commit `458534bec0489583cb48d5c6d0c901ce5946da98`.
The foundation's trace-privacy implementation, tests and fail-closed source handoff are preserved.
ContextBuffer extends the deep-copy fix with chronological insert/edit/delete/invalidation and bounded
tombstones. Gateway ingestion updates human context before slow processing; running-draft freshness
is still P3. Reply/edit/real deployment metadata reaches schemas, historical bursts and prompts.

`delivery.ts` separates definitely-unsent, partial and uncertain sends. Native/webhook chunks retain
confirmed message IDs; unknown or partial sends cannot fall back by resending the entire answer.
Asset and expression branches preserve the same boundary. Uncertainty reports bind to the exact
operation, step and claim, keep receipt IDs and do not advance the conversation. No schema migration.

Local evidence before integration: 20 real Python tests, 17 Node behavioral tests against transpiled
actual source, and six explicitly selected manual mutation probes caught by assertions. Five seed
regressions failed on the original snapshot and passed after changes. These are not full Vitest,
Ruff/mypy, PostgreSQL, live Discord or independent-security acceptance. Local package DNS access
failed; full route collection requires unavailable LangGraph. The integrated source must be checked
by the actual configured CI. Do not add these counts to the foundation's counts as a unique total.

Temporary patch-transfer files and workflow remove themselves in this batch. The patch SHA256 is
`b72eb14d190f710e6437deceffa4198691daf0e0611d2a89d4c61d10f9aacb37`; the pre-reconciliation
source tree was verified as `825065b9be3b127accf34d9835afc448ea379149`. This transport is not
a permanent coding-agent runtime, live deployment or production-data operation.

## Next concrete action

Read exact-head integration/CI results and repair failures without weakening protected invariants.
Finish P2's scoped Reply ancestor fetching, persistent response-source links, restart handling and
non-blocking slow-job scheduling. P3 multi-role budgets/re-entry/freshness, P4 explicit notes and
relationship/Roast/writer retirement, P5 unified observation/Portal and P6 remain incomplete.
No merge or deployment. Unpushed Work changes remain unknown; reconcile new remote changes first.
