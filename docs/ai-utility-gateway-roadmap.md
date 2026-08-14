# AI Utility Gateway Roadmap

Status: **Phase 7 complete · Phase 8 validation complete · decision: HOLD / do not merge yet**

Branch: `feat/ai-utility-gateway`
Draft integration PR: `#160`

Merge policy: **do not merge to `main` automatically.** Phase 8 records the decision; an actual merge still requires explicit approval after the remaining live-environment evidence is collected.

## Goal

Build one Super Admin-managed AI Utility Gateway that supplies low-cost system intelligence to Character Relay while keeping Character models focused on roleplay and keeping Runtime authority deterministic.

The Gateway may advise, classify, summarize, compress, rank, and interpret. It must not bypass Tool permissions, Key Groups, credentials, side-effect validation, scope isolation, cooldowns, idempotency, or other Runtime authority.

## Fixed architecture decisions

- Existing Character Relay Tool Registry remains the execution layer. The Gateway does not invent or directly execute privileged Tools.
- Existing shared local E5 runtime remains the high-frequency semantic engine.
- SQLite remains the source of truth for Topic, Memory, Wiki, provider configuration, and derived vectors. No external Vector DB is required by this roadmap.
- Media remains `SHA-256 -> cache/reference -> media.inspect -> Media Understanding`. No multimodal media embedding is introduced.
- Free providers must remain explicitly `FREE ONLY` members.
- Free-provider exhaustion must never silently become paid usage on that provider.
- Paid fallback is OpenRouter only and requires explicit Runtime configuration and budget limits.
- Provider API keys are Super Admin-managed and stored server-side in the encrypted Credential Vault.
- Quota state is response/event driven and cached where possible; providers are not polled before every inference call.
- Derived Wiki content never becomes more authoritative than its source Knowledge documents.
- New System Intelligence consumers must be independently disableable and must degrade to the existing deterministic/E5 path when Utility inference is unavailable.

## Provider candidates

Free-pool candidates:

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
| 2 | Implemented | Quota, health, router, OpenRouter paid fallback; real-provider allowance/reset remains a live validation gap |
| 3 | Implemented | RAG + Topic Intelligence + E5 ambiguity assistance |
| 4 | Implemented | Memory Intelligence on SQLite |
| 5 | Implemented | Media Understanding through Gateway, SHA-256 preserved |
| 6 | **Complete** | LLM Wiki / knowledge consolidation + conservative overview retrieval |
| 7 | **Complete** | Smart Participation tie-break + Tool continuation ambiguity assistance |
| 8 | **Complete — HOLD** | Automated/integration validation complete; real-provider economics/RAM evidence still required before merge |

## Phase 0 — Existing semantic foundation

Retained foundation:

- shared E5 runtime and query-vector reuse
- semantic RAG gate
- Conversation Topic Memory foundation
- semantic Tool continuation
- Super Admin semantic routing Judge prototype
- Key Groups bulk-apply UI refinement

The integration branch was created from the validated foundation while `main` remained untouched.

## Phase 1 — Utility Gateway foundation + Portal management

**Status: COMPLETE**

Implemented:

- provider-neutral capability contract
- stable free-provider member IDs, provider/model/base URL, enabled state, capabilities, priority, and enforced `FREE ONLY` membership
- Super Admin Gateway enable/disable and routing strategy configuration
- OpenRouter-only paid fallback configuration and daily/monthly budgets
- encrypted Vault credential scope `utility:{member_id}`
- Admin-only credential status/configure/delete endpoints
- no raw API-key echo to the browser
- removed provider members clean orphaned Vault credentials
- pre-Gateway config migrates with disabled/safe defaults

Phase 1 validation:

- CI `#1071`: **SUCCESS**
- Railway Smoke `#1037`: **SUCCESS**

## Phase 2 — Quota, health, routing, and OpenRouter paid fallback

**Status: IMPLEMENTED · real-provider allowance/reset behavior not production-validated**

Implemented:

- normalized states: `healthy / degraded / unavailable / cooling_down / exhausted`
- persisted provider telemetry and usage records
- remaining quota/reset observations when exposed by the provider
- error-rate, latency, cooldown, and priority routing inputs
- capability-scoped FREE ONLY provider selection
- event-driven state updates from actual request outcomes
- free-pool exhaustion never silently becomes paid usage
- OpenRouter-only paid fallback with explicit enablement and daily/monthly budgets
- provider/model/tier/routing reason/attempts/latency/token/cost observations in Runtime results

Offline regression coverage proves quota exhaustion/cooldown routing, malformed output fallback, paid-fallback enablement, and budget rejection. CI intentionally does not consume production free-provider quotas, so real-account allowance/reset behavior remains an unresolved Phase 8 live-evidence item.

## Phase 3 — Semantic + Topic Intelligence

**Status: IMPLEMENTED**

RAG:

