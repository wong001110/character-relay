# AI Utility Gateway Roadmap

Status: **integration work in progress**

Branch: `feat/ai-utility-gateway`

Merge policy: **do not merge to `main` phase-by-phase.** Complete and validate all planned phases first, then make one explicit merge/no-merge decision in Phase 8.

## Goal

Build one Super Admin-managed AI Utility Gateway that supplies low-cost system intelligence to Character Relay while keeping Character models focused on roleplay and keeping Runtime authority deterministic.

The Gateway may advise, classify, summarize, compress, rank, and interpret. It must not bypass Tool permissions, Key Groups, credentials, side-effect validation, scope isolation, cooldowns, idempotency, or other Runtime authority.

## Fixed architecture decisions

- Existing Character Relay Tool Registry remains the execution layer. The Gateway does not invent or execute privileged Tools.
- Existing shared local E5 embedding runtime remains the high-frequency semantic engine.
- SQLite remains the source of truth for Topic, Memory, Wiki, provider configuration, and derived vectors for this roadmap. No external Vector DB in the initial implementation.
- Existing media behavior remains `SHA-256 -> cache/reference -> media.inspect -> Media Understanding`. No multimodal media embedding in this roadmap.
- Free providers must have renewable/resetting free allowance and must not require mainland-China-style real-name verification/KYC for the intended integration path.
- Free-provider exhaustion must never silently become paid usage on that provider.
- Paid fallback is OpenRouter only.
- Provider API keys are Super Admin-managed and stored server-side in the encrypted Credential Vault.
- Quota status is event-driven/cached where possible; do not query every provider before every inference call.

## Candidate provider set

Initial adapters are limited to providers that can plausibly satisfy the renewable-free-allowance requirement. Exact model IDs and quota telemetry mechanisms are verified when each adapter is implemented.

Core candidates:

- OpenRouter free models
- Groq
- Cerebras
- Cloudflare Workers AI
- Mistral free mode
- SambaNova free tier
- Gemini free tier

Paid fallback:

- OpenRouter only

## Phase 0 — Existing semantic foundation

Source: PR #159 and earlier Semantic Runtime work.

Already available / retained:

- shared E5 runtime and query-vector reuse
- semantic RAG gate foundation
- Conversation Topic Memory foundation
- semantic Tool continuation
- Super Admin semantic routing Judge prototype
- Key Groups bulk-apply UI refinement

Phase 0 is **not** a merge point. It is the base for this integration branch.

Exit criteria:

- `main` remains untouched
- integration branch starts from the validated Phase 0 head

## Phase 1 — Utility Gateway foundation + Portal management

Build the provider-neutral core before adding provider-specific quota logic.

### Backend

- `UtilityCapability` contract, initially:
  - `semantic_judge`
  - `topic_intelligence`
  - `memory_intelligence`
  - `knowledge_wiki`
  - `context_compiler`
  - `media_understanding`
  - `structured_summary`
- provider/member configuration model
- pool membership and capability assignment
- routing policy model
- encrypted per-provider credential scopes
- SQLite persistence for secret-free provider/pool configuration
- disabled-by-default Gateway runtime
- deterministic no-provider/no-credential degradation

### Portal

Super Admin workspace for:

- add/edit/disable provider members
- provider/model/base URL
- capability membership
- FREE ONLY flag
- credential configured/missing state
- paid OpenRouter fallback settings
- pool priority/order
- health/quota placeholders for later phases

### Non-goals

- no live quota adapter yet
- no Topic/Memory/Media consumer migration yet
- no LLM Wiki yet

Exit criteria:

- configuration survives restart
- secrets never return to browser
- admin authorization enforced
- no existing Character/Media/Tool behavior changes when Gateway disabled
- Python + Web + Discord + Docker + Railway Smoke green

## Phase 2 — Quota, health, routing, and OpenRouter paid fallback

Implement provider adapter contracts and runtime selection.

### Provider telemetry

Each adapter exposes a normalized snapshot where available:

- healthy / degraded / unavailable / cooling_down / exhausted
- remaining requests/tokens/credits/neurons when knowable
- reset time/window when knowable
- observation source: response header / provider API / local meter / estimated
- last observed time
- latency and recent error rate

Do not poll before each model call. Update on real responses and reconcile only when stale, manually refreshed, or after quota/provider errors.

### Routing

Selection considers:

1. capability compatibility
2. FREE ONLY eligibility
3. quota not exhausted
4. health/cooldown
5. recent error rate
6. latency
7. configured priority

### Paid fallback

- OpenRouter only
- explicit enable/disable
- optional daily/monthly budget caps
- no other provider may silently switch from free to paid
- all-free-failed behavior must be defined per consumer

Exit criteria:

- at least two free adapters prove real routing/fallback behavior
- quota exhaustion/cooldown tests
- paid fallback cannot activate unless explicitly enabled
- Observation can identify selected provider/model/tier/reason

## Phase 3 — Semantic + Topic Intelligence consumers

Move the most valuable low-risk semantic decisions onto the Gateway.

### RAG

- replace fixed Judge model cascade with `capability=semantic_judge`
- keep high-confidence E5 decisions deterministic
- contextual fallback requires explicit Judge approval
- Judge failure for contextual fallback stays RAG OFF

### Topic Memory

Use E5 for obvious continuation/switch decisions and Utility Gateway only for gray-zone discourse intent.

Judge output is structured/advisory, for example:

- `continue`
- `switch`
- `clarify`
- `close`
- confidence
- capsule refresh recommendation
- resolved/new open-loop suggestions

