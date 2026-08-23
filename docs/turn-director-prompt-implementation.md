# Turn Director and Focused Roleplay Prompt — Implementation Plan

Status: **complete for the implemented Turn Director and social-posture scope — merged to `main`**
Integration: historical phase commits were squash-merged into `main`.
Current runtime authority: Intelligence Core v3

This document records the implemented scope and the remaining intentional non-goals. Current source, schemas, and tests remain authoritative.

## Current execution record

### Phase 0–1 delivered

- Add a structural-only Roleplay prompt manifest to the private Provider Trace request event. The manifest contains only fixed section character counts, bounded counts, and booleans; it contains no prompt text, Discord IDs, credentials, user text, or expression descriptions.
- Preserve the Smart Output/CR_OUTPUT schema while removing duplicate `LIVE CONTEXT` from the final Roleplay prompt, retaining one canonical recent transcript, and replacing the repeated trigger body with a marker.
- Prefer compact expression `semantic_intent`/`semantic_emotion` labels in both candidate guidance and prior-message transcript rendering. Keep a description fallback only where compact semantics are absent.
- Compact an invalid Smart Output repair request instead of resending the full Roleplay prompt as a second user message.

### Evidence and invariants

Implemented against `src/echo_masque/connector_runtime.py`, `src/echo_masque/smart_output.py`, `src/echo_masque/providers/trace.py`, and their focused tests. The branch retains V3-only authority, all existing Smart Output parser/alias/action validation, explicit Discord targeting, interaction-session safety constraints, and no raw prompt logging.

### Phase 0–1 validation before commit

- focused Ruff: passed;
- strict mypy for touched source: passed;
- focused prompt/context/expression/provider-trace pytest: `23 passed` (two pre-existing dependency/cache warnings);
- `git diff --check`: passed;
- Connector `typecheck`, tests, and production build: passed.

### Phase 0–1 commit

Committed as `4bcbd58 feat: focus roleplay prompt composition` on
`codex/turn-director-phase-0-1`.

### Phase 2 delivered

- `prepare_character_turn` takes selected message membership only from the authoritative
  V3 `ContextBundleV3.segment`; Connector input cannot nominate a focused Segment.
- The Roleplay transcript preserves source order but retains only selected Segment
  messages. It safely falls back to the rolling transcript when the selected IDs cannot
  be rendered or when an explicit mention/reply trigger sits outside the selected set.
- An unaddressed Smart-admission trigger outside the selected Segment is intentionally
  omitted. The prompt identifies the selected conversation and adds a boundary against
  concurrent discussions rather than leaking that trigger.
- The prompt manifest records the structural focus decision only; it still contains no
  message text or Discord IDs.

This is transcript isolation, not a claim of complete semantic isolation: existing V3
knowledge, correction, and social retrieval still use their current query/target paths.
Those ownership changes remain for later Director/continuity phases.

### Phase 2 validation before commit

- focused Ruff: passed;
- strict mypy for touched source: passed;
- composer, V3 context propagation, Discord targeting/expression, and Provider Trace
  redaction pytest: `19 passed`;
- `git diff --check`: passed.

### Phase 2 commit

Committed as `5756350 feat: scope roleplay context to v3 segments` on
`codex/turn-director-phase-2-segments`.

### Phase 3 delivered

- Add an opt-in, separately configured `turn_director` Utility capability. It is not an
  implicit alias for `semantic_judge`; without a configured free-pool Director member,
  the Runtime preserves the Phase 2 path.
- A strict, bounded proposal can select only already-selected message IDs, the Runtime's
  deterministic interaction posture, and at most two internal read requests from
  `memory.search`, `conversation.search`, and `wiki.lookup`.
- Director evaluation occurs only after V3 Context/Segment resolution, only when V3 marks
  the turn `external_lookup_needed`, and only when the Runtime can execute its internal
  read allowlist. It cannot affect admission, Segment membership, reply target, visible
  action, credentials, writes, or side-effect tools.
