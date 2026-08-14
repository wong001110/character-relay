# AI Utility Gateway Roadmap

Status: **Phase 6 implementation complete · Phase 7 not started · Phase 8 validation/merge pending**

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
- Derived Wiki content never becomes more authoritative than its source Knowledge documents.

## Provider candidates

Free-pool candidates to verify adapter-by-adapter:

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
| 2 | Implemented | Quota, health, router, OpenRouter paid fallback; real-provider matrix remains part of Phase 8 validation |
| 3 | Implemented | RAG + Topic Intelligence + E5 ambiguity assistance |
| 4 | Implemented | Memory Intelligence on SQLite |
| 5 | Implemented | Media Understanding through Gateway, SHA-256 preserved |
| 6 | **Complete** | LLM Wiki / knowledge consolidation + conservative live overview retrieval |
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

- provider-neutral capability contract for `semantic_judge`, `topic_intelligence`, `memory_intelligence`, `knowledge_wiki`, `context_compiler`, `media_understanding`, and `structured_summary`
- provider members with stable ID, provider/model/base URL, enabled state, capabilities, priority, and enforced `FREE ONLY` membership
- Super Admin Gateway enable/disable, routing strategy, provider membership, paid-fallback model, and budget configuration
- per-member encrypted Vault credential scope `utility:{member_id}`
- Admin-only credential status/configure/delete endpoints
- raw API keys never returned to the browser
- removed provider members clean orphaned Vault credentials
- pre-Gateway configuration migrates with Gateway disabled and safe defaults

Validation on Phase 1 head `68e5217d8978e63acf26b1ed9b6ecd1a5fbd3f58`:

- CI `#1071`: **SUCCESS**
- Railway Smoke `#1037`: **SUCCESS**
- Python 3.12/3.13 Ruff, strict Mypy, Pytest success
- Web typecheck/tests/build success
- Discord connector typecheck/tests/build/image success
- Docker production smoke success

## Phase 2 — Quota, health, routing, and OpenRouter paid fallback

**Status: IMPLEMENTED · live-provider matrix deferred to Phase 8**

Implemented runtime behavior:

- normalized provider states: `healthy / degraded / unavailable / cooling_down / exhausted`
- persisted provider telemetry and usage records
- remaining quota/reset observations when a provider exposes them
- error-rate, latency, cooldown, and configured-priority routing inputs
- FREE ONLY provider selection by requested capability
- provider clients reused through the existing Character Relay provider layer
- provider errors update routing state instead of polling every provider before every request
- free-pool exhaustion never silently becomes paid usage
- OpenRouter-only paid fallback requires explicit enablement and enforces daily/monthly budgets
- Observation/runtime results retain provider, model, tier, routing reason, attempts, latency, token use, and paid-cost fields

Focused tests cover free-provider fallback, quota/cooldown state, disabled paid fallback, and budget rejection. Real-account/provider allowance behavior remains an explicit Phase 8 validation item because CI uses deterministic offline transports rather than consuming production free quotas.

## Phase 3 — Semantic + Topic Intelligence

**Status: IMPLEMENTED**

RAG:

- high-confidence E5 decisions remain deterministic
- ambiguous routing can use `capability=semantic_judge`
- current-message evidence is prioritized
- contextual fallback requires Utility/Judge approval
- contextual Judge failure keeps RAG OFF so older Knowledge context cannot leak into unrelated turns

Topic Memory:

- E5 handles obvious continuation/switch cases
- Utility can assist gray-zone discourse intent such as continue, switch, clarify, close, capsule refresh, and open-loop interpretation
- Runtime remains authoritative for topic scope, lifecycle, persistence, and Tool permissions

The Gateway assists ambiguity; it does not replace the shared local E5 runtime.

## Phase 4 — Memory Intelligence on SQLite

**Status: IMPLEMENTED**

SQLite remains the source of truth. Durable scoped memory support includes:

- owner/character/scope
- memory type/content
- confidence/importance
- source references and timestamps
- superseded/merged relationships
- E5 vector linkage through the existing semantic-vector layer

Gateway advice can cover extract/ignore, reinforce, duplicate detection, merge, conflict, supersede/update, consolidation, and importance. Runtime performs all writes and ordinary retrieval remains available if Utility inference fails.

No external Vector DB dependency is introduced.

## Phase 5 — Media Understanding through Utility Gateway

**Status: IMPLEMENTED**

Preserved epistemic/cache flow:

`media source -> SHA-256/cache/reference -> media.inspect -> Utility Gateway media_understanding -> cached perceived result`

Properties retained:

