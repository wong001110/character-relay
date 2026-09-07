# Remaining reliability gaps — implementation closeout

Date: 2026-09-07. Branch: `codex/ai-native-reliability-review`, Draft PR #204.
Baseline: `8c30540338ce6799068f6c36ceb8730090993c60`. This document supersedes the
unimplemented status of R10–R17 in the [product review](reviewer-product-runtime-2026-09-07.md).
Implementation and offline verification are complete; newly added browser/PostgreSQL CI gates
must pass before release. Live model quality and production incident causality are not established.

## Disposition and evidence

| Finding | Implemented behavior | Evidence / contract |
| --- | --- | --- |
| R10 ingress | Global and destination admission bounds cover preflight, collector-held bursts, and runtime queue; age checked again before API work; explicit requests receive busy/expired outcomes | Discord `turnIngress.test.ts`; [job contract](mcp-conversation-jobs.md) |
| R11 lifecycle | Explicit reply-based cancel/replace bound to human author, source message, deployment and destination; cancellation CAS suppresses generated-but-unclaimed finals; active-turn gates prevent new tool work and late image publication | `test_turn_jobs.py`, `turnControl.test.ts`; job contract |
| R12 scratch | Actual reads filter expired/archived scratch; owner-scoped checkpoint/expiry maintenance starts with API lifespan | `test_conversation_runtime_memory_lifecycle.py`; [memory contract](memory-lifecycle-contract.md) |
| R13 gap results | Discovery candidates persist with source, expiry and review state; scoped operator acceptance validates exact stored source, claims the candidate and writes evidence in one transaction; reject competes through CAS | `test_knowledge_gap_discovery_v3.py`, `test_deployment_belief_management.py`; Portal Conversation panel |
| R14 first use | Correct internal connection UUID copy/guidance, paused/server-profile instructions, authorized Fabric bootstrap, candidate/Belief actions; PR Demo checks use local contracts while deployed health remains separately identified | Web API tests; `scripts/verify_portal_closeout.py`; [Discord setup](user/discord-setup.md) |
| R15 capability cache | Endpoint identity preserves scheme, effective port and case-sensitive path; negative observations expire after 15 minutes and permit probing; persistence upsert prevents stale observations replacing newer ones | `test_capability_quota_closeout.py`; 11 selected expiry-policy mutants killed |
| R16 Runtime evidence | Actual message API → Runtime → generated reply → delivery claim/ack → durable replay journey, plus existing Fabric fault/recovery tests | `test_runtime_journey_replay.py`; [replay limits](runtime-replay-validation.md) |
| R17 maintenance | Batched diagnostic writes with actual event timestamps/durations, periodic safe retention, explicit scoped Belief correction/rejection/forget, supervised lifecycle shutdown | `test_runtime_trace_closeout.py`, memory/Belief tests; memory contract |
| S03/S05 egress | Configurable media clients use exact provider-origin admission; controlled HTTP/MCP/browser call sites resolve public addresses immediately before literal-IP socket dial, preserving Host/SNI; redirects/subresources use the guarded path | `test_network_safety_transport.py`, browser/MCP/client tests; [security contract](security.md) |
| S06 quota races | Conditional SQL upserts atomically consume request/generation/evaluation quotas and record login failures; owner admission spans API resource quota checks and writes across repository transactions | `test_capability_quota_closeout.py`, `test_phase15_security_controls.py`; PostgreSQL CI contention test |

## Operational contracts

Cancel/replace is an explicit control, not an interpretation that every later human message
replaces prior work. Already claimed delivery or an in-flight external side effect cannot be
undone. Cancellation closes publication and new-work admission; uncertain effects retain their
ledger and are not automatically replayed. Job execution remains bounded and in-process rather
than a distributed queue. The existing dedicated Fabric worker owns its separate background work.

Capability cache keys use a versioned SHA-256 identity; old ambiguous endpoint keys are ignored.
No plaintext URL credential/query is stored in the new key. Supported observations do not expire;
unsupported observations become unknown at 900 seconds. There is no forced schema/data migration.