- The graph and sequential paths run the same async Director stage before Roleplay. Only
  completed, bounded read results appear in a distinct Roleplay brief. Rejection or
  Utility unavailability keeps the original prompt intact.
- Utility provider work carries the existing private trace scope into its worker thread,
  so a graph-run Director call remains associated with the `turn_director` Runtime node
  without adding proposal text, queries, or read results to traces.

### Phase 3 validation before commit

- focused Ruff: passed;
- strict mypy for touched source: passed;
- Utility capability/structured-output, Director contract scope, Provider Trace, V3
  context, and Character Turn graph pytest: `18 passed` across bounded batches;
- `git diff --check`: passed.

### Phase 3 commit

Committed as `4a1fe99 feat: add v3 turn director utility` on
`codex/turn-director-phase-3-utility`.

### Phase 4 delivered

- Ordinary internal context reads are no longer advertised to Roleplay or force-invoked in
  its tool loop. The only path for those reads is the bounded, Runtime-validated Turn
  Director stage introduced in Phase 3.
- Explicitly assigned deployment tools remain available to Roleplay. Runtime-owned media
  inspection remains separately forced only under its existing media epistemic gates.

### Phase 4 commit

Committed as `36fbcdf refactor: keep internal reads out of roleplay tools` on
`codex/turn-director-phase-4-tool-ownership`.

### Phase 5 delivered

- Social Relationship State now reaches Roleplay as a compact qualitative posture rather
  than raw familiarity, affinity, trust, and comfort scores. Impression remains explicitly
  subjective and evidence-backed.
- Existing direct-reply social projection remains unchanged. No new automatic factual-memory
  writer was added: this repository has no canonical durable Memory candidate owner, and it
  would be unsafe to repurpose authored character memory, Relationship/Impression, or Wiki.
  A future memory-candidate workflow must persist proposed/accepted/rejected state with
  Segment/message provenance and apply output-dependent social effects only after delivery
  acknowledgement.

### Phase 5 commit

Committed as `22dee02 feat: render qualitative social posture` on
`codex/turn-director-phase-5-social-memory`.

### Phase 6 delivered

- Documentation now provides a direct evaluation/calibration route from both general and
  developer indexes, and corrects stale wording that described the Turn Director plan as
  wholly unimplemented.
- The repository now uses a maintained `docs/agent-map.md` and handoff workflow instead of
  generated OpenWiki pages. Agents update only affected map rows as part of their coherent
  phase and still verify every claim against source/tests/contracts.

## 1. Outcome

Make Discord turns feel more natural while reducing high-cost Roleplay-model input:

- Roleplay concentrates on character voice, wording, pacing, and a visible Discord action.
- Runtime owns identity, scope, permissions, rate limits, tool execution, persistence, and Discord delivery validation.
- A bounded Utility/Intelligence Pool model may act as a **Turn Director** for genuinely ambiguous or tool-dependent turns.
- A Burst may contain several simultaneous conversations. A Character sees its selected Segment, not an undifferentiated channel transcript.
- Memory and Social Context are retrieved and written per relevant Segment/target, without turning subjective impressions into factual canon.

The target is not “use an LLM before every response.” The target is a conditional, observable system that spends Utility and Roleplay tokens only where they add value.

## 2. Evidence map and current baseline