- high-confidence E5 decisions remain deterministic
- ambiguous routing can use `semantic_judge`
- current-message evidence is prioritized
- contextual fallback requires Utility/Judge approval
- Judge failure keeps contextual RAG OFF rather than leaking older Knowledge into unrelated turns

Topic Memory:

- E5 handles obvious continuation/switch cases
- Utility assists gray-zone continue/switch/clarify/close interpretation
- Runtime remains authoritative for scope, persistence, lifecycle, and Tool permissions

## Phase 4 — Memory Intelligence on SQLite

**Status: IMPLEMENTED**

SQLite remains the source of truth. Durable memory supports owner/character/scope, memory type/content, confidence/importance, source references, timestamps, supersede/merge relationships, and E5 linkage.

Gateway advice can cover extract/ignore, reinforce, duplicate detection, merge, conflict, supersede/update, consolidation, and importance. Runtime performs writes; Utility failure cannot corrupt or block ordinary memory retrieval.

No external Vector DB dependency is introduced.

## Phase 5 — Media Understanding through Utility Gateway

**Status: IMPLEMENTED**

Preserved flow:

`media source -> SHA-256/cache/reference -> media.inspect -> Utility Gateway media_understanding -> cached perceived result`

Properties retained:

- no media embedding/vector pipeline
- successful SHA-256 cache hits avoid repeat model calls under existing privacy/scope rules
- provider selection respects modality capability
- video retains direct/extraction/keyframe behavior
- failed/declined inspection preserves the correct unseen/unperceived state
- paid Media fallback remains OpenRouter-only

## Phase 6 — LLM Wiki / Knowledge consolidation

**Status: COMPLETE**

Wiki is a derived layer, not a replacement for raw Knowledge.

Implemented:

- SQLite Wiki page identity, title/key, body, keywords, confidence, stale state, timestamps
- source manifest with source IDs/titles/type/content SHA-256
- stable source snapshot SHA-256
- Knowledge source changes mark affected Wiki pages stale
- current-page reads independently verify source hash
- lazy rebuild on the next eligible overview query
- same source hash reuses the current page without another Utility call
- Base/account lifecycle removes or migrates derived rows without leaving owner orphans
- Utility failure returns raw RAG unchanged
- exact/quote/citation/source/evidence/detail queries keep raw RAG authoritative
- overview/summary/explanation queries may use a compact derived page when one unambiguous Knowledge Base is identified
- provenance is embedded in the synthetic Wiki context

Language coverage for overview-vs-evidence routing includes English, Simplified Chinese, Traditional Chinese, mixed English/Chinese, and Malay markers. Evidence-sensitive Malay terms such as `sumber`, `bukti`, `petikan`, and `tepat` keep raw RAG authoritative.

Phase 6 validation:

- CI `#1098`: **SUCCESS**
- Railway Smoke `#1064`: **SUCCESS**

## Phase 7 — Additional System Intelligence consumers

**Status: COMPLETE**

Phase 7 deliberately adds only consumers that can run in gray zones rather than placing another network inference on every Character turn.

### Dedicated capabilities

Added independently assignable capabilities:

- `participation_tiebreak`
- `tool_continuation`

The Super Admin Utility Gateway panel exposes both capabilities. A consumer with no enabled member explicitly assigned to its capability is treated as disabled, even if global OpenRouter paid fallback is enabled.

### Smart Participation tie-break

The existing deterministic profile checks and E5 relevance remain authoritative.

Utility is eligible only when:

- at least two semantic profiles are ready
- the best E5 relevance is already strong (`>= 0.75`)
- the top candidates are in a narrow E5 gray zone (gap `<= 0.04`)
- the capability is explicitly enabled

Safety invariant:

- Utility **never increases any candidate's E5 relevance**
- the selected candidate keeps its original score
- non-selected tied candidates may only be demoted
- therefore Utility cannot make an originally ineligible Character cross a participation threshold; it can only reduce multi-Character semantic contention

Unknown deployment choices, low confidence, unavailable providers, or malformed results preserve the original E5 scores.

### Tool continuation ambiguity assistance

Existing high-confidence semantic continuation remains first.

Utility is considered only when:

- the current turn remains on the same topic
- cancellation is not detected
- continuation/retry/clarification evidence is in a bounded gray zone below the deterministic threshold
- exactly one pending action matches the already-scoped actor/Character/deployment state
- that Tool is currently assigned by Runtime
- `tool_continuation` is explicitly enabled

Utility may decide only whether the message refers to that one pending action. It cannot assign, authorize, or execute the Tool. Multiple pending actions, unassigned Tools, cancellation, mismatched returned Tool IDs, low confidence, or Gateway failure all resolve to no Utility continuation.

### Deliberately not activated

`context_compiler` and `structured_summary` contracts remain available but are not placed in the ordinary Character hot path in Phase 7. A guaranteed extra network call on common turns was not justified by measured benefit, so the existing prompt-budget/context logic remains authoritative.

### Phase 7 focused safety tests

Coverage proves:

- tie-break only demotes non-selected candidates
- no E5 candidate is ever boosted
- clear E5 winners skip Utility
- unknown/low-confidence choices are rejected
- one assigned gray-zone pending Tool can be interpreted
- multiple pending actions are never guessed
- unassigned Tool/cancel/wrong Tool results are rejected
- Gateway unavailable preserves existing behavior
- both consumers require explicit capability assignment

## Phase 8 — End-to-end validation and merge decision

**Status: COMPLETE — DECISION: HOLD / DO NOT MERGE YET**

### Final validated code head

Code head: `0413486628a26a5a1fa427007d37b0ba211031aa`

CI `#1112`: **SUCCESS**

- Python 3.12: Ruff **SUCCESS**, strict Mypy **SUCCESS**, full Pytest **SUCCESS**
- Python 3.13: Ruff **SUCCESS**, strict Mypy **SUCCESS**, full Pytest **SUCCESS**
- Web: typecheck/tests/build **SUCCESS**
- Discord connector: typecheck/tests/build/image **SUCCESS**
- Docker production checks **SUCCESS**
  - production image builds
  - production without persistent storage is rejected
  - persistent-volume startup succeeds
  - healthcheck succeeds
  - storage identity survives container replacement
  - container smoke test succeeds

Railway Smoke `#1078`: **SUCCESS**

### Phase 8 regression matrix covered by automated tests

Validated in the repository/CI suite:

- English / Simplified Chinese / Traditional Chinese / mixed English-Chinese / Malay Wiki overview-vs-evidence routing
- RAG contextual fallback fail-closed behavior
- Topic continuation/switch/close paths covered by the existing semantic/topic suite
- Memory duplicate/update/supersede and scope persistence covered by the Memory Intelligence suite
- Media cache/epistemic/provider fallback behavior covered by existing media tests
- free-provider exhaustion/cooldown routing with deterministic offline providers
- paid fallback enablement and budget enforcement
- malformed structured output falls through to the next eligible free provider
- restart/storage persistence through Docker replacement test
- credential Vault isolation and no-secret-echo behavior
- owner/Character/deployment/Knowledge scope isolation through existing integration tests
- Wiki source staleness, rebuild, compact-context reduction, and provenance
- Phase 7 authority boundaries and independent capability disablement

### Branch integration state

Final code comparison before this roadmap update:

- branch is `ahead 72`
- branch is `behind 0`
- merge base remains current `main` base `38c579c4f151742d27d2d8e667bd47f66ab2c5a3`
- there is no hidden rebase divergence at this checkpoint

The integration branch is a substantial Runtime feature set, not a small isolated patch, so passing CI alone is not sufficient justification for an automatic merge.

### Evidence still missing

The following roadmap items cannot honestly be marked production-validated from CI/smoke evidence alone:

1. **Real free-provider allowance/reset matrix** — CI uses deterministic/offline provider behavior and does not consume live Groq/Cerebras/OpenRouter/etc. free quotas.
2. **Real free-tier savings / latency economics** — no controlled production measurement yet proves the expected cost savings and acceptable latency under representative Character Relay traffic.
3. **Railway baseline vs peak RAM** — Railway HTTP smoke proves deployability/readiness, not baseline/peak memory usage under Utility load.
4. **Public Demo readiness** — Public Demo Status `#822` still reports `ready=false`: 5 demo Character Cards, 6 Scenarios, 1 Test Pack, but only 3 credential-ready Characters. This is an external demo credential/configuration blocker, not a Gateway code regression.

### Final Phase 8 answers

- Gateway architecture is safer and more provider-neutral than the old fixed-model Judge path: **supported by code/tests**.
- Free-tier savings are meaningful in real operation: **not yet measured**.
- Portal operation and credential isolation are safe at the tested contract level: **yes**.
- Topic/RAG false-positive behavior is better under the tested regression cases: **yes**, but no production A/B metric is claimed.
- Memory is bounded and survives Utility failure: **yes in tests**.
- Wiki reduces repeated overview context while preserving raw provenance: **yes in regression fixtures**.
- Media preserves the existing SHA-256 epistemic/cache behavior: **yes in tests**.
- Railway deployability is acceptable: **yes by smoke**.
- Railway RAM/peak-load behavior is acceptable: **not yet measured**.
- Real-provider quota/reset behavior is validated: **not yet**.

### Merge decision

**Outcome 3: keep the integration branch experimental and do not merge `main` yet.**

Reason: the implementation and automated gates are green, but the roadmap explicitly requires live-provider economics/quota evidence and Railway memory observations before a production merge decision. Those requirements are not relaxed merely because CI passes.

`main` remains unchanged. PR `#160` should remain Draft until the missing live evidence is collected and an explicit merge decision is requested.

## Phase execution rule

For any follow-up validation work:

1. preserve deterministic Runtime authority
2. do not grant Utility permission/credential/side-effect authority
3. run focused tests plus full CI/Railway Smoke after code changes
4. record real-provider/Railway measurements separately from offline regression evidence
5. do not merge `main` without explicit approval
