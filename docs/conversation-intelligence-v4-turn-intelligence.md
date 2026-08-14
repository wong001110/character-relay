# Conversation Intelligence V4 — Unified Turn Intelligence + Structured Output Hardening

Status: **PLANNED / part of Draft PR #166**

Branch: `agent/conversation-intelligence-v4`

This document extends `docs/conversation-intelligence-v4-roadmap.md`. It is part of the same Smart Participation V4 integration PR and must not be implemented as a separate PR.

## Goal

Reduce repeated low-cost LLM judgments inside one Discord conversation turn and make Utility structured outputs reliable enough that schema mistakes do not cause unnecessary provider fallthrough.

The target hot path is:

```text
Conversation Burst
→ explicit audience + hard deterministic gates
→ shared E5 / Topic / Graph evidence
→ identify unresolved gray-zone tasks
→ zero or one Turn Intelligence Utility call
→ per-field validation + independent fallback
→ Runtime authority
```

The unified Turn Intelligence call is not a general agent and does not replace Media Understanding, Wiki generation, durable Memory validation, Tool Runtime, Character Runtime, or Echo Masque evaluation.

---

## Current-state audit

### 1. Multiple Judge implementations coexist

Current `main` contains both:

- the AI Utility Gateway with capability-specific typed decisions; and
- the older `SemanticRoutingJudgeService` used by `KnowledgeRouteGate` for RAG routing.

The old RAG Judge owns its own primary → availability fallback → quality-escalation cascade while the Utility Gateway separately owns provider health/fallback routing. V4 should converge provider routing into the Utility Gateway and retire the old consumer-owned provider cascade after parity coverage exists.

### 2. RAG can be judged more than once for one Character turn

`ContextOrchestrator` may evaluate a current-message Knowledge route and then evaluate a contextual query built from recent human turns. If current retrieval yields no candidates, it may also attempt contextual fallback routing.

V4 should present current and contextual evidence together and make one knowledge-routing decision:

```text
knowledge_route = off | current | contextual
```

rather than independently judging current and contextual queries.

### 3. Utility contracts are currently one schema per model call

The Gateway exposes separate typed decisions for RAG, Topic, Memory, Participation, Tool continuation, summary, Wiki, and context compilation. This is a good authority boundary for independent non-hot-path jobs, but Topic + Participation + RAG + Tool continuation can all describe the same current conversation ambiguity.

V4 should unify only these turn-level interpretation tasks when more than one is ambiguous.

### 4. Not every implemented Utility consumer is currently wired into the Character hot path

Code existence must not be confused with production call count. The default app currently constructs a normal `ContextOrchestrator`, which creates the regular Topic Memory path. Utility Topic/Memory/RAG-guard modules exist but are not all injected into the default Character-turn path.

The V4 migration must explicitly document which consumer is active, shadow-only, compatibility-only, or retired.

---

# Unified Turn Intelligence contract

## Requested-task model

Do not send every possible task on every burst. Deterministic/E5/Graph stages first determine which decisions are already clear.

Example:

```text
topic       = ambiguous
speaker     = ambiguous
knowledge   = ambiguous
pending_tool = clear
```

The Utility request includes only unresolved tasks:

```json
{
  "requested_tasks": ["topic", "speaker", "knowledge"]
}
```

If `requested_tasks` is empty, no Utility call is allowed.

Normal conversational interpretation should therefore require at most one Utility inference per Conversation Burst, excluding genuinely separate later operations such as Media Understanding.

## Proposed decision shape

Use one versioned strict schema, conceptually:

```json
{
  "schema_version": "turn-intelligence-v1",
  "topic": {
    "decision": "continue",
    "confidence": 0.86,
    "reason_code": "same_open_topic"
  },
  "speaker": {
    "deployment_id": "deployment-a",
    "confidence": 0.82,
    "reason_code": "best_context_fit"
  },
  "knowledge": {
    "route": "off",
    "confidence": 0.91,
    "reason_code": "social_followup"
  },
  "pending_action": null
}
```

