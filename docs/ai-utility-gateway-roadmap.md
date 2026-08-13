# AI Utility Gateway Roadmap

Status: **Phase 1 complete · Phase 2 not started**

Branch: `feat/ai-utility-gateway`
Draft integration PR: `#160`

Merge policy: **do not merge to `main` phase-by-phase.** Complete and validate the planned phases first, then make one explicit merge / partial-merge / no-merge decision in Phase 8.

## Goal

Build one Super Admin-managed AI Utility Gateway that supplies low-cost system intelligence to Character Relay while keeping Character models focused on roleplay and keeping Runtime authority deterministic.

The Gateway may advise, classify, summarize, compress, rank, and interpret. It must not bypass Tool permissions, Key Groups, credentials, side-effect validation, scope isolation, cooldowns, idempotency, or other Runtime authority.

## Fixed architecture decisions

- Existing Character Relay Tool Registry remains the execution layer. The Gateway does not invent or directly execute privileged Tools.
- Existing shared local E5 runtime remains the high-frequency semantic engine.
- SQLite remains the source of truth for Topic, Memory, Wiki, provider configuration, and derived vectors for this roadmap. No external Vector DB initially.
- Media remains `SHA-256 -> cache/reference -> media.inspect -> Media Understanding`. No multimodal media embedding in this roadmap.
- Free providers must have renewable/resetting free allowance and must not require mainland-China-style real-name verification/KYC for the intended integration path.
- Free-provider exhaustion must never silently become paid usage on that provider.
- Paid fallback is OpenRouter only.
- Provider API keys are Super Admin-managed and stored server-side in the encrypted Credential Vault.
- Quota state should be event-driven/cached where possible; do not query every provider before every inference call.

## Provider candidates

Free-pool candidates to verify adapter-by-adapter in Phase 2:

- OpenRouter free models
- Groq
- Cerebras
- Cloudflare Workers AI
- Mistral free mode
- SambaNova free tier
- Gemini free tier

Paid fallback:

- OpenRouter only

## Progress

| Phase | Status | Scope |
|---|---|---|
| 0 | Complete foundation | Existing Semantic Runtime + PR #159 base |
| 1 | **Complete** | Gateway config, Portal, Vault credentials |
| 2 | Not started | Quota, health, router, OpenRouter paid fallback |
| 3 | Not started | RAG + Topic Intelligence + E5 ambiguity assistance |
| 4 | Not started | Memory Intelligence on SQLite |
| 5 | Not started | Media Understanding through Gateway, SHA-256 preserved |
| 6 | Not started | LLM Wiki / knowledge consolidation |
| 7 | Not started | Additional System Intelligence consumers |
| 8 | Not started | End-to-end validation and merge decision |

## Phase 0 — Existing semantic foundation

Source: PR #159 and earlier Semantic Runtime work.

Retained foundation:

- shared E5 runtime and query-vector reuse
- semantic RAG gate
- Conversation Topic Memory foundation
- semantic Tool continuation
- Super Admin semantic routing Judge prototype
- Key Groups bulk-apply UI refinement

Phase 0 is not a merge point. The integration branch was created from the validated Phase 0 head while `main` remained untouched.

## Phase 1 — Utility Gateway foundation + Portal management

**Status: COMPLETE**

Implemented:

### Provider-neutral runtime contract

Initial capabilities:

- `semantic_judge`
- `topic_intelligence`
- `memory_intelligence`
- `knowledge_wiki`
- `context_compiler`
- `media_understanding`
- `structured_summary`

Added provider members with:

- stable member ID
- provider / model / base URL
- enabled state
- capability membership
- priority
- enforced `FREE ONLY` membership
- duplicate-ID validation

Gateway defaults to disabled. Paid fallback defaults to disabled and is structurally restricted to OpenRouter.

### Super Admin Portal

System Intelligence workspace now supports:

- Gateway enable/disable
- routing strategy configuration
- add/edit/remove free-provider members
- provider/model/base URL
- capability membership
- priority
- credential configured/missing state
- OpenRouter-only paid fallback model
- daily/monthly paid-fallback budget settings

New provider members must be saved into System Intelligence configuration before their Vault credential scope exists.

