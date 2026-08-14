# Character Relay Runtime Roadmap

This document records the current runtime boundaries and the implemented Smart Participation V4 / Conversation Intelligence milestone for Discord Smart Participation, Context/Topic/Memory, Media Understanding, RAG/Wiki, Tool Calling, and System Intelligence.

Detailed V4 architecture and implementation history lives in `docs/conversation-intelligence-v4-roadmap.md`; release evidence lives in `docs/conversation-intelligence-v4-validation.md`.

## 1. Runtime boundaries

Character Relay keeps these concerns separate:

1. **Routing** — resolve explicit Discord addressing, Reply, Server/Channel/Thread scope, and active deployments.
2. **Smart Participation** — decide whether an unaddressed social turn should admit any Character and which Character(s) receive the turn.
3. **Conversation Intelligence** — maintain bounded topic, participant, event, media, memory, and later graph-derived context without granting execution authority.
4. **Character Context** — assemble recent conversation, Topic/Memory/RAG/Media context, Expression candidates, Tool schemas, and prompt budgets for an admitted Character.
5. **Smart Output** — let the admitted Character choose a natural social action.
6. **Tool/Media execution** — validate Tool availability, permissions, side effects, Media inspection, credentials, scope, idempotency, and bounded Tool loops.
7. **Delivery** — validate references/resources and execute the allowed Discord action.
8. **Evaluation** — observe selection/runtime behavior and keep external RAG/OOC evaluation separate from production Character authority.

A recurring design rule remains:

> LLM output is a proposal. Character Relay Runtime remains the authority that validates, scopes, and executes it.

## 2. Current Smart Participation V3

Smart Participation V3 is a semantic multi-Character turn selector.

Current production behavior includes:

- explicit Reply/Mention/address routing before Character Runtime;
- configurable Smart Participation Profiles;
- multilingual E5 Character semantic profiles;
- shared FastEmbed/ONNX E5 runtime and recent query-vector reuse;
- deterministic question/help/topic/keyword/trigger/initiative signals;
- avoid phrases, per-Character cooldown, channel cooldown, and rate limits;
- conservative lightweight follow-up for low-information social turns;
- bounded multi-Character admission and ordered execution;
- optional Primary/Secondary coordination;
- Utility Gateway tie-break for narrow high-confidence E5 ambiguity;
- Utility tie-break may demote competitors but cannot grant eligibility;
- Behavior Notebook visibility for selected and silent/no-selection turns.

See `docs/smart-participation-v3.md` for the current semantic participation model.

### 2.1 Current limitation

V3 still evaluates ordinary Discord traffic primarily message-by-message and Character-by-Character. Topic/Media/relationship context is richer after a Character has already been selected than it is during speaker selection.

This is the main motivation for V4.

## 3. Current Smart Output and Character Runtime

Smart Output remains the Character's bounded social action contract. The Character may choose to ignore, send a message, react, use a Sticker/Emoji reference, or use other explicitly supported structured actions.

Runtime validates the proposal before Discord delivery. Invalid references/resources/actions do not become partial side effects.

Character provider failures stay turn-scoped. A successful provider HTTP response is not treated as equivalent to accepted Smart Output or final Runtime delivery.

See `docs/smart-output-v1.md` and the Behavior Notebook runtime traces.

## 4. Current semantic/context foundation

The previous roadmap described sparse-only RAG and future Vector Memory. `main` has moved beyond that baseline.

Current foundations include:

- shared multilingual E5 runtime across Smart Participation, Knowledge routing/retrieval, Expressions, Conversation Media, Topic continuity, and Tool relevance;
- short-lived SHA-256-keyed query-vector reuse without retaining raw Discord text in the query cache;
- hybrid semantic Knowledge retrieval with a semantic route gate so unrelated social turns can skip RAG;
- Conversation Topic Memory with bounded topic capsules, semantic continuation/switch classification, participants, open loops, and pending actions;
- semantic Tool continuation for scoped pending side effects;
- Memory Intelligence stored in SQLite with Runtime-authoritative writes;
- derived LLM Wiki pages for overview/summary use while raw Knowledge remains authoritative for evidence/detail queries;
- prompt budgeting and bounded Character Turn context.

SQLite remains the production source of truth for these derived/runtime records. An external Vector DB is not currently required.

## 5. Current AI Utility Gateway

System Intelligence is provider-neutral and Super Admin-managed through the AI Utility Gateway.

The Gateway can advise/classify/summarize/rank in bounded gray zones while Runtime retains authority.

Current consumers include areas such as:

- semantic/RAG ambiguity assistance;
- Topic interpretation in gray zones;
- Memory Intelligence;
- Media Understanding provider routing;
- LLM Wiki consolidation;
- Smart Participation tie-break;
- Tool continuation ambiguity assistance.

High-confidence E5/deterministic decisions should not pay for another network inference. Utility failure must degrade to the existing deterministic/E5 path rather than make the Character runtime unavailable.

See `docs/ai-utility-gateway-roadmap.md` for the provider/budget/safety model.

## 6. Current Media Understanding

Media behavior separates content understanding from Character epistemic truth.

Current design includes:

- visible image attachments can be passively perceived;
- links/videos/other non-visible shared content are inspected through the normal Runtime-owned `media.inspect` Tool when the Character chooses to inspect them;
- the dedicated Media Attention LLM pre-pass has been removed;
- Media Understanding results can reuse SHA-256/cache identity;
- historical Conversation Media supports semantic recall with stricter automatic-recency and low-information safeguards;
- explicit/reply historical references can bypass ordinary automatic age limits;
- OCR/readable text is hydrated only when the follow-up actually asks for text/number/price/capacity-like details;
- one Character perceiving media does not imply that another Character perceived it.