Runtime remains authoritative for topic scope/lifecycle/persistence.

### E5 assistance

Gateway may help only with difficult semantic cases:

- ambiguity resolution
- query rewrite
- reranking suggestions

It does not replace the shared E5 model.

Exit criteria:

- Topic continuation no longer depends on brittle phrase/regex behavior
- unrelated turns do not inherit old Knowledge context
- Topic scope isolation tests remain green
- traces expose E5 score + Judge use + final decision

## Phase 4 — Memory Intelligence on SQLite

Add durable Memory without introducing a separate Vector DB.

### Storage

SQLite source-of-truth records for:

- memory item/content
- owner/character/scope
- memory type
- confidence / importance
- source message/event references
- timestamps / last-used
- superseded/merged relationships
- derived E5 vector record or existing semantic-vector repository integration

### Retrieval

- shared E5 vector for current turn
- scoped candidate retrieval
- cosine/top-K over bounded candidates
- no external ANN database initially

### Utility intelligence

Gateway may advise:

- extract / ignore
- reinforce existing memory
- duplicate detection
- merge
- conflict detection
- supersede/update
- consolidation
- importance

Runtime validates and performs writes.

Exit criteria:

- bounded memory growth in duplicate/repeated-preference tests
- update/supersede tests
- scope isolation tests
- Gateway failure does not corrupt or block memory retrieval
- no Vector DB dependency

## Phase 5 — Media Understanding through Utility Gateway

Keep existing media epistemic/cache architecture.

Flow remains:

`media source -> SHA-256/cache/reference -> media.inspect -> Utility Gateway media_understanding -> cached perceived result`

Requirements:

- no media vector/embedding pipeline
- reuse successful SHA-256 cached understanding across eligible consumers according to current scope/privacy rules
- provider selection based on actual modality support
- images use capable vision providers
- video keeps current extraction/direct-provider strategy without introducing cross-modal embeddings
- failed/declined inspection must preserve epistemic state accurately
- paid media fallback is OpenRouter only

Exit criteria:

- current `media.inspect` semantics unchanged
- cache-hit path avoids repeat model calls
- fallback/provider failure tests
- no false claim that Character saw content before successful inspection

## Phase 6 — LLM Wiki / Knowledge consolidation

Implement Wiki as a derived knowledge layer, not a replacement for raw sources.

### Wiki records

SQLite pages include:

- title/key
- summary/body
- source IDs and source versions/hashes
- generated/updated timestamps
- confidence/state
- stale flag

### Builder

Utility Gateway performs bounded jobs:

- source condensation
- page creation/update suggestion
- page split/merge suggestion
- stale-source reconciliation
- contradiction flagging

### Retrieval policy

- Wiki may satisfy common overview questions with a compact answer context
- raw RAG remains available for detailed/evidence-sensitive questions
- source traceability is mandatory
- Wiki-generated text is never treated as an untraceable ground-truth replacement

Exit criteria:

- source changes mark/rebuild affected Wiki pages
- Wiki can reduce prompt tokens for repeat/common questions
- raw source citations/provenance remain available
- stale Wiki cannot silently override newer raw source evidence

## Phase 7 — System Intelligence extensions

Add system-level consumers only after the core Gateway is proven stable.

Primary candidates:

- Topic capsule refresh/compression
- conversation/interaction summarization
- Context Compiler for prompt-budget planning
- duplicate context detection across Topic/Memory/RAG/Media
- structured extraction from provider/tool results
- Smart Participation gray-zone/tie-break Judge
- Tool continuation ambiguity assistance using existing Tool Registry only
- background knowledge/memory maintenance jobs
- provider quality sampling and model A/B observations

Explicitly excluded:

- direct permission decisions
- credential decisions
- Tool side-effect authorization
- autonomous destructive database maintenance

Exit criteria:

- each consumer can be independently disabled
- no single Utility failure blocks Character turns
- prompt-size/latency impact measured, not assumed

## Phase 8 — End-to-end validation and merge decision

No automatic merge.

### Validation matrix

- multilingual conversations: English, Simplified/Traditional Chinese, mixed language; add Malay where useful
- RAG false-positive/false-negative cases
- Topic continuation/switch/close cases
- Memory duplicate/update/conflict cases
- media cache-hit/cache-miss/provider-failure cases
- all-free-exhausted behavior
- OpenRouter paid fallback with budget cap
- provider outage / timeout / malformed JSON
- restart persistence
- credential isolation
- multi-user / multi-character / deployment scope isolation
- token/latency/provider-call observations
- Railway memory baseline and peak comparison

### Merge decision checklist

Only after all phases:

- Is Gateway measurably more reliable than the current fixed-model semantic Judge?
- Are free-provider savings meaningful without unacceptable latency?
- Is Portal management understandable enough to operate safely?
- Did Topic/RAG false positives improve?
- Is Memory useful without excessive storage or model traffic?
- Does Wiki reduce repeat-context cost while preserving provenance?
- Is Media behavior at least as reliable as the current SHA-256 design?
- Is Railway RAM/latency still acceptable?
- Are all CI/smoke/manual validation checks green?

Possible outcomes:

1. merge whole integration branch to `main`
2. merge selected phases only after splitting/rebasing
3. keep experimental and do not merge

## Phase execution rule

For every phase:

1. inspect current integration branch and relevant live code
2. implement only that phase's scope
3. add/adjust focused tests
4. run CI + Railway Smoke
5. inspect failures and fix without broad suppressions
6. update this roadmap with completion notes and measurements
7. stop at the phase boundary and report status
8. do **not** merge `main`
