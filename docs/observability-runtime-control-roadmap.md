# Post-V4 Observability & Runtime Control Roadmap

Status: **IMPLEMENTED / RELEASE VALIDATED**

Branch: `agent/observability-runtime-control`

Draft PR: `#167`

## Goal

Turn the completed Conversation Intelligence V4 and AI Utility Gateway foundations into systems that are easy to inspect and tune from Portal without Railway environment edits, Connector restarts, or direct SQLite inspection.

The implementation addresses three production usability gaps:

1. Conversation Intelligence now exposes current Learned State, decay/evidence, and scoped Topic history through Portal.
2. AI Utility Gateway now exposes Runtime health plus authoritative quota/reset observations and automatically re-admits providers after cooldown/reset expiry.
3. Conversation Burst / Turn Collector timing is now a persisted Portal Runtime setting that the live Connector can adopt without restart.

## Fixed decisions

- Portal-persisted Runtime configuration takes precedence over environment bootstrap defaults.
- Environment variables remain safe bootstrap/fallback defaults; they are not the long-term control plane.
- Changing Portal Runtime settings does not require a Connector restart.
- Existing pending Conversation Bursts keep the timing snapshot they were created with; new bursts use the latest synced config.
- Explicit Character addressing, replies, interaction sessions, and other Runtime-owned fast paths remain immediate.
- Character Card core truth stays separate from Learned State.
- Learned State Inspector is observational; it is not a Character Card editor.
- Topic Memory remains Topic lifecycle authority; Graph is derived evidence.
- Utility provider `enabled` is an Admin/manual state. Runtime quota/cooldown/exhaustion never silently rewrites it.
- Provider quota metadata is shown only when observed or deterministically known. Missing metadata is shown as `Unknown` rather than estimated.
- Free-provider exhaustion never silently becomes paid use on that provider.
- Paid fallback remains separately configured and budget bounded.
- Topic transition reasons are displayed only when an authoritative persisted source exists. Current Topic timeline/status/timing is always inspectable; the Portal does not fabricate a classifier reason that was never persisted.

## Phase 0 — Shared observability contracts — COMPLETE

### Conversation Intelligence

Implemented read-only APIs expose Character-scoped Learned State with:

- state type
- subject type/key plus a readable Topic label when available
- stored value
- current effective/decayed value
- stored/current confidence
- positive/negative evidence counts
- contradiction count
- half-life / expiry
- last evidence timestamp
- bounded recent provenance

Topic inspection is strictly scoped by owner + Discord connection + server + channel + thread and exposes:

- current active Topic
- up to 20 recent Topic records
- status (`active / cooling / closed / archived`)
- label, summary, keywords, participants, open loops
- message count / capsule version
- started / last-active / closed timestamps

No Graph inference is used as Topic truth.

### Utility Gateway

Implemented Runtime snapshot exposes:

- credential readiness
- Runtime health state
- multiple quota dimensions
- remaining / optional limit
- quota unit/type
- reset time
- cooldown until
- last error
- last observed time
- observation source
- latency / error rate

### Turn Collector

Implemented Runtime snapshot combines:

- current Connector effective config from heartbeat
- pending burst/preflight scope counts (best-effort heartbeat observation)
- candidate / bypass / burst / collected / collapsed counters
- bypass reasons
- last burst ID / time / flush reason
- persisted `smart_participation_burst_flushed` activity for reliable recent history

No raw prompts, credentials, embeddings, or unbounded chat history are exposed.

## Phase 1 — Dynamic Conversation Burst control — COMPLETE

### Defaults

- quiet window: **3,000 ms**
- maximum wait: **10,000 ms**
- maximum messages: **5**
- maximum characters: **1,500**

Portal presets:

- Fast: 1.5 s / 4 s
- Balanced: 3 s / 10 s — default
- Patient: 5 s / 15 s

Runtime precedence:

```text
Portal persisted config
    > environment bootstrap/default
    > code default
```

The Connector adopts changed values through its existing bounded synchronization cycle without restart. Each pending burst snapshots its config at creation, so a Portal edit affects new bursts without mutating an already-open timer.

Explicit Character name/address, reply, interaction, and other fast paths remain immediate.

## Phase 2 — Free Pool quota/reset observation and automatic recovery — COMPLETE

Provider responses now preserve authoritative rate-limit metadata where available, including OpenAI-compatible request/token remaining/limit/reset headers and `Retry-After`.