| Area | Current implementation evidence | Important current behavior |
| --- | --- | --- |
| Discord Burst | `connectors/discord/src/turnIngress.ts`, `connectors/discord/src/contextBuffer.ts`, `connectors/discord/src/index.ts` | A Burst is a bounded temporal collection; its messages are preserved individually and enter rolling context. |
| Conversation Structure | `src/echo_masque/conversation_structure_resolver.py`, `tests/test_conversation_structure_*.py` | One Burst may produce several Segments. The Utility `semantic_judge` is currently used only when deterministic segmentation is ambiguous. |
| Participation | `src/echo_masque/participation_planner_v3.py`, `src/echo_masque/api/routes/smart_participation_vnext.py` | V3 is the sole participation authority; current final admission is deterministic/embedding-based after candidate evidence. |
| Character context and prompt | `src/echo_masque/character_turn_context_v3.py`, `src/echo_masque/context_resolver_v3.py`, `src/echo_masque/connector_runtime.py` | V3 context sections are injected into the Roleplay request, but the current prompt can duplicate live chat and the trigger. |
| Smart Output and expressions | `src/echo_masque/smart_output.py`, `src/echo_masque/api/expression_schemas.py`, `src/echo_masque/expression_assistant.py` | Up to ten expressions can be supplied; prompt guidance currently prefers long `semantic_description` over the existing short `semantic_intent`. |
| Utility Pool | `src/echo_masque/utility_gateway_router.py`, `src/echo_masque/utility_gateway_contracts.py`, `src/echo_masque/admin_runtime.py` | A configured free-token member with `semantic_judge` capability may be used. Unavailability must degrade safely. |
| Social Intelligence | `src/echo_masque/social_intelligence_v3.py`, `src/echo_masque/character_relationships.py`, `src/echo_masque/social_event_runtime.py`, `tests/test_social_event_runtime_v3.py` | Relationship State and subjective Impression can be injected into a current turn. Automatic ingress projection is deliberately limited to a confirmed human reply to a Runtime-known Character message. |

The historical V4 documents explain why Burst and final-ambiguity Utility work were considered, but must not be restored as V4 compatibility code. The governing architecture contract is `docs/intelligence-core-v3-architecture.md`.

## 3. Non-negotiable invariants

1. Intelligence Core v3 remains the only participation and context authority. Do not revive Topic authority, V4 schema bridges, Connector-local semantic fallbacks, or shadow authority.
2. Runtime, not either LLM, owns deployment identity, Discord/server scope, permissions, cooldowns, rate limits, credentials, tool execution, persistence, and side effects.
3. A Utility decision is advisory until it has passed schema, reference, scope, and policy validation.
4. Free-token Utility availability is volatile. Every optional Utility path needs a deterministic fallback or a safe no-op; required Runtime checks never depend on it.
5. A selected Roleplay turn cannot use voluntary `ignore` to overturn authoritative admission. Provider/schema failure and non-selection remain separate outcomes.
6. Raw messages, tool results, media, and external results remain provenance evidence. Wiki and Impression never outrank source evidence.
7. Relationship/Impression are directional and subjective social state, not factual Memory or a way to infer private history.
8. Do not expose credentials, raw private debug captures, hidden planner-only media knowledge, or internal scores to a Character or ordinary Discord event logs.

## 4. Target ownership model

```text
Discord event / Burst
        |
        v
Runtime deterministic preflight
  scope, identity, explicit reply/mention, permissions, cooldown, rate limits
        |
        v
Conversation Structure v3
  Segment and Thread evidence; Utility only for structural ambiguity
        |
        v
Participation Planner v3
  eligible candidates and selected Segment(s)
        |
        +-- clear, no-tool turn --> focused context package
        |
        +-- ambiguous or tool-dependent turn --> Turn Director Utility proposal
                                                   |
                                                   v
                                            Runtime validation/execution
                                                   |
                                                   v
Focused Roleplay package
  character contract, selected Segment, relevant evidence, social posture,
  verified tool results, compact Discord output contract
        |
        v
Roleplay LLM
  one natural visible action and character wording
        |
        v
Runtime output validation and Discord delivery
        |
        v
Post-turn, non-blocking consolidation
  Episodes, Memory candidates, Social Event proposals, derived Wiki work
```

### Responsibilities