Exact production shape may use nullable submodels or an explicit `requested` flag, but it must have one unambiguous representation for an unrequested field.

Allowed turn-level tasks:

- `topic`: continue / switch / clarify / close;
- `speaker`: choose at most one already-supplied candidate or abstain;
- `knowledge`: off / current / contextual;
- `pending_action`: continue or reject exactly one already-scoped pending Tool action.

The Judge may never create a deployment ID, Tool ID, Knowledge Base, Topic ID, permission, or action that Runtime did not supply.

## Per-field authority and fallback

A single malformed or low-confidence sub-decision must not invalidate valid sibling decisions.

Example:

```text
Topic confidence      0.91 → accept
Speaker confidence    0.85 → accept
Knowledge confidence  0.43 → deterministic fallback
Tool confidence       0.88 → accept
```

Each field has:

- its own minimum confidence;
- allowed IDs/enums supplied by Runtime;
- independent validation;
- independent deterministic/E5 fallback;
- independent trace status.

The outer response is valid only if the envelope/schema version is valid, but one bad optional field should degrade that field rather than forcing another whole-provider call when the remaining fields are usable.

## Participation safety

The unified Judge inherits the current participation invariant:

> Utility may only resolve contention among already-eligible supplied candidates. It may not make an ineligible Character cross the participation threshold.

The selected Character keeps Runtime-authorized eligibility. Utility is advisory reranking/tie resolution only.

## Tool continuation safety

The unified Judge receives at most one already-scoped pending Tool action when Tool continuation is ambiguous. It may answer only whether the current burst continues that action.

Assignment, availability, credentials, idempotency, side-effect limits, and execution remain Tool Runtime authority.

## Knowledge safety

The unified Judge decides only between supplied route modes (`off/current/contextual`). It does not select arbitrary documents and cannot manufacture Knowledge context.

Exact/quote/citation-sensitive retrieval rules remain deterministic and raw Knowledge remains authoritative.

---

# Do not merge these tasks into Turn Intelligence

## Media Understanding

Media perception may require multimodal providers and is triggered only when Runtime/Character semantics allow inspection. Keep it as a separate on-demand capability.

Turn Intelligence may only reason over already-authorized media references or cached media facts that the relevant Character is allowed to know.

## Wiki generation

Wiki is a derived knowledge-maintenance job and is not a realtime speaker-routing decision. Keep lazy rebuild and source-hash reuse separate.

## Durable Memory mutation

Turn Intelligence may later emit a bounded hint such as `memory_candidate=true`, but it must not directly create/reinforce/merge/supersede durable Memory.

Memory mutation requires its own retrieval, duplicate/conflict checks, provenance, and write authority.

## Echo Masque / evaluation Judge

Character evaluation/OOC judging is a separate product domain and must never be folded into Discord Turn Intelligence.

---

# Structured Output Audit

## Finding A — live Utility calls are prompt-only JSON today

`ExistingProviderUtilityCaller` uses the normal OpenAI-compatible chat completion path. The current live request does not supply native `response_format`, JSON Schema, function/tool schema, or another provider-enforced structured-output mechanism.

Therefore the model is currently constrained mainly by system-prompt wording and later Pydantic validation.

This is insufficient for heterogeneous free models and already caused production-visible field-alias failures in Participation tie-break.

## Finding B — `max_output_tokens` is currently discarded

The Utility caller receives `max_output_tokens` but deletes it instead of forwarding it to the provider. The generic OpenAI-compatible provider also does not currently expose an output-token-limit parameter.

V4 must wire the requested bound through the provider interface and map it to the compatible provider request field. The exact request field may vary by provider/API compatibility layer, but the Utility contract must not silently ignore the configured output bound.

## Finding C — most Utility prompts underspecify the exact JSON contract

Participation tie-break now explicitly declares:

- exact field names;
- no prose/markdown;
- forbidden aliases;
- explicit abstention shape.

