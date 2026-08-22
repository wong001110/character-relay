# Conversation Intelligence Control Plane Roadmap

Status: **historical branch roadmap — superseded by Intelligence Core v3 and current source/tests**
Branch: `agent/conversation-intelligence-control-plane`

## Goal

Make Topic, Memory, Character Learned State, and Social Graph behavior observable, governable, repairable, and retrieval-efficient without weakening the existing deterministic/runtime authority model.

The revised architecture incorporates two useful ideas without copying either system literally:

1. **SAG / SQL-Retrieval Augmented Generation** — persist semantically complete events and typed entities in relational storage, use dense retrieval for seed recall, then activate query-local relationships through bounded SQL joins rather than maintaining a global retrieval graph.
2. **ChatGPT-style layered memory principles** — keep durable user-controlled memories separate from broad conversation history, and use background synthesis to keep inferred memory fresh, relevant, reviewable, and replaceable over time.

This work intentionally does **not** introduce GNNs or a new Graph database. Existing SQL-backed authority remains authoritative. Embeddings, query-local structure, synthesized Memory, and Social Graph projections remain derived/rebuildable intelligence.

## Revised memory model

Character Relay should no longer treat every form of memory as one table or one retrieval strategy.

### Working Memory
- Recent Discord turn/burst context.
- Active Topic capsule and pending actions.
- Short-lived and deterministic.

### Episodic History
- Episode rows are the semantically complete event unit.
- Episodes retain source message/media refs and timestamps.
- Episodic retrieval uses SQL scope constraints + E5 seed recall + query-time event/entity expansion.
- Episodes are evidence; they are not automatically durable Character beliefs.

### Saved / Core Memory
- Explicitly user-approved or user-promoted durable Character memory.
- Pinned/high-priority, reviewable, editable, and not silently decayed away.
- Appropriate for stable facts/preferences/constraints the Character should reliably carry forward.

### Synthesized Memory
- Background-consolidated memory inferred from many Episodes.
- Freshness-aware and supersedable.
- Appropriate for changing preferences, plans, recurring patterns, relationship summaries, and durable observations.
- Must preserve provenance back to Episode/message evidence.

### Learned State
- Numeric/temporal state such as interest, relationship, salience, ownership, fatigue, expertise, stance.
- Append-only evidence history + fast aggregate read model.
- Not converted into prose Memory unless consolidation has sufficient evidence.

### Memory Summary
- A compact per-Character/per-server synthesis of currently useful context.
- Generated in the background from Saved Memory + Synthesized Memory + recent relevant history.
- Versioned/reviewable and optimized for freshness rather than being an immutable notebook dump.

## Revised retrieval architecture

### SQL event/entity index

Use existing Episodes as event records. Add typed canonical entities and incidence rows instead of materializing a global knowledge graph for retrieval.

Examples of deterministic entities:
- Discord user / actor
- Character Card / deployment
- Topic
- Media
- Tool/action
- Server/channel/thread
- time window

Semantic entities may include projects, works, products, subjects, preferences, goals, or named concepts. These should be extracted in background consolidation and only when they improve retrieval; do not run an LLM extractor on every Discord message.

### Character epistemic isolation

A server-wide event index must never make Characters omniscient. Retrieval requires an explicit perception/access constraint showing that a Character actually observed or was authorized to use the Episode/evidence.

### Query-time recall

1. Apply exact SQL authority filters: owner, Character, Discord server, visibility/perception, subject/user, time, Topic when applicable.
2. Use multilingual E5 to retrieve seed Episodes/Memories.
3. Expand only a bounded local neighborhood through shared typed entities using SQL joins.
4. Prune high-degree/noisy entities and cap expansion budget.
5. Hybrid-rerank dense + sparse + recency + confidence/importance.
6. Use Utility/LLM Judge only for genuinely ambiguous final selection or synthesis.
7. Return original Episode/Memory evidence to the Character runtime; query-local structure is an index, not truth.

## Graph responsibility after revision

### Keep Graph for
- Character ↔ User / Character ↔ Character relationship state.
- Participation history, ownership, fatigue, and other edge-weight/decay signals.
- Ego-graph observability and optional graph-native analytics.
- Media perception links when they encode epistemic truth.

### Do not require persistent Graph for
- General Memory retrieval.
- Topic/Episode multi-hop recall.
- Generic event/entity association.

