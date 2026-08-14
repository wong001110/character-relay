# Smart Participation V4 — Conversation Intelligence Graph Roadmap

Status: **PLANNED / implementation branch opened**

Branch: `agent/conversation-intelligence-v4`

Delivery rule: **all work in this roadmap stays in one Draft PR until final validation and explicit merge approval.** Do not split Turn Collector, participation pipeline reorder, conversation-aware resolution, Graph shadow mode, Graph reranking, Topic/Media integration, or the final rollout into separate implementation PRs.

## Goal

Upgrade Smart Participation from per-message Character Card relevance into a conversation-aware speaker planner that understands short message bursts, active topic continuity, participants, events, media, and bounded relationship context without moving runtime authority into an LLM.

The target behavior is:

```text
Discord messages
→ explicit audience fast path
→ adaptive Turn Collector
→ Conversation Burst
→ cheap deterministic gates
→ Topic / conversation state
→ E5 + Graph evidence
→ candidate reranking
→ Utility Judge only for final ambiguity
→ Speaker Plan
→ Character Runtime
```

The Graph is an evidence and memory layer. It is **not** another independent detector and must not bypass explicit addressing, hard blocks, cooldowns, rate limits, Tool permissions, media epistemic truth, or Runtime delivery authority.

## Current production baseline

The roadmap starts from the current `main` behavior rather than the older V2 assumptions:

- Smart Participation V3 semantic Character Card profiles use the shared multilingual E5 runtime.
- query embeddings are reused across semantic consumers through the process-shared cache.
- deterministic Smart Participation still owns profile enablement, style, literal topics/keywords/triggers, avoid phrases, cooldowns, channel limits, lightweight follow-up, and multi-character admission.
- the Utility Gateway can break narrow E5 ties, but it may only demote competing candidates and cannot grant eligibility.
- Conversation Topic Memory persists bounded topic capsules with summary, keywords, participants, open loops, pending actions, status, and semantic continuation/switch classification.
- Tool continuation already uses Topic Memory and the Utility Gateway only in bounded gray zones.
- Media Understanding keeps SHA-256/cache reuse, passive visible-image perception, Tool-driven link/video inspection, character-scoped epistemic state, semantic historical recall, and lazy OCR hydration.
- Behavior Notebook can observe silent/no-selection Smart Participation turns and candidate score breakdowns.

## Problems to solve

### 1. Per-message evaluation during message bursts

The Discord Connector currently serializes messages per channel/thread, but each human message is still independently processed. Rapid sequences such as:

```text
我觉得
刚才那张图
其实蛮好笑的
```

can therefore produce multiple semantic scoring passes against incomplete fragments. This wastes E5/Judge work and can let a Character react before the human has finished the thought.

### 2. Expensive semantic work happens before some cheap routing decisions

For ordinary messages the Connector may request semantic Character relevance before name/group audience resolution and before low-information, cooldown, rate-limit, and other cheap Smart Participation gates are fully known.

### 3. Utility tie-break is based on E5 ambiguity rather than final participation ambiguity

The current Utility tie-break sees current text plus Character semantic profiles and E5 scores. Later deterministic scoring can still change candidate order because of topic/keyword/trigger/initiative/cooldown signals. The Utility should operate only after deterministic and contextual evidence has produced the actual final gray zone.

### 4. Topic intelligence is mainly post-selection

Topic Memory is currently most useful after a Character has already been admitted into Character Runtime. V4 should use bounded active-topic evidence during speaker selection while preserving one authoritative topic lifecycle implementation.

### 5. Character semantic participation profiles are too static

The current participation embedding is based on Character identity/persona fields. V4 should support a participation-focused semantic representation that can include configured participation topics and role hints without embedding hard avoid/boundary rules that must remain deterministic.

### 6. Context intelligence is fragmented

Smart Participation, Topic Memory, Media Recall, Tool continuation, and RAG each make related semantic/context decisions. V4 should let these systems share a bounded conversation state instead of adding more independent detectors.

### 7. Some speaker-state accounting is process-local

Connector-local admission/cooldown bookkeeping works for the current deployment shape but is reset on process restart and is unsuitable as a long-term multi-replica source of truth. V4 should define which state must become server-side/durable while preserving cheap local caches where safe.