| Owner | Decides | Must not decide |
| --- | --- | --- |
| Runtime | legal scope, identity, action/tool validity, execution, persistence, delivery | persona wording or a subjective social interpretation without evidence |
| Structure resolver | which supplied messages form Segment(s) and Thread membership | which Character is allowed to bypass Runtime gates |
| Participation Planner | eligible speaker plan and selected Segment evidence | external side effects or Character phrasing |
| Turn Director Utility | bounded response brief, whether supplied internal tools may help, and a proposal for an ambiguous choice | inventing tool IDs, IDs/references, credentials, authority, or unvalidated writes |
| Roleplay LLM | wording, conversational rhythm, and a valid visible action within its turn contract | admission, broad retrieval planning, tool execution, persistence, or policy/security decisions |

## 5. Conditional Turn Director

The Turn Director is a new V3-native Utility capability, not a restored V4 planner. It should be considered only after deterministic gates, Conversation Structure, and candidate narrowing.

### Invoke it when

- several eligible Characters or Segments remain plausibly suitable after deterministic/embedding evidence;
- the selected Segment is ambiguous enough that reply target or response posture cannot be selected safely;
- the current turn has a verified need for internal evidence/tool work (for example, a factual question, relevant media, a URL, or a known knowledge gap);
- a post-turn candidate needs a bounded social-event interpretation with a resolved target and source evidence.

### Do not invoke it when

- a simple social continuation has one clear selected Segment and needs no evidence;
- an explicit reply/mention and deterministic context already make the intended target clear;
- the turn is blocked by scope, policy, cooldown, rate limit, or media safety gates;
- no visible response should be admitted;
- a Runtime-required operation already has a deterministic implementation.

### Proposal contents

The eventual typed contract must be defined alongside implementation and validated strictly. Conceptually it may contain only supplied references and bounded enums for:

- selected Segment and reply target;
- admission recommendation only within Runtime-supplied candidate IDs;
- a concise response focus and social posture;
- a list of Runtime-supplied, internal read-only tool requests with bounded arguments;
- a list of evidence references and explicit non-claims;
- optional post-turn social-event or Memory proposals, each tied to source evidence.

It must not contain user-visible prose, raw provider reasoning, arbitrary tool names, credentials, free-form database writes, or externally side-effecting commands.

### Fallback

When the Utility Pool is unavailable, invalid, timed out, or rejected by Runtime:

1. retain the existing deterministic V3 speaker/Segment plan when it is sufficient;
2. perform Runtime-required work normally;
3. skip optional internal retrieval and optional post-turn proposals;
4. give Roleplay a truthful compact brief, never a fabricated tool result.

## 6. Focused Roleplay package

Roleplay must retain a clear output contract. Prompt reduction means removing duplicated or irrelevant information, not asking the model to guess an output format.

```text
CHARACTER CONTRACT
  stable persona, safety/identity boundary

TURN CONTRACT
  one valid visible Discord action; supplied aliases/references only

DIRECTOR BRIEF (only when present)
  selected Segment, reply target, response posture, focus, non-claims

FOCUSED CONVERSATION
  original messages from the selected Segment, in order

RELEVANT CONTINUITY (optional)
  bounded Thread state, Episode, Belief, Knowledge, or Social posture

VERIFIED TOOL RESULTS (optional)
  only Runtime-executed results needed to answer

EXPRESSIONS
  compact aliases and permitted actions; detailed meaning only when necessary
```

Rules for composition:

- Preserve one canonical copy of the relevant chat. Do not put the same raw messages in both `LIVE CONTEXT` and `Recent conversation`.
- If the trigger is already the final message in focused chat, mark it rather than repeating its full text.
- Other simultaneous Segments are represented only as a short boundary notice when needed: “Other discussions are active; do not answer or summarize them.”
- Keep the existing exact Smart Output/CR_OUTPUT shape and Runtime validation. Reduce repeated prose/examples only after snapshot and parse tests prove equivalence.
- Let Roleplay choose wording, sentence count, and permitted visible action. The Director may provide posture and focus but must not script a line or force an emoji.