Other Utility helpers commonly say only `Return strict JSON` or list a few keys. This is weaker than the strict Pydantic models, many of which use `extra="forbid"`.

A provider can therefore return semantically correct data with an invented key, omitted default field, wrapper object, enum synonym, or explanation field and still trigger `schema_error`.

## Finding D — schema failure currently encourages provider fallthrough

The Gateway extracts a JSON object and validates it against the Pydantic schema. A validation failure is classified as protocol/schema failure and routing may try another eligible provider.

This is useful for genuine provider incompatibility, but a weak prompt contract can turn one logical decision into multiple successful HTTP calls whose only failure is field shape.

V4 must measure and bound this behavior.

## Finding E — stale Utility implementation/test references exist

At least one current test references `echo_masque.utility_gateway_runtime`, while current source layout exposes `utility_gateway_contracts`, `utility_gateway_live`, and `utility_gateway_router` instead. V4 should remove or migrate stale imports/tests so there is one canonical Utility implementation path.

---

# Structured Output Hardening Plan

## 1. Provider capability-aware structured mode

Add an explicit structured-output mode to the Utility provider path, resolved per provider/model capability:

```text
json_schema   → preferred when actually supported
json_object   → fallback when JSON mode is supported but schema enforcement is not
prompt_only   → compatibility fallback
```

Do not claim native JSON Schema merely because an endpoint is OpenAI-compatible. Provider/model capability must be configured or positively known.

## 2. Native JSON Schema first

For `json_schema` providers, derive a compact schema from the exact Pydantic decision model and send it through the provider request's structured-output field.

Requirements:

- strict schema name/version;
- `additionalProperties: false` where supported;
- exact enum values;
- exact nullable/unrequested representation;
- bounded strings/arrays;
- no arbitrary nested objects.

Runtime still validates the returned object with Pydantic. Provider-enforced structure reduces malformed output; it does not replace Runtime validation.

## 3. JSON-object mode second

If a provider supports JSON object mode but not schema enforcement:

- request JSON object mode;
- include the exact compact example/schema in the system prompt;
- explicitly forbid markdown, prose, wrapper keys, aliases, and omitted required keys.

## 4. Prompt-only compatibility mode

For providers with neither capability, every Utility contract must include the same exact shape discipline already proven useful by Participation tie-break:

- exact keys;
- exact enum strings;
- required vs nullable fields;
- exact abstention/unrequested shape;
- no aliases;
- no additional fields;
- no markdown/prose.

Generate this contract from the typed schema where practical instead of hand-maintaining divergent prose.

## 5. Enforce output-token bounds

Extend the provider interface used by Utility so `max_output_tokens` is forwarded instead of deleted.

Tests must assert the outbound provider payload contains the intended limit for supported endpoints.

Turn Intelligence should keep its schema deliberately small so normal responses fit in a low token ceiling.

## 6. No automatic repair call in the normal Utility hot path

Do not add a guaranteed second LLM `repair JSON` call. If one provider returns unusable structure:

- use valid per-field data when safely recoverable under the strict envelope;
- otherwise follow bounded Gateway provider fallback;
- if no valid result exists, use deterministic/E5 fallback.

A future repair attempt must be justified by measurements showing it is cheaper/better than deterministic fallback.

## 7. Separate schema incompatibility from provider health

Observability should distinguish:

- invalid JSON syntax;
- missing required key;
- unexpected/alias key;
- wrong enum;
- wrong type;
- output truncation;
- unsupported structured-output mode;
- provider HTTP/protocol failure.

A model repeatedly ignoring one capability schema may be a capability-specific incompatibility rather than a globally unhealthy provider.

Provider health/routing should not over-penalize unrelated capabilities solely because one schema contract is incompatible.

## 8. Version every hot-path schema

Turn Intelligence responses carry a schema version. Contract changes must be explicit and traceable.

Do not silently change expected keys while old models/provider caches/configuration still assume another shape.