## Architecture invariants

1. Explicit Discord addressing remains highest priority.
2. Hard deterministic blocks remain authoritative.
3. The Character model never decides whether it was eligible to receive a turn.
4. Utility LLM output remains advisory and bounded to supplied candidates.
5. Graph evidence cannot grant Tool permission or side-effect authority.
6. Media content truth and Character perception truth remain separate.
7. The same media understanding may be reused by SHA-256, but each Character's `PERCEIVED / SKIPPED / INSPECTED` state remains character-scoped.
8. SQLite remains the initial source of truth. No Neo4j, external graph database, GNN, or external Vector DB is required for V4.
9. Existing E5 runtime remains the high-frequency semantic engine.
10. Every new stage must be independently disableable and must degrade to the current V3 path.

---

# Phase 0 — Measurement baseline and compatibility contract

Before behavior changes, extend observability so the V3 path can be compared with V4 on the same traffic.

Record at minimum:

- message arrival timestamp and processing start delay;
- explicit-audience resolution outcome;
- whether semantic scoring was skipped or invoked;
- raw E5 relevance per candidate;
- deterministic candidate score before contextual reranking;
- Utility tie-break use and latency;
- final selected speaker set;
- Character Runtime start time;
- final delivery or silence reason.

Add feature flags for each later phase. Production must be able to fall back to the existing V3 path without schema rollback.

Exit criteria:

- Behavior Notebook can distinguish V3 baseline vs V4/shadow decisions.
- no raw embedding vectors, credentials, hidden prompts, or unbounded conversation text are added to observability.

# Phase 1 — Adaptive Turn Collector / Conversation Burst

Add a channel/thread-scoped collector before proactive Smart Participation.

Initial configurable defaults:

- quiet window: ~1.5 seconds after the most recent ordinary human message;
- maximum wait: ~4 seconds;
- maximum messages per burst: 5;
- bounded readable text budget around 1,500 characters for selection analysis.

The collector must preserve each source message separately:

- message ID;
- author ID/display name;
- timestamp;
- reply target;
- text;
- Emoji/Sticker semantics;
- attachments/media references.

Do not flatten the burst into one fake Discord message for persistence or delivery.

### Immediate/bypass path

Do not delay clearly addressed turns. The following should bypass or force-flush the collector:

- direct Discord reply to a Character Relay message;
- explicit Character name/address alias;
- explicit group address;
- interaction/session-controlled turns;
- other Runtime-owned explicit routes where waiting cannot improve audience resolution.

When an explicit turn arrives while an ordinary burst is pending, flush the pending burst in order before processing the explicit turn unless doing so would violate an existing explicit reply/interaction ordering contract.

### Burst semantics

A burst may contain multiple human authors. Preserve the speaker sequence so later intelligence can distinguish:

```text
A: 我觉得这个游戏很好玩
B: 哪里好玩了
A: 战斗啊
B: 我觉得超无聊
```

from a single-author four-line message.

Exit criteria:

- rapid fragmented messages usually create one proactive Smart Participation evaluation;
- explicit address latency is not materially increased;
- queued stale per-message evaluations are reduced;
- message IDs remain valid for Smart Output reply/reference behavior.

# Phase 2 — Reorder the Smart Participation pipeline

Move cheap deterministic work before E5/Utility wherever the result is already knowable.

Target order:

```text
explicit audience
→ no-deployment / participation-mode checks
→ burst/low-information handling
→ hard profile blocks / avoid rules
→ cooldown and channel rate-limit eligibility
→ candidate set
→ E5/context intelligence only for remaining candidates
```

Do not call semantic scoring for candidates already blocked by deterministic eligibility.

### Utility placement

Remove Utility tie-break from the raw semantic-score stage as the final selection authority. Preserve raw E5 scores. Utility should receive the final narrow candidate set only after deterministic and contextual evidence is assembled.

Rename/trace values clearly:

- `raw_e5_relevance` — unchanged embedding cosine result;
- `contextual_score` or equivalent — deterministic/context evidence result;
- `utility_adjustment` — bounded demotion/reranking result;
- `final_participation_score` — value used for admission.

The Utility must never be reported as having changed the raw E5 result.