### Expression compaction

Default expression guidance should use the existing short semantic fields:

```text
e1 — playful_pointing; actions: inline, react
e4 — skeptical_confusion; actions: inline, react
```

Use `semantic_intent` (and, where useful, `semantic_emotion`) before `semantic_description`. Expand full description only for a small number of ambiguous/highly relevant candidates. In live conversation context, omit retrieval source and confidence from the Roleplay prompt; preserve them in diagnostics instead.

## 7. Parallel conversations and memory

### Segment-first context

A Burst is a time window, not a single topic. The selected Character should receive:

1. raw messages in its selected Segment;
2. the associated Thread working state only when it is relevant;
3. a small set of evidence-backed Memory cards that match that Segment and target;
4. at most a boundary notice about other active Segments.

One Character should normally receive one primary Segment per Burst. Multiple Characters may be assigned to different Segments only within existing Runtime output/rate limits and with deliberate scheduling; zero visible responses remains valid for an unaddressed Burst.

### Memory retrieval and writes

| State | Read on hot path | Write policy |
| --- | --- | --- |
| Segment/Thread working state | selected Segment only | update through Conversation Structure/Runtime |
| Episode | only a relevant continuation | form after a bounded event/Segment, not every chat line |
| Belief/Knowledge | only when needed for the response | evidence-backed, revisable, provenance-preserving |
| Social Relationship/Impression | only for the addressed/resolved current target | write only a resolved, evidence-backed social event or revisable impression |
| Wiki | derived evidence only | asynchronous projection; never direct Roleplay authority |

Long-term consolidation should stay off the critical Discord reply path unless it is needed for the current response. The Turn Director may propose a write; Runtime validates and records it later.

## 8. Social Intelligence and conversational attitude

Relationship State and Impression should affect natural distance, warmth, directness, and willingness to continue a conversation, but never create fictitious shared history or override hard participation rules.

- Maintain directional bot→user and bot→bot state; authored Character-to-Character priors remain distinct from lived deployment state.
- Retrieve social state only for the resolved interaction target of the selected Segment.
- Convert internal numeric signals into a short natural posture for Roleplay. Keep raw dimensions, confidence, and source evidence in the Director/diagnostic layer.
- Continue automatic direct-interaction evidence only where current Runtime identity/reply evidence is confirmed.
- Add richer social events (support, praise, teasing, conflict, apology, and similar) as post-turn Utility proposals only after target resolution and source-message validation. Ambiguous events remain unresolved and do not change relationship state.
- Treat bot→bot interaction exactly as scoped deployment-to-deployment evidence; never infer a relationship merely because two bots appeared in the same Burst.

## 9. Delivery phases

Each implementation phase belongs on its own active branch and must have one coherent implementation commit after its listed gate passes. `docs/active-development-plan.md` must be recreated/updated only for the branch that actually implements a phase; the historical V3 cutover ledger must not be repurposed.

### Phase 0 — Baseline observability and replay fixtures

Add privacy-safe prompt manifests to the private Provider Trace path: section character estimates, duplicate suppression decisions, and expression statistics. Do not put raw private prompt contents into ordinary logs, Discord operational events, or ingress capture.

Create fixtures for: simple continuation, explicit reply, factual/tool turn, multi-Segment Burst, concurrent bot/user conversation, expression-heavy turn, Utility unavailable, and invalid Utility output.

Gate: focused Python/Connector tests, redaction review, and debug retention/scope tests.

Status: **complete — committed in `4bcbd58`.**

### Phase 1 — Focused prompt composition and expression compaction

Refactor prompt construction behind a tested composer. Preserve current output schema and delivery behavior while removing duplicate transcript/trigger text, capping context by relevance, and using compact expression labels by default.

Gate: prompt snapshots, Smart Output parser/validator tests, context budget tests, Connector typecheck/tests/build, and measured before/after manifest comparison on fixtures.

