# Post-V4 Observability & Runtime Control Roadmap

Status: **PLANNED / ACTIVE IN DRAFT PR**

Branch: `agent/observability-runtime-control`

## Goal

Turn the completed V4 and AI Utility Gateway foundations into systems that are easy to inspect and tune from Portal without Railway environment edits, Connector restarts, or direct SQLite inspection.

This roadmap covers three related gaps discovered after V4 production rollout:

1. Conversation Intelligence has learned state and Topic state, but Portal does not yet show current values, evidence, decay, or Topic transitions clearly.
2. AI Utility Gateway persists normalized quota/health fields, but live providers do not yet expose enough remaining/reset metadata to Portal, and cooldown expiry does not reliably re-admit a provider for probing.
3. Conversation Burst / Turn Collector is live, but timing is still boot-time environment configuration rather than a dynamically tunable Runtime setting.

## Fixed decisions

- Portal-persisted Runtime configuration takes precedence over environment bootstrap defaults.
- Environment variables remain safe bootstrap/fallback defaults; they are not the long-term control plane.
- Changing Portal Runtime settings must not require a Connector restart.
- Existing pending Conversation Bursts keep the timing snapshot they were created with; new bursts use the latest synced config.
- Explicit Character addressing, replies, interaction sessions, and other Runtime-owned fast paths remain immediate.
- Character Card core truth stays separate from Learned State.
- Learned State Inspector is observational; it must not become a hidden Character Card editor.
- Topic Memory remains Topic lifecycle authority; Graph is derived evidence.
- Utility provider `enabled` is an Admin/manual state. Runtime quota/cooldown/exhaustion must never silently rewrite it.
- Provider quota metadata is shown only when observed or deterministically known. Do not invent remaining quota estimates.
- Free-provider exhaustion never silently becomes paid use on that provider.
- Paid fallback remains separately configured and budget bounded.

## Phase 0 — Shared observability contracts

Add stable API contracts for Portal inspection before expanding UI.

### Conversation Intelligence snapshot

Expose Character-scoped Learned State with:

- state type
- subject type/key and readable label when available
- stored value
- current effective/decayed value
- confidence
- positive/negative evidence counts
- contradiction count
- half-life / expiry
- last evidence timestamp
- bounded provenance entries

Expose Topic scope inspection with:

- current active Topic
- recent Topic records
- status (`active / cooling / closed / archived`)
- label, keywords, participants, open loops
- message count / capsule version
- started / last-active / closed timestamps
- bounded transition reason/evidence where available

### Utility Gateway snapshot

Expose the existing provider Runtime snapshot to Admin Portal:

- manual enabled state
- configured credential state
- Runtime health state
- remaining quota observations
- quota unit/type
- reset time
- cooldown until
- last error
- last observed time
- observation source
- latency / error rate

### Turn Collector runtime snapshot

Expose current effective config and live counters:

- enabled
- quiet window
- maximum wait
- max messages
- max characters
- pending burst/preflight scopes
- collected / bypass / burst / collapsed counts
- bypass reasons
- last burst ID / time / flush reason

Exit criteria:

- Portal can query all three systems without raw SQL or Railway access.
- no raw prompts, credentials, embeddings, or unbounded chat history are exposed.

## Phase 1 — Dynamic Conversation Burst control

Move Turn Collector timing from boot-time-only env configuration to a persisted Portal-controlled Runtime profile.

### New defaults

- quiet window: **3,000 ms**
- maximum wait: **10,000 ms**
- maximum messages: **5**
- maximum characters: **1,500**

Portal should offer presets:

- Fast: 1.5 s / 4 s
- Balanced: 3 s / 10 s — default
- Patient: 5 s / 15 s

### Runtime precedence

```text
Portal persisted config
    > environment bootstrap/default
    > code default
```

### Live sync

Connector receives config through the existing periodic server synchronization path or a bounded dedicated config fetch. Runtime reconfiguration must not require process restart.

The implementation must avoid mutating timers of already-open bursts. A burst captures the effective collector config when it is opened; subsequent bursts use the new config.

Exit criteria:

- changing quiet/max wait in Portal affects new bursts without Railway redeploy/restart;
- currently pending bursts finish under their original timing snapshot;
- explicit/reply fast-path latency remains unchanged;
- Portal shows the effective value currently used by Connector.

## Phase 2 — Free Pool quota / reset observation and automatic recovery

Complete the response-driven provider quota state machine.

### Provider observations

Normalize provider metadata where available, including:

- `Retry-After`
- request remaining/reset
- token remaining/reset
- daily request/token limits when exposed
- credit/quota balance when exposed
- provider-specific units such as Cloudflare neurons only when the API exposes an authoritative value

Quota observations should support multiple simultaneous dimensions rather than forcing all providers into one generic scalar.

Suggested shape:

```text
quota_dimensions[]
  kind
  remaining
  limit (optional)
  unit
  reset_at
  window_seconds (optional)
  source
```

When a provider exposes no reliable quota metadata, Portal must show `Unknown`, not an estimate.

### Runtime state machine

Manual state and Runtime state stay separate:

```text
Admin: ENABLED / OFF
Runtime: unknown / healthy / degraded / cooling_down / exhausted / unavailable
```

On quota/rate-limit failure:

1. preserve Admin `enabled=true`;
2. temporarily remove the member from eligible routing;
3. use provider reset/Retry-After when available;
4. otherwise apply bounded backoff;
5. once cooldown/reset expires, return the provider to a probe-eligible state;
6. successful probe -> `healthy`;
7. repeated 429 -> update cooldown/reset and continue to next free member.

Fix the current recovery gap where an expired `cooling_down` record can remain permanently excluded because the persisted status is never normalized back to a probe-eligible state.

### Portal Free Pool cards

Show per member:

- Admin enabled state
- Runtime health
- Key readiness
- remaining/reset for all known quota dimensions
- cooldown countdown/reset timestamp
- last observed timestamp
- last provider error
- observation source

Exit criteria:

- rate-limited free providers automatically leave routing temporarily;
- reset/cooldown expiry automatically makes them probe eligible again without Admin toggles or restart;
- no quota field is fabricated when provider metadata is unavailable;
- Free Pool UI explains why a provider is currently eligible or skipped.

## Phase 3 — Conversation Intelligence Inspector

Add a dedicated Portal Inspector rather than overloading Behavior Notebook.

### Character view

For each Character:

- Core Interests from Character Card — read-only authoritative reference
- Learned Interests
- Expertise
- Stance
- Relationships
- Salience
- Conversation Ownership
- Participation Fatigue

Each Learned State card shows:

- current effective value
- stored value at last evidence
- confidence
- evidence counts
- half-life / decay direction
- last evidence time
- recent provenance/evidence timeline

Core and Learned values must be visually separate so users do not mistake derived state for Character Card edits.

### Topic view

By Discord connection / Server / Channel / Thread:

- current Topic
- status
- summary/label
- keywords
- participants
- open loops
- message count
- capsule version
- started/last-active/closed times
- recent Topic timeline
- transition reason when available

### Behavior Notebook integration

Behavior Notebook remains turn-focused and should explain why a speaker was selected:

- deterministic base
- raw E5
- active Topic evidence
- Dynamic Interest
- Expertise
- Relationship
- Ownership
- Fatigue
- Utility adjustment
- final score / selection reason

The Inspector answers "what is the state now?"; Behavior Notebook answers "why did this turn happen?".

Exit criteria:

- a user can answer "what is Ann interested in now?" without SQLite inspection;
- a user can answer "why did this Interest change?" from bounded provenance;
- a user can answer "what is the current Topic and when did it switch?" from Portal;
- current state and per-turn decision explanations remain separate views.

## Phase 4 — Portal live control and diagnostics

Bring the three systems into a coherent admin/diagnostic UX.

### Smart Participation Studio

Add Conversation Burst controls and live status:

- Enable Turn Collector
- preset selector
- quiet window
- maximum wait
- advanced max messages/chars
- current effective Connector config
- current pending state
- last burst summary
- cumulative collected/collapsed/bypass counters

### Utility Gateway

Upgrade Free Pool provider cards with Runtime health and quota/reset state.

### Conversation Intelligence

Add a dedicated Inspector entry from Portal/Discord workspace with Character and Topic tabs.

Exit criteria:

- no Railway env edit is needed for ordinary Turn Collector tuning;
- quota/reset problems are diagnosable from Portal;
- learned state and Topic changes are inspectable from Portal.

## Phase 5 — Validation and rollout

Automated validation:

- Python Ruff / strict Mypy / full Pytest
- Web typecheck / tests / build
- Discord Connector typecheck / tests / build
- Docker production smoke
- Railway Smoke

Required focused scenarios:

1. change Turn Collector 3 s -> 5 s without restart; next burst uses 5 s while an already-open burst retains 3 s;
2. explicit Character address still bypasses Turn Collector immediately;
3. 429 with Retry-After enters cooldown and automatically becomes probe eligible after expiry;
4. exhausted quota with reset timestamp becomes probe eligible at reset;
5. missing quota headers display Unknown rather than fabricated values;
6. multiple quota dimensions render independently;
7. Learned Interest effective value decays correctly in Inspector;
8. provenance explains recent positive/negative Interest changes;
9. Topic current/recent timeline respects owner/server/channel/thread scope;
10. Inspector cannot edit Character Card core truth or cross owner/scope boundaries.

## Delivery rule

All implementation for this roadmap stays in one Draft PR on `agent/observability-runtime-control` until validation is complete. Do not merge automatically; merge requires explicit owner approval.