Exit criteria:

- explicit names/group addresses do not trigger unnecessary semantic scoring;
- low-information/cooldown/rate-limited turns do not call Utility;
- Utility is invoked only for the actual final gray zone.

# Phase 3 — Server-side Conversation-Aware Participation Resolver

Replace the narrow Connector `/semantic-score` dependency with a conversation-aware resolver while retaining the old endpoint/path as a compatibility fallback during migration.

The resolver request should carry bounded scope and turn identity, for example:

```text
connection_id
guild_id
channel_id
thread_id
burst/message IDs
author IDs
reply target
bounded burst text
candidate deployment IDs
```

The server returns candidate evidence rather than raw vectors.

Candidate evidence should distinguish:

- raw E5 relevance;
- Character participation-profile relevance;
- active-topic affinity;
- recent topic participation;
- recent speaker/turn relationship evidence;
- Graph evidence when enabled;
- Utility use/reason when enabled;
- final recommendation/admission metadata.

### Participation Semantic Profile V2

Build a stable semantic participation source that may include:

- existing Character identity/persona fields;
- configured Smart Participation topics;
- role/group-role hints;
- concise positive participation guidance.

Keep these outside the embedding and deterministic:

- avoid phrases / hard boundaries;
- cooldowns;
- enable/disable;
- rate limits;
- permissions.

### Eliminate preview/runtime drift

Move the authoritative participation scoring contract to one server-side implementation or one shared contract with generated parity tests. The Portal Playground and Discord Runtime must not evolve independent scoring semantics.

The Connector may keep a bounded local fallback for server unavailability, but the fallback must be explicitly observable as degraded mode.

Exit criteria:

- Portal preview and Discord Runtime use the same authoritative evidence/scoring contract;
- Topic evidence can affect speaker selection before Character Runtime;
- one request replaces the current semantic-score request rather than adding another normal-turn network hop.

# Phase 4 — Conversation Intelligence Graph foundation (shadow mode)

Implement a lightweight graph on SQLite.

Initial node types:

- `Topic`
- `Character`
- `Actor`
- `Event`
- `Media`
- `ConversationBurst`

Initial edge types:

- `PARTICIPATED_IN`
- `RELATED_TO`
- `MENTIONED`
- `REPLIED_TO`
- `INVOLVED_IN`
- `REFERENCES`
- `PERCEIVED`
- `SKIPPED`
- `INSPECTED`
- `FOLLOWED_BY`

Edges must include bounded provenance and lifecycle metadata such as confidence/source/created/last-active timestamps where relevant.

### Graph is derived evidence

Raw Discord messages, existing Topic records, media cache records, and Runtime-owned state remain authoritative. Graph nodes/edges are a derived index that can be rebuilt or pruned.

### Shadow mode

Graph initially has **zero effect** on speaker admission.

For every eligible V3 decision, compute a shadow recommendation and show in Behavior Notebook:

- V3 selected candidate(s);
- Graph-assisted recommendation;
- graph paths/evidence used in bounded human-readable form;
- agreement/disagreement reason.

Do not expose private raw message history through graph traces.

Exit criteria:

- Graph updates are bounded and do not create an LLM call on every message;
- Graph shadow decisions can be evaluated against real outcomes/feedback;
- SQLite size/latency and cleanup behavior are measured.

# Phase 5 — Graph-assisted reranking

After shadow data is acceptable, allow Graph evidence to rerank only candidates that already passed deterministic eligibility.

First rollout rule:

> Graph may support ordering/demotion among plausible candidates, but may not make an otherwise ineligible Character cross the participation threshold.

Useful evidence includes:

- Character recently participated in the active topic;
- Character is directly involved in a referenced event;
- current burst explicitly/implicitly continues a prior Character statement;
- topic is linked to media perceived by that Character;
- bounded Character↔Character coordination/history relevant to the current topic;
- repeated participation penalties to avoid one Character monopolizing a topic.

Do not use a universal `graph_score +N` table detached from provenance. Produce named evidence with bounded weights so Behavior Notebook can explain why the ranking changed.

Utility Judge receives Graph evidence only in the final ambiguous candidate set. It cannot traverse arbitrary graph data or select outside the supplied candidates.

Exit criteria:

- measurable reduction in wrong-speaker and duplicate-speaker feedback;
- no measurable increase in intrusive replies;
- Graph can be disabled without changing stored authoritative conversation/media data.

# Phase 6 — Media + Topic relationship integration

Connect existing Media Understanding and Topic Memory to the graph without changing media perception policy.

### Media object vs Character epistemic state

Represent shared media understanding separately from per-Character perception:

```text
Media object
  SHA-256
  summary
  readable text/OCR when available
  source/reference metadata

Character A ─ PERCEIVED → Media
Character B ─ SKIPPED   → Media
```

If Character A caused the media understanding to be computed and Character B later chooses to inspect the same SHA-256 content, B may reuse the cached understanding while still gaining its own `PERCEIVED/INSPECTED` edge only after the Runtime says B actually perceived it.

### Graph-assisted historical media recall

Keep current explicit/reply recall and semantic safeguards. Graph adds a candidate narrowing path:

```text
current topic/burst
→ related historical topic/event
→ linked media
→ semantic rerank
→ bounded media context
```

Graph must not resurrect stale media merely because an old relationship exists. Recency, explicit reference, reply reference, privacy scope, and current Media Recall policy remain inputs.

### Topic evolution

Topic Memory remains the lifecycle authority for `active / cooling / closed / archived`. Graph adds relationships between topics/events/media/participants rather than replacing continuation classification.

Exit criteria:

- fewer irrelevant historical-media recalls;
- repeated SHA content does not cause unnecessary Media Understanding calls;
- no Character gains knowledge of media it never perceived.

# Phase 7 — Durable social state and final rollout

Move only the speaker-selection state that must survive restart/multi-replica operation to a server-side durable source of truth.

Candidates include:

- admitted proactive selections relevant to cooldown/rate limits;
- recent speaker anchor needed by lightweight follow-up;
- burst identity/status if a collector must recover safely.

Keep high-frequency ephemeral caches local where correctness does not require durability.

### Final evaluation matrix

Validate at minimum:

- English, Simplified Chinese, Traditional Chinese, mixed Chinese/English, and Malay social turns;
- single-author fragmented bursts;
- multi-author bursts;
- direct Mention/Reply/name/group address fast paths;
- low-information acknowledgements;
- rapid topic switch;
- short pronoun/continuation turns such as `真的？然后呢？`;
- competing Character Card semantic profiles;
- existing primary/secondary coordination;
- current image attachment behavior;
- link/video Tool-driven inspection;
- repeated media SHA reuse across different Characters;
- historical media recall and stale-media rejection;
- Utility provider unavailable/malformed/low-confidence behavior;
- restart and multi-replica-safe social accounting;
- Behavior Notebook trace completeness.

### Success metrics

Compare V4 to the recorded V3 baseline:

- semantic resolver calls per human message;
- Utility calls per human message;
- p50/p95 selection latency;
- Character Runtime calls per human message;
- user feedback: correct / should speak / should stay silent;
- wrong-speaker rate;
- duplicate/interruptive reply rate;
- stale-media recall rate;
- media-understanding cache reuse;
- Graph rows/DB growth and cleanup cost;
- Railway baseline/peak RAM and CPU under representative bursts.

### Merge policy

The PR stays Draft until all phases intended for the release are complete and the final validation matrix is recorded.

Do not merge solely because CI is green. Final merge requires:

1. Python/Web/Discord/Docker CI green;
2. Railway Smoke green;
3. no regression in explicit addressing or Smart Output delivery;
4. measured V3 vs V4 selection/latency evidence;
5. bounded Graph storage/cleanup evidence;
6. explicit owner approval.

If Graph does not show enough measured benefit, the same PR may ship the Turn Collector + pipeline reorder + conversation-aware resolver while leaving Graph reranking disabled/shadow-only. Graph storage must remain removable without breaking authoritative Topic/Media/Runtime records.

## Expected end state

V3 primarily asks:

> Which Character Card is semantically relevant to this message?

V4 should instead answer:

> What is this short conversation burst doing, which topic/event/media/people does it continue, who has actually been involved, and which already-eligible Character would most naturally take the next turn?

The implementation must achieve that without turning Character Relay into an always-on LLM router.