See `docs/media-awareness-and-generation-roadmap.md` and `docs/media-epistemic-observability.md`.

## 7. Current Tool Calling

Tool Calling is already a Runtime capability rather than a future-only item.

The Character model can propose assigned Tools inside a bounded Tool loop. Runtime owns:

- Deployment Tool assignment;
- Key Groups/credentials;
- side-effect validation;
- operation/idempotency boundaries;
- current availability;
- Tool continuation state;
- execution and traces.

Conversation Topic Memory can preserve a safe blocked side-effect intent and later expose the Tool only when the same scoped actor/Character/deployment semantically continues the pending topic and the Tool is actually assigned.

See `docs/tool-calling-roadmap.md`.

## 8. Current milestone — Smart Participation V4 / Conversation Intelligence Graph

V4 is implemented in Draft PR #166 and release-validated for CI/Railway. The runtime remains feature-flagged and shadowable so Graph/Learned-State influence can be rolled out conservatively without weakening explicit or deterministic authority.

All implementation work is intentionally kept on one feature branch and one Draft PR so the architecture can be validated as one coherent pipeline rather than as disconnected detection features.

Target pipeline:

```text
Discord ingress
→ explicit audience fast path
→ adaptive Turn Collector
→ Conversation Burst
→ cheap deterministic eligibility gates
→ active Topic / conversation evidence
→ E5 + participation semantics
→ SQLite Conversation Graph evidence
→ candidate reranking
→ Utility Judge only for final ambiguity
→ Speaker Plan
→ Character Runtime
```

### 8.1 Adaptive Turn Collector

Rapid ordinary human messages should be collected into a bounded Conversation Burst instead of independently triggering full Smart Participation detection for every fragment.

The collector preserves each source message/author/reply/media reference. Explicit Character addressing and other Runtime-owned explicit routes remain immediate or force-flush pending ordinary bursts.

### 8.2 Pipeline reorder

Cheap/authoritative checks should happen before semantic/Utility work when possible. Explicit routing, hard blocks, low-information handling, cooldowns, and rate limits should prevent unnecessary E5/Utility calls.

### 8.3 Conversation-aware participation resolver

The current narrow semantic-score request evolves into one bounded server-side conversation-aware resolver that can see connection/guild/channel/thread scope and active conversation state.

The resolver should replace a normal network hop rather than add a second normal-turn inference request.

### 8.4 Conversation Intelligence Graph

The first Graph implementation stays on SQLite. No Neo4j, GNN, or external graph database is required.

Initial nodes:

- Topic
- Character
- Actor
- Event
- Media
- Conversation Burst

Initial relationships include participation, mention/reply, topic/event/media links, and Character-scoped media perception.

Graph starts in **shadow mode** and cannot affect admission until measured against the V3 baseline.

### 8.5 Graph-assisted reranking

The first live Graph rollout can only reorder/demote candidates that already passed deterministic eligibility. It cannot make an otherwise ineligible Character cross the participation threshold.

Only after measured evidence should relationship/topic/event/media context be considered for broader eligibility semantics.

### 8.6 Topic + Media integration

Topic Memory remains the lifecycle authority. Media Runtime remains the epistemic authority. The Graph links those existing truths rather than replacing them.

A cached Media Understanding may be reused for the same SHA content while `PERCEIVED / SKIPPED / INSPECTED` state remains per Character.

### 8.7 Durable social state

V4 also defines which selection/cooldown/burst state must survive restart or multi-replica operation instead of remaining Connector-process-local.

See `docs/conversation-intelligence-v4-roadmap.md` for phase-by-phase scope, invariants, success metrics, shadow rollout, and merge gates.

## 9. V4 delivery sequence — one PR

The V4 Draft PR completed the sequence as one coherent implementation:

1. Baseline measurement + compatibility flags.
2. Adaptive Turn Collector / Conversation Burst.
3. Smart Participation pipeline reorder.
4. Server-side conversation-aware participation resolver + semantic profile V2.
5. SQLite Conversation Intelligence Graph foundation in shadow mode.
6. Behavior Notebook V3-vs-Graph comparison evidence.
7. Graph-assisted reranking for already-eligible candidates.
8. Topic/Event/Media relationship integration.
9. Character-scoped media perception edges + SHA understanding reuse verification.
10. Durable social-state cleanup where correctness requires it.
11. Full regression/performance/economics/Railway validation.
12. Explicit merge decision.

Production rollout may keep Graph/Learned-State reranking in shadow or disabled mode until live outcome evidence justifies activation. Graph remains a removable derived layer and does not own authoritative conversation/media truth.

## 10. Evaluation priorities

Future selection quality should be evaluated on actual group-chat behavior rather than only semantic similarity fixtures.

Key measurements include:

- Smart resolver calls per human message;
- Utility calls per human message;
- p50/p95 selection latency;
- Character provider calls per human message;
- correct / should-speak / should-stay-silent feedback;
- wrong-speaker rate;
- duplicate/interruption rate;
- short continuation/pronoun handling;
- stale Media recall rate;
- Media Understanding cache reuse;
- Graph database growth/cleanup cost;
- Railway RAM/CPU under message bursts.

## 11. Later directions

After V4 stabilizes, potential later work includes:

- richer persistent relationship/memory semantics when real usage justifies them;
- a Vector DB only if corpus/latency/scale measurements justify moving beyond SQLite/vector BLOBs;
- selective LangChain components where they simplify stable contracts rather than becoming Runtime authority;
- stronger offline evaluation datasets built from Behavior Notebook and user feedback;
- external RAG/OOC evaluation improvements kept separate from Character production authority.

MCP is not required for the V4 architecture.