Quota observations support multiple simultaneous dimensions instead of one generic scalar.

Runtime state remains separate from manual Admin state:

```text
Admin: ENABLED / OFF
Runtime: unknown / healthy / degraded / cooling_down / exhausted / unavailable
```

On quota/rate-limit failure:

1. Admin `enabled` remains unchanged;
2. the provider temporarily leaves eligible free routing;
3. authoritative reset/Retry-After is used when available;
4. otherwise bounded cooldown is used;
5. expired `cooling_down` / `exhausted` state becomes probe eligible automatically;
6. success returns the member to `healthy`;
7. repeated 429 updates cooldown/reset and routing continues to the next eligible member.

Portal Free Pool cards now show Runtime health, known quota dimensions, reset/cooldown, observation time/source, and last error. Providers that expose no reliable quota metadata show `Unknown`.

## Phase 3 — Conversation Intelligence Inspector — COMPLETE

A dedicated `Intelligence` Server Notebook tab now separates state inspection from per-turn Behavior Notebook explanations.

### Character view

For a selected Character the Portal shows:

- Character Card reference as authoritative core truth
- Learned Interest
- Expertise
- Stance
- Relationship
- Salience
- Conversation Ownership
- Participation Fatigue

Each Learned State entry exposes:

- readable subject label where available
- current decayed value
- stored value at last evidence
- confidence
- positive/negative evidence counts
- contradiction count
- half-life
- last evidence time
- recent bounded provenance

### Topic view

For the selected Discord Server/Channel scope the Portal shows:

- current Topic
- summary/status
- keywords
- open loops
- message count
- capsule version
- started / last-active / closed timing
- recent Topic timeline

Excluded channels and excluded categories are omitted from the Inspector selector.

Behavior Notebook remains responsible for the separate question: “why did this speaker get selected on this turn?”

## Phase 4 — Portal live control and diagnostics — COMPLETE

### System Intelligence / Conversation Burst

Portal now exposes:

- enable/disable Turn Collector
- Fast / Balanced / Patient presets
- quiet window / maximum wait
- max messages / characters
- current effective Connector config
- pending burst count (heartbeat-best-effort)
- 24h persisted burst / collected / collapsed counts
- last persisted burst timing, latency and flush reason
- per-Connector session counters

`smart_participation_burst_flushed` is also visible in Discord Event Log.

The pending count is intentionally best-effort because a burst normally lives only 3–10 seconds while heartbeat/UI polling is slower. Persisted last-burst and 24h activity are the reliable audit signal.

### Utility Gateway

Free Pool cards expose manual configuration separately from Runtime health and quota/reset observations.

### Conversation Intelligence

The new Server Notebook Inspector makes learned state and Topic history visible without SQLite inspection.

## Phase 5 — Validation and rollout — COMPLETE

Focused checkpoint validation completed:

- Dynamic Burst Runtime config, pending-burst config snapshot, and Free Pool cooldown recovery: passed Python + Connector targeted validation.
- Free Pool quota + Portal controls: workflow `31877569925` passed Python Ruff/strict Mypy/targeted tests and Web typecheck/tests/build.
- Conversation Intelligence Inspector: workflow `31877950586` passed strict Mypy, Learned State/Topic scope tests, and Web typecheck/tests/build.
- Conversation Burst live observability: workflow `31878381444` passed Python validation, Discord Connector typecheck/127 tests/build, Web tests/build, and diff check.
- Inspector readable subjects/category filtering: workflow `31878589506` passed Python strict validation and Web tests/build.

Final clean-head release gate completed on commit `d8d4329735efb9f6ed4306fad2f3c07b5d9bcbcc`:

- CI `#1352` / workflow `31878695567`: **green**
  - Python 3.12 Ruff + strict Mypy + repository-wide Pytest
  - Python 3.13 Ruff + strict Mypy + repository-wide Pytest
  - Web typecheck + tests + production build
  - Discord Connector typecheck + tests + build + image build
  - production Docker build + persistent-storage + health + smoke validation
- Railway Smoke `#1318` / workflow `31878695579`: **green**

Public Demo Status is evaluated separately. The current `main` commit already has a failing Public Demo Status run (`31832019603`) because of the existing demo credential-readiness baseline, so an identical result is not treated as an Observability & Runtime Control regression.

## Delivery rule

All implementation for this roadmap remains in Draft PR `#167` on `agent/observability-runtime-control`. Do not merge automatically; merge requires explicit owner approval.