These are better represented as SQL event/entity incidence and activated at query time. Authority/provenance Graph edges may remain where useful for audit/visualization, but they are not the primary retrieval backbone.

## Phase 0 — Baseline and safety contracts

- Add tests that lock current Topic/Memory/Graph authority boundaries.
- Define mutation contracts for archive, invalidate, delete-derived-data, and scoped reset.
- Define observation event schemas before changing runtime behavior.
- Preserve raw Discord event/message evidence during derived-data cleanup.

Exit criteria:
- destructive operations have explicit scope and dry-run coverage;
- no operation can silently delete raw Discord source evidence.

## Phase 1 — Data Hygiene and Governance

### Topic governance
- Archive a Topic manually.
- Delete corrupted Topic-derived intelligence with a dry-run impact preview.
- Scoped reset by Discord server/channel/thread.
- Cascade/invalidate dependent Topic vectors, Topic-local Memories, Wiki pages, query-index projections, checkpoints, and Topic-scoped Learned State where applicable.

### Memory governance
- Browse Memory vNext by Character + server.
- Invalidate/delete one synthesized Memory record.
- Reset derived Memories for one Character + server.
- Keep provenance visible before destructive operations.
- Add distinction between user-pinned Saved/Core Memory and auto-synthesized Memory before broad auto-cleanup is enabled.

Exit criteria:
- polluted Topic/Memory data can be removed without deleting raw Discord conversation evidence;
- all destructive actions are owner-scoped and auditable.

## Phase 2 — Topic Lifecycle and Decision Observatory

Implement explicit lifecycle:

`active -> cooling -> closed -> archived`

Historical semantic resume may reactivate an appropriate cooling/closed Topic. Pending actions may hold a Topic open when required.

Compute/reuse one Topic continuity decision per turn and record bounded evidence:
- from_topic_id / to_topic_id
- continue | switch | resume | create
- dense/sparse score
- continuation/switch act evidence
- idle age
- reason code
- timestamp/message id

Observation:
- server/channel Topic counts by lifecycle status
- stale-active warning
- transition timeline
- decision trace details
- mixed-content warning

Exit criteria:
- a developer can explain why a Topic continued, switched, resumed, or was created;
- stale active Topics no longer persist indefinitely.

## Phase 3 — Interaction Grounding

Separate semantic relevance from conversational address before roleplay generation.

Deterministic states:
- `direct_character`
- `group_invited`
- `ambient`
- `role_group_directed`
- `ambiguous`

Default rule: professional/topic relevance may increase participation relevance but must not imply that a Character is being interviewed, challenged, accused, or asked for professional advice.

Exit criteria:
- ambient profession-related discussion produces peer-group behavior by default;
- explicit addressing/challenges remain detectable;
- Utility/LLM Judge is limited to pragmatic gray zones.

## Phase 4 — Episodic SQL-RAG Index

### Schema
- Reuse `ConversationEpisodeRecord` as the event/evidence unit.
- Add canonical `ConversationEntity` rows.
- Add `EpisodeEntity` incidence rows.
- Add Character↔Episode perception/access rows where server-global Episode visibility would otherwise cause omniscient recall.
- Entity identity must be stable and owner/server scoped where appropriate.

### Indexing
- Deterministically index known structured refs first: actor, Character, Topic, media, tool/action, location, time.
- During background consolidation, optionally extract semantic entities from Episode summaries/key points.
- Do not run semantic entity extraction on every raw message.
- Keep all entity-derived structure rebuildable from Episode/source evidence.

### Retrieval
- E5 seed Episodes.
- SQL event→entity→event expansion, normally one bounded expansion round.
- High-degree entity suppression.
- Hybrid rerank and strict candidate budgets.
- Return original Episode evidence.

Exit criteria:
- multi-hop conversational recall can recover related evidence that plain top-k E5 misses;
- no global graph rebuild is required when new Episodes are added;
- Character epistemic isolation is preserved.

## Phase 5 — Dreaming-style Background Memory Synthesis

Borrow the product principles of modern ChatGPT Memory without assuming OpenAI's private implementation.

### Saved/Core Memory
- User-created/promoted memory.
- Pin/prioritize control.
- Explicit edit/delete.
- Revision history.