Authenticated mutating API requests acquire owner admission before resource quota checks and hold
it through the write. PostgreSQL uses a dedicated NullPool connection and transaction advisory
lock, released by rollback; SQLite uses an OS file lock for the database/owner pair. Same-owner
writes serialize, different owners remain independent, and a five-second wait returns 429 with
retry guidance. Slow mutations therefore delay other writes by that owner. PostgreSQL advisory
connections consume database capacity and must be included in deployment sizing. Request counters
and login failures use atomic upserts; an expired login-admission read does not write back stale state.

Diagnostic buffering is best effort: 2,048 queued events, batches of 128, flush every 250 ms.
Overflow and failed batch writes increment `dropped_events`; write failures are logged. Diagnostics are
not an authorization or delivery ledger. Runtime event timestamps are captured before buffering,
and completed nodes carry measured duration. Production lifespan starts maintenance immediately
and every 60 seconds; terminal diagnostic retention defaults to seven days and 5,000 trace runs.
Unsettled delivery/uncertain side effects protect their durable operation records from pruning.
Those records may grow until explicitly reconciled; retention must not silently erase uncertainty.
AsyncExitStack unwinds partially started services and stops work producers before browser/trace
shutdown. Database work already running in a thread is joined during maintenance cancellation.

Schema changes are additive: register the gap candidate table and add `source_author_id` to old
`discord_turn_jobs` tables with default empty string. Historical jobs with unknown authors do not
gain guessed cancellation authority. `test_turn_job_migration.py` exercises repeat initialization
against an old SQLite schema and verifies existing job data survives. No source-memory deletion,
production reset, feature deletion or automatic MCP enablement is included.

## Validation record

- Integrated Python 3.12: `python -m pytest -n 2 --tb=short` — **1,041 passed, 6 skipped**,
  13 warnings, 325.57 seconds. This precedes the last browser-channel, additive-migration and
  login-reset refinements; focused post-refinement checks and published-head CI supplement it.
- Post-refinement capability/migration/browser/transport scope: **24 passed, 1 skipped**.
  The skip is the new explicitly gated disposable-PostgreSQL test, not a swallowed failure.
- Discord Connector: **110 tests across 19 files**, typecheck and production build passed.
- Portal: **71 tests across 23 files**, typecheck and production build passed.
- Capability expiry policy: `mutmut run '*capability_observation_is_current*' --max-children 2`
  on fresh statistics — **11 killed, 0 survivors**. This is only the selected helper scope.
- Final atomic login/capability/security scope: **14 passed, 1 PostgreSQL skip**.
- Ruff repository lint and clean-cache mypy (**403 source files**) passed. Existing CI exclusions
  were not expanded.
- Independent final source review found no additional release blocker in the cancellation,
  gap acceptance, egress, quota, and lifespan paths after corrections. This is source-review
  evidence; the reviewer did not independently rerun the parent's whole suite.

The Docker CI job now executes actual built Portal navigation and form actions using Playwright
and synthetic API fixtures. The script accepts loopback origins only and intercepts every API
request. PostgreSQL CI additionally exercises parallel quota consumption and same-owner advisory
lock serialization in the explicitly designated disposable test database. Local Docker,
PostgreSQL and Chromium are unavailable; these executions await CI rather than being called passes.

## Remaining external validation and deliberate deferrals

The API/worker recipe and offline replay do not establish the original production sync incident's
cause. Real configured MCP compatibility, Discord delivery under outage, natural dialogue quality,
and quality/latency/cost comparisons still require an authorized isolated environment and baseline.
Production Demo credential readiness is an operational configuration problem; changing its CI
classification does not provision the missing credential or claim the deployed service is repaired.

Pinned transport covers the call sites listed in the security contract, not arbitrary injected
clients or every Chromium/native protocol. Browser WebSocket routes are closed; WebRTC,
WebTransport and media-capture APIs are disabled in the controlled contexts. Deployment-level
egress isolation remains necessary for broader native/process boundaries.

The user parked local-model/adversarial reproduction. No rejected attack reproduction was resumed,
and this closeout is not a completed full adversarial Red Team exercise. Source-wide defensive
assessment and synthetic rejection/recovery tests remain distinguished from live adversarial proof.
Dense retrieval expansion, gameplay/WebRTC, new collectors and framework replacement remain
deferred product work rather than missing fixes in this batch.

Next takeover: review PR #204 and its exact-head CI, then configure one isolated MCP/Discord preview
and run the documented quality/recovery comparison. No merge, deployment or live dispatch was made.