Status: **complete — committed in `4bcbd58`.**

### Phase 2 — Segment-first Character context

Pass selected Segment membership into the actual Character-turn composition path. Give Roleplay selected-Segment raw messages plus scoped continuity; prevent unrelated Burst Segments from appearing as a second transcript. Keep explicit Discord reply semantics authoritative.

Gate: Conversation Structure and Character-turn integration tests covering interleaved conversations, reply chains, multi-Character selection, and no-cross-segment context leakage.

Status: **complete — committed in `5756350`.**

### Phase 3 — Conditional Turn Director for planning and internal reads

Introduce the typed, schema-validated V3-native Turn Director proposal and its invocation policy. Start with bounded internal read-only tools and response briefs. Runtime validates all refs and executes all tools; Roleplay receives only verified results.

Do not create a second participation authority: the Director is considered only after V3 candidate narrowing and may only recommend within supplied candidates. Utility failure must use the Phase 2 deterministic path.

Gate: Utility Gateway capability/health/fallback tests, structured-output rejection tests, tool-scope tests, end-to-end turn tests, latency/token manifests, and provider trace redaction review.

Status: **complete — committed in `4a1fe99`.**

### Phase 4 — Tool ownership cutover

Move ordinary internal retrieval/tool-choice from Roleplay to the conditional Director. Retain a narrowly scoped Character-driven internal exploration path only when a later persona-specific need cannot be predicted; it must remain bounded and observable. Keep external capability tools and all side effects Runtime-authorized with explicit user intent where required.

Gate: tool runtime/security tests, no-credential-to-prompt assertions, idempotency/side-effect tests, and regression tests for direct factual requests and unavailable tools.

Status: **complete — committed in `36fbcdf`.**

### Phase 5 — Social and memory consolidation

Add post-turn, evidence-backed proposals for social events and memory candidates. Keep direct-reply evidence automatic, make richer interpretation conditional, and ensure unresolved targets never mutate state. Render short social posture rather than raw numerical state in Roleplay packages.

Gate: Social Intelligence lifecycle/decay tests, provenance and supersession tests, bot→user and bot→bot scope tests, multi-Segment isolation tests, and prompt snapshot tests.

Status: **complete for the safe social-posture scope — committed in `22dee02`.**

### Phase 6 — Evaluation, tuning, and documentation refresh

Use captured, access-controlled diagnostic fixtures and Evaluation Lab scenarios to compare the old and new prompt composition. Review:

- Roleplay input token distribution and duplicate sections;
- Utility calls per admitted turn/Burst and fallback rate;
- end-to-end latency distribution;
- invalid or rejected output rate;
- tool-plan precision and safe no-op behavior;
- human review of naturalness, interruption, and cross-topic contamination.

Tune policy from evidence rather than fixed assumptions. Update canonical contracts,
operator/debug documentation, and the affected manual agent-map rows in the same phase.

Status: **complete for documentation navigation — included in the squash merge to `main`.**

## 10. Explicit non-goals

- Do not call a Utility model for every chat message merely because a free pool exists.
- Do not move Discord delivery, secret access, external side effects, or durable writes into an LLM.
- Do not use Relationship State as a universal speaker-admission override.
- Do not put full raw debug captures, Utility reasoning, scores, or credentials in Character prompts.
- Do not restore Topic authority or historical V4 compatibility layers.
- Do not make a Character sound pre-scripted by forcing Director-authored wording, emoji, or hidden emotional state.

## 11. Future handoff

The remaining intentional gap is the durable factual-memory candidate workflow. Do not implement it by repurposing authored Character Memory, Relationship/Impression, or Wiki. A future scoped branch must first establish a canonical owner for proposed/accepted/rejected candidate state, Segment/message provenance, and delivery-acknowledged social effects. It must then update the relevant `docs/agent-map.md` row and prove multi-Segment and scope isolation with focused tests.