### Synthesized Memory
- Background job reads new/changed Episodes since checkpoint plus current Memory state.
- Produces create/reinforce/supersede/merge/invalidate proposals.
- Maintains `valid_from`, `valid_to`, `last_confirmed_at`, freshness/staleness state.
- Separates stable fact/preference from temporary plan/location/event state.
- Can rewrite current-state memory into historical state when time passes instead of leaving stale present-tense facts active.

### Memory Summary
- Maintain a compact current memory summary per Character + server.
- Summary is reviewable/versioned and regenerated from authoritative Memory/Episode evidence.
- Summary is context optimization, never the only source of truth.

Exit criteria:
- Memory can stay current as circumstances change;
- stable Saved Memory cannot be silently overwritten by background synthesis;
- every synthesized statement remains traceable to evidence.

## Phase 6 — Unified Character Recall Router

Route each turn among different memory layers instead of treating all recall as one vector search.

Possible sources:
- Working Memory / active Topic
- Saved/Core Memory
- Synthesized Memory / memory summary
- Episodic SQL-RAG
- Wiki/server knowledge
- Learned State / Social Graph

Policy:
- exact/direct references use SQL filters first;
- semantic historical references use E5 + SQL-RAG expansion;
- high-confidence relevant Saved Memory may be preloaded narrowly;
- deeper history remains tool/agent retrievable;
- providers without reliable tool-calling receive a tiny, bounded high-confidence pre-turn recall fallback.

Exit criteria:
- no provider is completely memory-blind only because it failed to call `memory.search`;
- prompt injection remains bounded and evidence-backed;
- broad history is not dumped into every turn.

## Phase 7 — Character Mind and Social Graph

Split Learned State UI by timescale:

### Now
- salience
- conversation ownership
- participation fatigue

### Developing preferences/knowledge
- interest
- expertise
- stance

### Social
- relationship

Keep append-only evidence history with value-before/value-after, delta, confidence, source, Discord server/channel/Topic scope, reason, and timestamp.

Social Graph becomes specialized rather than universal:
- canonical Character/User actor identity
- Character ↔ User / Character ↔ Character relationship projection
- server-scoped ego graph
- edge strength/confidence/recency/evidence
- optional lightweight NetworkX analytics only where graph-native metrics are useful

Exit criteria:
- interest/relationship changes can be explained over time and per server;
- Graph no longer carries generic retrieval responsibilities better served by SQL-RAG.

## Phase 8 — Portal Observation and Memory Controls

Portal should expose the layers distinctly rather than rendering one generic Memory screen.

Views:
- Server overview
- Topic timeline + decision traces + cleanup
- Saved/Core Memory
- Synthesized Memory + provenance + freshness
- Episode/Event retrieval trace
- Entity neighborhood activated for a query
- Memory Summary history
- Current Interest
- Social ego graph

Controls:
- archive/reset polluted derived data
- pin/promote/unpin Memory
- edit/delete Memory
- inspect/restore Memory revisions
- optionally mark a session/channel as no-memory for future use

Exit criteria:
- the developer/user can inspect what the Character currently remembers, why, from which evidence, and whether it is stable or inferred.

## Phase 9 — Calibration, rollout, and acceptance

- Shadow traces for lifecycle, grounding, SQL-RAG expansion, memory synthesis, and graph-derived signals.
- Compare baseline E5 retrieval against E5 + SQL query-local expansion.
- Measure recall@k on curated Character Relay multi-hop conversation cases.
- Track candidate expansion size, high-degree entity suppression, and retrieval latency.
- Track Saved vs Synthesized Memory usage and stale-memory corrections.
- Add counters for E5/SQL clear decisions vs Utility/Judge escalations.
- Validate judge-call rate stays low.
- Regression cases for profession-background ambient chat, explicit expert request, explicit challenge, historical topic resume, cross-episode references, bot-to-bot relationships, and per-Character perception isolation.

Final acceptance focus:
1. polluted Topic/Memory data can be safely cleaned;
2. Topic lifecycle/switching are explainable;
3. Characters do not mistake mere topic relevance for being personally questioned;
4. episodic recall supports structured multi-hop retrieval without a global retrieval graph;
5. Saved Memory and synthesized history are separate, controllable, fresh, and provenance-backed;
6. relationship/interest remain inspectable and server-aware;
7. Utility/LLM Judge remains a bounded low-frequency ambiguity resolver.