---

# Observability

Record privacy-safe structured-output telemetry for each Utility inference:

- capability / Turn Intelligence task set;
- schema name + version;
- requested structured mode;
- provider/model;
- parse status;
- validation failure category;
- response character count and output token count, not raw private output by default;
- number of provider attempts;
- whether provider fallthrough occurred because of schema shape;
- per-field accepted/fallback status for Turn Intelligence;
- latency and cost/quota observations already tracked by Gateway.

Behavior Notebook should make it possible to distinguish:

```text
E5/Graph clear → Utility skipped
Utility called once → all requested fields valid
Utility partial → Topic accepted, Knowledge fallback
Utility schema failure → deterministic fallback
Utility provider fallback → second provider used
```

---

# Tests required before rollout

## Contract tests

Add exact-output-contract tests for:

- Turn Intelligence envelope;
- Topic subdecision;
- Speaker subdecision;
- Knowledge route subdecision;
- Pending Tool continuation subdecision.

Participation's current exact-key regression test is the model to follow.

## Provider request tests

Assert:

- `json_schema` is sent only when provider/model capability says it is supported;
- JSON object mode is used when appropriate;
- prompt-only mode receives a complete exact contract;
- `max_output_tokens` is actually represented in the outbound request;
- DeepSeek/Gemini/OpenAI-compatible endpoint differences do not silently drop the structured contract.

## Failure tests

Cover:

- invented alias (`selected_deployment_id` vs `deployment_id`);
- wrapper object around the expected payload;
- extra explanation field under `extra="forbid"`;
- markdown around JSON;
- wrong enum synonym;
- truncated JSON;
- one malformed optional Turn Intelligence field with valid siblings;
- low-confidence one-field fallback;
- provider schema incompatibility followed by bounded provider fallback;
- all providers unavailable → deterministic/E5 fallback;
- no ambiguity → zero Utility calls.

## Call-count tests

For one Conversation Burst, assert normal Turn Intelligence behavior performs:

- zero Utility calls when all decisions are clear;
- at most one logical Turn Intelligence inference when one or more turn-level tasks are ambiguous;
- provider attempts only as bounded Gateway fallback for failure, not one separate logical inference per topic/speaker/RAG/tool task.

RAG regression should prove current + contextual evidence produces one `off/current/contextual` judgment rather than two independent Judge calls.

---

# Migration sequence inside PR #166

1. Add structured-output observability before changing routing.
2. Add provider output-token forwarding and provider structured-mode capability metadata.
3. Harden existing individual Utility contracts and regression tests.
4. Introduce versioned `TurnIntelligenceDecision` in shadow mode.
5. Feed current + contextual Knowledge-route evidence into one decision.
6. Move final Participation ambiguity into Turn Intelligence.
7. Move eligible Topic/Tool continuation gray zones into the same requested-task call.
8. Compare output/call count/latency against existing individual consumers.
9. Retire old `SemanticRoutingJudgeService` provider cascade after parity is proven.
10. Remove stale/duplicate Utility helper paths and stale tests/imports.
11. Keep Media/Wiki/Memory writes/Evaluation as separate capabilities.
12. Only then allow Turn Intelligence results to affect V4 speaker/context behavior beyond shadow mode.

## Exit criteria

- normal turn-level ambiguity needs at most one logical Utility inference per Conversation Burst;
- no Utility call when deterministic/E5/Graph evidence is clear;
- current/contextual RAG is not judged twice;
- structured-output schema failure rate is measured and materially lower than prompt-only baseline;
- `max_output_tokens` is enforced at the provider request layer;
- native schema/JSON modes are capability-aware and never assumed universally;
- provider fallback is bounded and observable;
- per-field fallback prevents one weak subdecision from discarding unrelated valid decisions;
- Runtime authority boundaries remain unchanged;
- old Semantic Routing Judge and stale Utility implementation paths are removed only after migration/parity tests pass.
