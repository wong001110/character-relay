# Conversation Intelligence Control Plane Roadmap

Status: active development
Branch: `agent/conversation-intelligence-control-plane`

## Goal

Make Topic, Memory, Character Learned State, and Conversation Graph behavior observable, governable, and repairable without weakening the existing deterministic/runtime authority model.

This work intentionally does **not** introduce GNNs or a new Graph database. Existing SQL-backed authority remains authoritative. Graph and embedding systems remain derived/rebuildable intelligence layers.

## Guiding architecture

- Deterministic routing and platform addressing remain first-line authority.
- Multilingual E5 handles frequent semantic relevance and retrieval.
- Graph/Learned State provide contextual reranking and explainable relationship evidence.
- LLM/Utility Judge is a low-frequency ambiguity resolver only.
- Character roleplay generation remains separate from participation admission.
- Raw Discord messages are source evidence; Topic/Memory/Wiki/Graph/Learned State are derived intelligence and must be governable.

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
- Cascade or invalidate dependent Topic semantic vectors, Topic-local Memories, Wiki pages, Graph projections, consolidation checkpoints, and Topic-scoped Learned State where applicable.

### Memory governance
- Browse Memory vNext by Character + server.
- Invalidate/delete one Memory record.
- Reset derived Memories for one Character + server.
- Keep provenance visible before destructive operations.

Exit criteria:
- previously polluted Topic/Memory data can be removed without deleting raw Discord conversation evidence;
- all destructive actions are owner-scoped and auditable.

## Phase 2 — Topic Lifecycle and Decision Observatory

### Lifecycle
Implement an explicit lifecycle rather than leaving stale Topics permanently active:

`active -> cooling -> closed -> archived`

Historical semantic resume may reactivate an appropriate cooling/closed Topic. Pending actions can hold a Topic open when required.

### TopicDecision
Compute continuity once per turn and pass the same decision through Tool Continuation, Topic observation, Episode projection, and tracing.

Record bounded decision evidence:
- from_topic_id / to_topic_id
- decision: continue | switch | resume | create
- dense score
- sparse score
- continuation/switch act evidence
- idle age
- reason code
- timestamp/message id

### Observation UI
- server/channel Topic counts by lifecycle status
- stale-active warning
- Topic transition timeline
- decision trace details
- Topic semantic cohesion / mixed-content warning

Exit criteria:
- a developer can answer why a Topic continued, switched, resumed, or was created;
- stale active Topics no longer persist indefinitely by default.

## Phase 3 — Interaction Grounding

Problem: semantic relevance does not imply conversational address. A Character whose profession/background matches a topic can currently interpret ambient group discussion as a question, challenge, or interrogation directed at them.

Add a cheap interaction-grounding layer after participation relevance and before roleplay generation.

### Deterministic states
- `direct_character`: mention, reply, or explicit Character-name addressing
- `group_invited`: explicit group invitation
- `ambient`: ordinary group discussion
- `role_group_directed`: statements/questions explicitly directed at a profession/group
- `ambiguous`: only this state may escalate to Utility/LLM Judge

### Grounding output
Provide compact runtime context:
- audience
- interaction type
- directed_at_character
- expertise_relevant
- expertise_requested
- response_posture

Default rule: professional background may increase relevance but must not imply that the Character is being interviewed, challenged, accused, or asked for professional advice.

Exit criteria:
- ambient profession-related conversations produce peer-group behavior by default;
- explicit addressing and genuine challenges remain detectable;
- LLM Judge frequency remains low and limited to pragmatic gray zones.

## Phase 4 — Memory Observatory and Retrieval Consistency

- Character × Server Memory browser.
- Filters for scope/type/status/confidence/importance.
- Provenance chain: Memory -> Episode -> Message.
- Use count / last used / superseded-by history.
- Add shared E5 hybrid retrieval to Topic/Episode searches.
- Use semantic candidate matching during Memory consolidation to reduce paraphrase duplicates.
- Add a tiny high-confidence pre-turn recall fallback while preserving tool-driven deeper recall.

Exit criteria:
- Memory formation and recall are inspectable;
- paraphrastic duplicates are materially reduced;
- providers without proactive tool use still receive narrowly justified historical context.

## Phase 5 — Character Mind Observation

Split Learned State UI by timescale instead of rendering every signal as one generic meter:

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

Add append-only Learned State evidence events containing value-before/value-after, delta, confidence, source, reason, and timestamp. Keep the existing aggregate table as the fast runtime read model.

Exit criteria:
- dynamic interest/relationship changes can be inspected over time;
- evidence provenance explains every material change.

## Phase 6 — Social Graph Observatory

- Canonical Character/User actor identities.
- Character ↔ User and Character ↔ Character relationship projection.
- Server-scoped relationship/interest views where context requires it.
- Ego-graph UI rather than an unreadable global hairball.
- Edge strength, confidence, recency, and evidence inspection.
- Optional lightweight NetworkX analytics for community/cohesion/multi-hop observation.

Exit criteria:
- a developer can inspect who a Character is close to, why, in which server/context, and how that relation changed;
- Graph remains a derived/rebuildable projection rather than primary authority.

## Phase 7 — Calibration, rollout, and acceptance

- Shadow traces for new lifecycle, grounding, and graph-derived signals.
- Compare old/new participation and Topic outcomes.
- Add observability counters for E5 clear decisions vs Utility/Judge escalations.
- Validate judge-call rate stays low.
- Regression cases for profession-background ambient chat, explicit expert request, explicit challenge, group invitation, and bot-to-bot conversation.
- Keep active rollout behind existing reversible modes where appropriate.

Final acceptance focus:
1. polluted Topic/Memory data can be safely cleaned;
2. Topic lifecycle and switching are explainable;
3. Characters do not mistake mere topic relevance for being personally questioned;
4. Memory, relationship, and dynamic interest are understandable in the Portal;
5. Utility/LLM Judge remains a bounded low-frequency ambiguity resolver.