- no media embedding/vector pipeline
- successful SHA-256 cached understanding can avoid repeat provider calls under existing scope/privacy rules
- provider selection respects modality capability
- video keeps the current direct/extraction/keyframe strategy rather than introducing cross-modal embeddings
- failed or declined inspection preserves the correct unseen/unperceived state
- paid Media fallback remains OpenRouter-only
- Character models do not need to spend their roleplay API allowance on Runtime-owned media classification/routing work

## Phase 6 — LLM Wiki / knowledge consolidation

**Status: COMPLETE**

Wiki is a derived Knowledge layer, not a replacement for raw sources.

### Persistence and provenance

SQLite Wiki pages now track:

- stable owner/base/page identity
- title/key and compact body
- keywords
- source manifest containing source IDs, titles, source type, and content SHA-256
- stable source snapshot SHA-256
- confidence
- stale state
- created/updated timestamps

Raw source document bodies are not duplicated into the Wiki provenance manifest.

### Source lifecycle

- Knowledge Document insert/update/delete marks affected Wiki pages stale
- Knowledge Base metadata changes mark affected pages stale
- Knowledge Base deletion removes derived Wiki rows
- account/workspace claim and delete lifecycle migrates/cleans Wiki ownership so bulk SQL operations cannot leave owner-orphaned derived data
- current-page lookup independently verifies the source snapshot hash, so a stale page cannot silently remain current even if an event path is missed

Rebuild is intentionally lazy: a changed source marks the derived page stale immediately, and the next eligible overview request rebuilds it. This avoids background provider traffic merely because an admin edited a source.

### Gateway consolidation

`KnowledgeWikiService` builds a bounded source snapshot and uses the existing `knowledge_wiki` Utility capability. It:

- reuses an existing page when the source hash is unchanged
- creates/updates only from bounded supplied source text
- persists the concrete derived result plus provenance hash/manifest
- degrades to raw Knowledge if the Utility Gateway is disabled, unavailable, exhausted, times out, or returns invalid output

### Conservative live retrieval

The default app Knowledge repository is now Wiki-aware, while the raw repository remains directly available.

Live policy is deliberately narrow:

- explicit overview/summary/introduction/explanation-style questions may lazy-build or reuse one compact Wiki overview
- English plus Simplified/Traditional Chinese overview markers are supported
- exact/verbatim/quote/citation/source/evidence/document-detail questions always keep raw RAG authoritative
- Wiki is used only when the raw retrieval identifies one unambiguous Knowledge Base
- multi-base ambiguity stays on raw RAG
- Wiki failures return the original raw candidates unchanged
- the synthetic Wiki context identifies itself as derived, includes source snapshot SHA-256, and lists bounded provenance references

This is a prompt-cost optimization, not an authorization or truth decision.

### Phase 6 tests

Focused coverage proves:

- same source hash reuses an existing Wiki page without another Utility call
- source changes stale and rebuild the overview
- stale Wiki cannot be returned as current
- Utility failure leaves raw RAG usable
- exact/evidence queries do not call the Wiki path
- broad overview queries can use the compact derived page
- compact Wiki context is smaller than the equivalent multi-chunk raw RAG context in the regression fixture
- Knowledge Base deletion and account lifecycle do not leave derived Wiki orphans

### Phase 6 integrated validation

Validated on integration head `52a978277eb2ecece6064c4725938df1cd880eab`:

- CI `#1098`: **SUCCESS**
  - Python 3.12: Ruff, strict Mypy, full Pytest success
  - Python 3.13: Ruff, strict Mypy, full Pytest success
  - Web: typecheck, tests, build success
  - Discord connector: typecheck, tests, build/image success
  - Docker production smoke checks success
- Railway Smoke `#1064`: **SUCCESS**

Public Demo Status `#808` remains an external demo-readiness failure, not a Phase 6 code gate. Its last response reports 5 demo Character Cards but only 3 credential-ready Characters, the same external readiness mismatch class that predates this phase.

**Phase 6 boundary: stop here. Do not start Phase 7 automatically and do not merge `main`.**

## Phase 7 — System Intelligence extensions

**Status: NOT STARTED**

Only after the core Gateway is explicitly approved to continue, consider:

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

**Status: NOT STARTED**

No automatic merge.

Validation matrix includes:

- English / Simplified Chinese / Traditional Chinese / mixed language; Malay where useful
- RAG false positives/negatives
- Topic continue/switch/close
- Memory duplicate/update/conflict
- Media cache hit/miss/provider failure
- all-free-exhausted behavior
- real free-provider allowance/reset behavior
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
- Are CI, smoke tests, real-provider checks, and manual validation green?

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