### Credential lifecycle

- per-member scope: `utility:{member_id}`
- encrypted Credential Vault only
- Admin-only credential status/configure/delete endpoints
- raw API keys are never returned to the browser
- unknown members are rejected
- removing a provider member cleans its corresponding Vault credential to avoid orphaned secrets
- existing Credential UI is reused rather than introducing a second secret-handling path

### Compatibility / safety

- pre-Gateway Admin Runtime configuration migrates to the new schema with Gateway disabled
- existing Character, Tool, Topic, Memory, RAG, and Media consumers are not migrated in Phase 1
- Gateway being disabled therefore preserves existing Runtime behavior

### Phase 1 validation

Validated on integration head `68e5217d8978e63acf26b1ed9b6ecd1a5fbd3f58`:

- CI run `#1071`: **SUCCESS**
  - Python 3.12: Ruff, Mypy, Pytest success
  - Python 3.13: Ruff, Mypy, Pytest success
  - Web: typecheck, tests, build success
  - Discord connector: typecheck, tests, build/image success
  - Docker production smoke checks success
- Railway Smoke run `#1037`: **SUCCESS**
- focused Phase 1 tests cover:
  - duplicate/non-free member rejection
  - Admin-only credential management
  - unknown-member rejection
  - no secret echo
  - encrypted-at-rest credential storage
  - removed-member credential cleanup
  - old-config migration
  - disabled/safe defaults

Public Demo Status is an external deployment-status signal and is not used as the Phase 1 code-validation gate.

Phase 1 boundary: **stop here. Do not start Phase 2 automatically and do not merge `main`.**

## Phase 2 — Quota, health, routing, and OpenRouter paid fallback

Implement the actual Utility Gateway selection/runtime layer.

### Normalized provider telemetry

Each provider adapter should expose, where available:

- `healthy / degraded / unavailable / cooling_down / exhausted`
- remaining requests/tokens/credits/neurons
- reset time/window
- observation source: response header / quota API / local meter / estimated
- last observed time
- latency and recent error rate

Do not poll before every request. Update state from real responses and reconcile only when stale, manually refreshed, or after quota/provider errors.

### Routing

Selection order considers:

1. requested capability
2. FREE ONLY eligibility
3. quota availability
4. health/cooldown
5. recent error rate
6. latency
7. configured priority

### Paid fallback

- OpenRouter only
- explicitly enabled only
- daily/monthly budget caps enforced by Runtime
- no free provider may silently become paid
- each consumer defines its all-free-failed degradation behavior

Exit criteria:

- at least two real free adapters demonstrate routing/fallback
- quota exhaustion and cooldown tests
- paid fallback cannot activate unless explicitly enabled
- Observation exposes provider/model/tier/routing reason

## Phase 3 — Semantic + Topic Intelligence

### RAG

- replace the fixed Judge cascade with `capability=semantic_judge`
- keep high-confidence E5 decisions deterministic
- contextual fallback requires explicit Judge approval
- contextual Judge failure remains RAG OFF

### Topic Memory

E5 handles obvious continuation/switch cases. Utility Gateway handles only gray-zone discourse intent such as:

- continue
- switch
- clarify
- close
- capsule refresh recommendation
- resolved/new open-loop suggestions

Runtime remains authoritative for topic scope, lifecycle, and persistence.

### E5 assistance

Gateway may assist only with difficult cases:

- ambiguity resolution
- query rewrite
- reranking suggestions

It does not replace shared local E5.

Exit criteria:

- topic continuation no longer depends on brittle phrase/regex behavior
- unrelated turns do not inherit old Knowledge context
- scope-isolation tests remain green
- trace shows E5 score + Judge use + final decision

## Phase 4 — Memory Intelligence on SQLite

Keep SQLite as source of truth and do not introduce a Vector DB yet.

Memory records should support:

- owner/character/scope
- memory type/content
- confidence/importance
- source message/event references
- timestamps/last-used
- superseded/merged relationships
- E5 vector linkage through the semantic-vector layer

Retrieval:

- reuse the current-turn shared E5 vector
- retrieve bounded scoped candidates
- cosine/top-K locally

Gateway may advise:

- extract / ignore
- reinforce existing memory
- duplicate detection
- merge
- conflict detection
- supersede/update
- consolidation
- importance

Runtime performs all writes.

Exit criteria:

- duplicate/repeated preference growth is bounded
- update/supersede and scope-isolation tests pass
- Gateway failure cannot corrupt or block ordinary memory retrieval
- no external Vector DB dependency

## Phase 5 — Media Understanding through Utility Gateway

Preserve existing epistemic and cache behavior:

`media source -> SHA-256/cache/reference -> media.inspect -> Utility Gateway media_understanding -> cached perceived result`

Requirements:

- no media embedding/vector pipeline
- reuse successful SHA-256 cached understanding according to existing scope/privacy rules
- provider selection uses actual modality capability
- images route only to vision-capable members
- video keeps the current direct/extraction strategy without cross-modal embeddings
- failed or declined inspection preserves correct epistemic state
- paid Media fallback is OpenRouter only

Exit criteria:

- existing `media.inspect` semantics remain intact
- cache hit avoids repeat model calls
- provider failure/fallback paths tested
- no false claim that Character saw content before successful inspection

## Phase 6 — LLM Wiki / knowledge consolidation

Wiki is a derived knowledge layer, not a replacement for raw sources.

SQLite Wiki pages should track:

- title/key
- summary/body
- source IDs + source version/hash
- generated/updated timestamps
- confidence/state
- stale flag

Gateway jobs may perform:

- source condensation
- page creation/update suggestion
- split/merge suggestion
- stale-source reconciliation
- contradiction flagging

Retrieval policy:

- Wiki can answer common overview questions compactly
- raw RAG remains available for detailed/evidence-sensitive questions
- provenance is mandatory
- stale Wiki never silently overrides newer source evidence

Exit criteria:

- source changes mark/rebuild affected pages
- repeated/common questions use fewer prompt tokens when Wiki is sufficient
- raw provenance remains available

## Phase 7 — System Intelligence extensions

Only after the core Gateway is stable, consider:

- Topic capsule refresh/compression
- conversation/interaction summarization
- Context Compiler / prompt-budget planning
- duplicate context detection across Topic/Memory/RAG/Media
- structured extraction from Tool/provider results
- Smart Participation gray-zone/tie-break Judge
- Tool continuation ambiguity assistance using the existing Tool Registry
- background Memory/Knowledge maintenance jobs
- provider quality sampling and model A/B observations

Explicitly excluded:

- permission decisions
- credential decisions
- Tool side-effect authorization
- autonomous destructive database maintenance

Every consumer must be independently disableable, and Utility failure must not block Character turns.

## Phase 8 — End-to-end validation and merge decision

No automatic merge.

Validation matrix includes:

- English / Simplified Chinese / Traditional Chinese / mixed language; Malay where useful
- RAG false positives/negatives
- Topic continue/switch/close
- Memory duplicate/update/conflict
- Media cache hit/miss/provider failure
- all-free-exhausted behavior
- OpenRouter paid fallback and budget caps
- provider outage/timeout/malformed structured output
- restart persistence
- credential isolation
- multi-user / multi-character / deployment scope isolation
- token/latency/provider-call observations
- Railway baseline and peak RAM comparison

Final questions:

- Is Gateway measurably more reliable than the fixed-model Judge?
- Are free-tier savings meaningful without unacceptable latency?
- Is Portal operation safe and understandable?
- Did Topic/RAG false positives improve?
- Is Memory useful without excessive storage/model traffic?
- Does Wiki reduce repeat-context cost while preserving provenance?
- Is Media at least as reliable as the current SHA-256 behavior?
- Is Railway RAM/latency acceptable?
- Are CI, smoke tests, and manual validation green?

Possible outcomes:

1. merge the integration branch to `main`
2. split and merge selected phases only
3. keep it experimental and do not merge

## Phase execution rule

For every phase:

1. inspect the current integration branch and relevant live code
2. implement only that phase
3. add focused tests
4. run CI + Railway Smoke
5. fix failures without broad suppressions
6. update this roadmap with results and measurements
7. stop at the phase boundary and report status
8. do **not** merge `main`
