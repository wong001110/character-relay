# Project state

Updated: **2026-09-21**. This is the only current progress and takeover record.

## Current execution

| Item | State |
| --- | --- |
| Repository | `wong001110/character-relay` |
| Merged runtime baseline | `3cd183d460812d16cfb0c6d8dbae305d8ef61363` (PR #205) |
| Accepted planning baseline | `be7a8c01e45662a8d68abbefccce46f07e6a7110`, open PR #206 |
| Implementation branch / PR | `feat/discord-group-chat-core-takeover` / Draft #207 |
| Current implemented source | `53d53d0cd99f7f59b518fc367ab619ed412a10a4` |
| Authorization | Execution takeover requested after Work quota exhaustion |
| Policy / requirements | [AGENTS.md](AGENTS.md), [accepted plan](docs/plans/discord-group-chat-core.md) |
| Gate | P2a configured integration passed; complete final-head CI still separate |
| Merge / deployment | **NOT AUTHORIZED** |

PR #206 is an ancestor, not assumed merged. No unrelated PR #203 work is incorporated.
Unpushed Work changes remain unknown. At publication a newer foundation commit `458534b` was
found and reconciled before P2a publication; its privacy changes and regression tests are preserved.
Always read the actual remote head before writing. Local source anchors are verified snapshots,
not a substitute for fetched remote Git history.

All D01-D11 / A01-A22 remain required. Optional participation includes valid silence; retain bounded
A-B-A, stable group-chat identities, scoped explicit notes, lightweight relationships and tool
boundaries. Remove replaced writers and Roast rather than hiding UI. Initial 3-role / 6-speaking-turn
/ 2-per-role values are ceilings, not quotas or measured optima. No new service/vendor is required.

## Phase state

| Phase | Status |
| --- | --- |
| P0 | Accepted documentation baseline available in PR #206 |
| P1 | IN_PROGRESS: source verified, initial behavior/privacy/receipt counterexamples covered; broader replay and real call/token baseline pending |
| P2 | IN_PROGRESS: P2a source metadata, live buffer updates and partial/uncertain delivery integrated; ancestor fetching, persistent response-source links, restart and slow-job separation remain |
| P3 | NOT_STARTED: bounded role re-entry, attempts/room budgets and final-draft freshness |
| P4 | NOT_STARTED: explicit scoped notes, relationship replacement, automatic-writer/Discovery and Roast retirement |
| P5 | IN_PROGRESS: metadata-first trace foundation only; expiring provider raw capture, unified observation and Portal work remain |
| P6 | NOT_STARTED: full integration, dependency audit, actual source cleanup and retirement audit |

This is not completion of the programme. Numerical relationships, ordinary automatic writers,
Roast and unique-role guards still exist until their phases replace them.

## Implemented and retained foundation

- Immutable-by-copy room snapshots; recent human aliases before unrelated roles; stable identity,
  no name-based impersonation. Selected-source persistence failure returns an authoritative empty
  plan rather than admitting a potentially retargeted turn.
- Provider trace defaults to metadata, preserving safe failure/category/usage diagnostics without
  default free-form request/response/error prose. Existing opt-in redaction tests remain; live
  overrides and historical traces are not changed. Raw capture expiry is not implemented yet.
- Added per-message Reply/edit/deployment metadata through Connector/Python schemas, historical
  burst reconstruction and role transcripts. Gateway create/edit/delete events update the human
  buffer before slow processing; chronological edits and bounded invalidation/deletion markers
  reject stale queued enrichment. This does not yet implement send-time draft refresh.
- Extracted `connectors/discord/src/delivery.ts`. Native/webhook chunks preserve confirmed receipt
  IDs; missing acknowledgements, partial sends, unknown errors and 429s cannot trigger a blind
  whole-answer identity fallback. Asset and expression branches preserve the same boundary.
- Durable uncertainty reports bind to the exact operation/step/claim, preserve receipt IDs and do
  not advance dialogue or replay effects. Existing database columns are reused; no migration.
- Temporary source-acquisition and patch-transfer workflows/parts are removed. They are not a
  permanent runner, coding-agent dependency or product service.

## Evidence and limitations

Receipts: [foundation](docs/reviews/group-chat-foundation-2026-09-21.md) and
[P2a transport](docs/reviews/group-chat-transport-2026-09-21.md). Review is self-review only.

Configured P2a run **35599133605** tested actual source `53d53d0` / tree
`8a88bee627c525c47f660cf80663ff990692dce5`: Node 24 typecheck, **135 Vitest tests / 21 files**,
Connector build, Ruff, mypy (**403 source files**) and **42 Python integration tests / 1 warning**
all passed. The run's event was a temporary transfer commit; its artifact records the actual tested
commit/tree. Artifact `10637609238` was downloaded, hash verified and extracted; its tracked source
recreated that exact Git tree locally. Complete CI of the final PR head remains a separate gate.

Before reconciliation: **20 local Python tests**, **17 transpiled Node behavioral tests**, and six
manually selected mutation probes caught by assertions. Five seed regressions failed on the
original source. These are overlapping scopes, not additive unique test counts or a full mutation
score. Local package DNS prevented full LangGraph/API/Ruff/mypy/Vitest execution; configured CI
provided the listed integration evidence without fake dependencies or weakened assertions.

`npm ci` reported **4 moderate dependency advisories**. Do not force-upgrade or claim a clean audit;
classify affected packages, runtime reachability and remediation before release. The Python warning
is a dependency deprecation. No live Discord, model naturalness/cost, PostgreSQL contention,
independent security review, merge or deployment is claimed. No production data was purged.

## Next concrete action

Read complete PR CI results, repair failures, then finish P2: permission-scoped Reply ancestors,
persistent generated-response/source links, bounded restart rehydration and non-blocking slow jobs.
Continue P3 only with the actual ingress/delivery boundaries; a fresh cache alone does not make a
running model request fresh. Preserve requester authority and completed/uncertain tool work.
P4-P6 remain as listed in the accepted plan. Update this state after coherent verified batches;
do not introduce another active ledger or keep an indefinite legacy runtime fallback.
