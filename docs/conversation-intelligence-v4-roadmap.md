# Smart Participation V4 — Conversation Intelligence Graph Roadmap

Status: **IMPLEMENTED / RELEASE VALIDATED IN DRAFT PR #166**

Branch: `agent/conversation-intelligence-v4`

Delivery rule: **all work in this roadmap stays in one Draft PR until final validation and explicit merge approval.** Do not split Turn Collector, participation pipeline reorder, conversation-aware resolution, Graph shadow mode, Graph reranking, Character Learned State, Topic/Media integration, or final rollout into separate implementation PRs.

## Implementation result

Phases 0–8 are implemented on `agent/conversation-intelligence-v4` in Draft PR #166.

Release validation completed against commit `4591f3c405136fd1c072837175b1a70e2dc07827`:

- **CI #1314:** green — Python 3.12/3.13 Ruff, strict Mypy and full Pytest; Web typecheck/tests/build; Discord Connector typecheck/tests/build/image; production Docker persistence and smoke checks.
- **Railway Smoke #1280:** green.
- Final guarded Connector edge validation passed **126 / 126 Vitest tests**, Python Media provenance tests, strict Mypy, Connector build, and `git diff --check`.
- Durable low-information recovery now restores a recent Smart speaker after Connector process-state loss without adding a request to the normal hot path.
- Pure visible-image bursts preserve the original Discord image-message ID through Media perception, Conversation Media, and Graph provenance; URL/video inspection policy remains Tool-driven.
- The Public Demo Status workflow remains red because the deployed demo has 5 Characters but only 3 ready credentials. The same workflow is red on current `main`, so this is recorded as a pre-existing deployment/configuration issue rather than a V4 runtime regression.

The PR remains **Draft and unmerged**. Runtime rollout remains independently disableable/shadowable and merge still requires explicit owner approval.

## Goal

Upgrade Smart Participation from per-message Character Card relevance into a conversation-aware speaker planner that understands short message bursts, active topic continuity, participants, events, media, bounded relationships, and evidence-backed learned character state without moving runtime authority into an LLM.

Target path:

```text
Discord messages
→ explicit audience fast path
→ adaptive Turn Collector
→ Conversation Burst
→ cheap deterministic gates
→ Topic / conversation state
→ E5 + Graph + learned-state evidence
→ candidate reranking
→ Utility Judge only for final ambiguity
→ Speaker Plan
→ Character Runtime
```

The Graph is an evidence and memory layer. It is **not** another independent detector and must not bypass explicit addressing, hard blocks, cooldowns, rate limits, Tool permissions, media epistemic truth, Character Card authority, or Runtime delivery authority.

## Current production baseline

V4 starts from the current `main` behavior:

- Smart Participation V3 semantic Character Card profiles use the shared multilingual E5 runtime.
- query embeddings are reused across semantic consumers through the process-shared cache.
- deterministic Smart Participation owns enablement, style, literal topics/keywords/triggers, avoid phrases, cooldowns, channel limits, lightweight follow-up, and multi-character admission.
- the Utility Gateway can break narrow E5 ties, but it may only demote competing candidates and cannot grant eligibility.
- Conversation Topic Memory persists bounded topic capsules with summary, keywords, participants, open loops, pending actions, status, and semantic continuation/switch classification.
- Tool continuation already uses Topic Memory and the Utility Gateway only in bounded gray zones.
- Media Understanding keeps SHA-256/cache reuse, passive visible-image perception, Tool-driven link/video inspection, character-scoped epistemic state, semantic historical recall, and lazy OCR hydration.
- Behavior Notebook can observe silent/no-selection Smart Participation turns and candidate score breakdowns.

## Problems to solve

### 1. Per-message evaluation during message bursts

The Connector serializes messages per channel/thread, but each human message is still independently processed. Rapid fragments can therefore trigger repeated semantic scoring against incomplete thoughts and can let a Character react before the human has finished.

### 2. Expensive semantic work happens before some cheap routing decisions

Semantic Character relevance may be requested before name/group audience resolution and before low-information, cooldown, rate-limit, and other cheap eligibility decisions are fully known.

### 3. Utility tie-break is based on E5 ambiguity rather than final participation ambiguity

The Utility currently sees current text plus Character semantic profiles and E5 scores, while later deterministic scoring can still change candidate order. Utility should operate only after deterministic and contextual evidence has produced the actual final gray zone.

### 4. Topic intelligence is mainly post-selection

Topic Memory is currently most useful after a Character has already been admitted. V4 should use bounded active-topic evidence during speaker selection while preserving one authoritative topic lifecycle implementation.

### 5. Character semantic participation profiles are too static

The current participation embedding is based mostly on Character identity/persona fields. V4 should support a participation-focused semantic representation that can include configured participation topics and role hints without embedding hard avoid/boundary rules that must remain deterministic.

### 6. Context intelligence is fragmented

Smart Participation, Topic Memory, Media Recall, Tool continuation, and RAG make related semantic/context decisions. V4 should let them consume one bounded conversation state rather than adding more independent detectors.

### 7. Character behavior is treated as mostly static

A Character Card can define stable interests and personality, but long-running group interaction also produces evidence about what a Character repeatedly engages with, understands, has opinions about, is socially close to, currently owns in the conversation, or has recently over-participated in. V4 should represent this as learned state without silently rewriting the Character Card.

### 8. Some speaker-state accounting is process-local

Connector-local admission/cooldown bookkeeping resets on restart and is unsuitable as a long-term multi-replica source of truth. V4 should define which state must become server-side/durable while preserving cheap local caches where safe.

## Architecture invariants

1. Explicit Discord addressing remains highest priority.
2. Hard deterministic blocks remain authoritative.
3. The Character model never decides whether it was eligible to receive a turn.
4. Utility LLM output remains advisory and bounded to supplied candidates.
5. Graph evidence cannot grant Tool permission or side-effect authority.
6. Character Card core personality/interests/boundaries remain authoritative over learned state.
7. Dynamic interests, stance, expertise, and relationships are evidence-backed derived state and must be correctable, decayed, pruned, or rebuilt.
8. Media content truth and Character perception truth remain separate.
9. The same media understanding may be reused by SHA-256, but each Character's `PERCEIVED / SKIPPED / INSPECTED` state remains character-scoped.
10. SQLite remains the initial source of truth. No Neo4j, external graph database, GNN, or external Vector DB is required for V4.
11. Existing E5 runtime remains the high-frequency semantic engine.
12. Every new stage must be independently disableable and must degrade to the current V3 path.
13. Derived state must carry bounded provenance/confidence and must not become permanent truth merely because one inference produced it.
14. Time-sensitive state must decay or expire according to its semantic type.

---

# Phase 0 — Measurement baseline and compatibility contract

Before behavior changes, extend observability so V3 and V4 can be compared on the same traffic.

Record at minimum:

- message arrival timestamp and processing start delay;
- explicit-audience resolution outcome;
- whether semantic scoring was skipped or invoked;
- raw E5 relevance per candidate;
- deterministic candidate score before contextual reranking;
- Utility use and latency;
- final selected speaker set;
- Character Runtime start time;
- final delivery or silence reason.

Add feature flags for each later phase. Production must be able to fall back to V3 without schema rollback.

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

Preserve each source message separately: message ID, author, timestamp, reply target, text, Emoji/Sticker semantics, and media references. Do not flatten the burst into one fake Discord message for persistence or delivery.

### Immediate/bypass path

Do not delay clearly addressed turns. Direct replies, explicit Character names/aliases, explicit group addresses, interaction/session-controlled turns, and other Runtime-owned explicit routes should bypass or force-flush the collector.

When an explicit turn arrives while an ordinary burst is pending, preserve ordering while avoiding unnecessary latency.

Exit criteria:

- rapid fragments usually create one proactive evaluation;
- explicit-address latency is not materially increased;
- queued stale per-message evaluations are reduced;
- original message IDs remain valid for Smart Output references.

# Phase 2 — Reorder the Smart Participation pipeline

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

Move Utility out of the raw semantic-score stage. Preserve raw E5 scores and call Utility only on the true final gray zone.

Trace separately:

- `raw_e5_relevance`
- `contextual_score`
- `utility_adjustment`
- `final_participation_score`

Utility must never be reported as having changed raw E5 relevance.

Exit criteria:

- explicit names/group addresses do not trigger unnecessary semantic scoring;
- low-information/cooldown/rate-limited turns do not call Utility;
- Utility is invoked only for actual final ambiguity.

# Phase 3 — Server-side Conversation-Aware Participation Resolver

Replace the narrow Connector `/semantic-score` dependency with one conversation-aware resolver while retaining compatibility fallback during migration.

The request should carry bounded scope and turn identity: connection/guild/channel/thread, burst/message IDs, authors, reply target, bounded burst text, and candidate deployment IDs.

Candidate evidence should distinguish:

- raw E5 relevance;
- Character participation-profile relevance;
- active-topic affinity;
- recent topic participation;
- recent speaker/turn relationship evidence;
- learned-state evidence when enabled;
- Graph evidence when enabled;
- Utility use/reason when enabled;
- final recommendation/admission metadata.

### Participation Semantic Profile V2

The stable semantic participation source may include Character identity/persona fields, configured Smart Participation topics, role/group-role hints, and concise positive participation guidance.

Keep avoid phrases, hard boundaries, cooldowns, enable/disable, rate limits, and permissions outside the embedding and deterministic.

### Eliminate preview/runtime drift

Move authoritative scoring to one server-side implementation or one shared contract with parity tests. Portal Playground and Discord Runtime must not evolve independent semantics.

Exit criteria:

- Portal preview and Discord Runtime share the same evidence/scoring contract;
- Topic evidence can affect speaker selection before Character Runtime;
- one request replaces the current semantic-score request rather than adding another normal-turn network hop.

# Phase 4 — Conversation Intelligence Graph foundation (shadow mode)

Implement a lightweight graph on SQLite.

Initial node types:

- `Topic`
- `Concept`
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

Edges/state must carry bounded provenance and lifecycle metadata where relevant, including confidence, evidence/source IDs, created/updated/last-active timestamps, and expiry/decay class.

### Entity/concept normalization

Aliases and semantically equivalent concepts must resolve conservatively so `摄影`, `拍照`, and `photography` do not become unrelated permanent nodes. Prefer deterministic aliases + E5; use Utility only for bounded ambiguity. Never merge entities solely because one LLM response says they are the same.

### Graph is derived evidence

Raw Discord messages, Topic records, Character Cards, media cache records, and Runtime-owned state remain authoritative. Graph data must be rebuildable/prunable.

### Shadow mode

Graph initially has zero effect on speaker admission. Behavior Notebook should compare V3 selection with Graph-assisted shadow recommendations and show bounded evidence paths/reasons.

Exit criteria:

- Graph updates are bounded and do not create an LLM call on every message;
- shadow decisions can be evaluated against real outcomes/feedback;
- SQLite size/latency and cleanup behavior are measured.

# Phase 5 — Graph-assisted reranking

After shadow data is acceptable, allow Graph evidence to rerank only candidates that already passed deterministic eligibility.

First rollout rule:

> Graph may support ordering/demotion among plausible candidates, but may not make an otherwise ineligible Character cross the participation threshold.

Useful evidence includes active-topic participation, event involvement, continuation of a prior Character statement, media perceived by the Character, bounded Character↔Character context, and repeated participation penalties.

Do not use one opaque universal graph score. Produce named evidence with bounded weights so Behavior Notebook can explain ranking changes.

Utility receives Graph evidence only for the final ambiguous candidate set and cannot traverse arbitrary graph data or select outside supplied candidates.

Exit criteria:

- measurable reduction in wrong-speaker and duplicate-speaker feedback;
- no measurable increase in intrusive replies;
- Graph can be disabled without changing authoritative conversation/media data.

# Phase 6 — Character Learned State & Social Dynamics (shadow first)

Add evidence-backed learned state without modifying Character Card core identity. The same derived-state infrastructure should serve Smart Participation and later Character context, but initial rollout affects neither eligibility nor persona truth until shadow validation succeeds.

## 6.1 Core vs learned state

Keep three layers separate:

```text
Character Card / Core
  personality
  explicit interests/dislikes
  hard boundaries
        ↓ authoritative constraints
Learned Character State
  dynamic interest
  expertise
  stance
  relationships
        ↓ bounded evidence
Short-term Social State
  conversation ownership
  salience
  participation fatigue
```

A dynamic signal may refine behavior inside Character Card boundaries, but may not contradict an explicit core fact. For example, repeated horror discussion must not turn an explicit `hates horror` Card fact into `likes horror`.

## 6.2 Dynamic Interest Affinity

Represent repeated topic/concept engagement separately from core interests.

Example:

```text
Character ─ INTERESTED_IN → Photography
  affinity = 0.72
  confidence = 0.81
  positive_evidence = 9
  negative_evidence = 3
```

Potential positive evidence includes repeated voluntary participation, follow-up questions, inspected related media, and sustained topic engagement. Negative evidence may include repeated eligible-but-silent outcomes or repeated disengagement, but one silence must never be treated as dislike.

Dynamic interest uses medium decay and must not create a positive feedback loop where being selected once permanently makes future selection more likely.

## 6.3 Expertise Affinity

Interest and competence must be independent.

```text
Character A: INTERESTED_IN PC Hardware = high; EXPERT_IN = low
Character B: INTERESTED_IN PC Hardware = medium; EXPERT_IN = high
```

Technical/help questions may value expertise more than casual preference questions. Expertise must be evidence-backed and should be conservative; ordinary confident roleplay prose is not proof of expertise.

## 6.4 Topic Stance / Opinion

Track whether a Character has a recurring positive, negative, mixed, or uncertain stance toward a topic when supported by evidence.

```text
Character ─ HAS_STANCE → AI Art
  stance = skeptical
  confidence = 0.73
```

Stance is not the same as interest. A Character may be highly interested in a topic specifically because they disagree with it.

Character Card explicit preferences override learned stance when they conflict.

## 6.5 Relationship State

Support bounded Character↔Character and Character↔Actor social state, for example familiarity, trust, affinity/affection, and friction.

Relationship state must be scoped, evidence-backed, slowly decayed, and never inferred globally from one conversation. It may help answer why a Character naturally joins a message from one speaker but stays silent for the same topic from another speaker.

Relationship inference must not expose private information across Server/Channel/account boundaries.

## 6.6 Conversation Ownership

Represent who currently owns an answer, open conversational thread, or directed question.

Examples:

```text
Question ─ DIRECTED_TO → Ann
Topic ─ CURRENT_OWNER → Ann
OpenLoop ─ AWAITING_RESPONSE_FROM → Ann
```

Conversation ownership is short-lived and should strongly discourage unrelated Characters from interrupting a Character who is currently expected to answer, unless there is explicit multi-character addressing or a justified complement/challenge role.

This state should usually expire in minutes or when the open loop is resolved/topic changes.

## 6.7 Participation Fatigue / Saturation

Add negative feedback so one high-interest Character does not monopolize a topic.

Track bounded recent speaker saturation and topic-specific saturation. High dynamic interest must not produce:

```text
selected more
→ more positive interest evidence
→ selected even more
```

Recent over-participation should reduce reranking support while preserving explicit addressing.

Fatigue is short-lived and decays quickly.

## 6.8 Salience as supporting short-term state

Although not a primary learned trait, retain an optional short-lived salience signal for recently important events/topics. A flood event may temporarily make weather more salient to a Character without permanently increasing their interest in weather.

Salience decays faster than dynamic interest.

## 6.9 Provenance, confidence, negative evidence, and temporal decay

Every learned state must retain enough evidence metadata to explain and rebuild it. At minimum:

- state/relation type;
- Character and target concept/actor;
- value/affinity/stance;
- confidence;
- positive/negative evidence counts;
- bounded source IDs/types;
- created/updated/last-confirmed timestamps;
- decay/expiry class.

Suggested lifetime classes:

```text
Character Card core        → no decay here; author-owned
Relationship               → slow decay
Dynamic Interest/Expertise → medium or evidence-dependent decay
Stance                     → medium/slow, update on contradictory evidence
Salience                   → fast decay
Conversation Ownership     → minutes / open-loop lifecycle
Participation Fatigue      → fast decay
Burst state                → short-lived
```

Contradictory evidence should reduce confidence or supersede state rather than accumulating incompatible permanent truths.

## 6.10 Shadow-mode evaluation

Before learned state affects reranking, Behavior Notebook should show:

- current V4 candidate order without learned state;
- learned-state shadow order;
- interest/expertise/stance/relationship/ownership/fatigue evidence used;
- whether each signal supported, demoted, or had no effect;
- confidence and age/decay status.

Initial activation rule after shadow validation:

> Learned state may rerank/demote already-eligible candidates, but may not by itself grant eligibility or override explicit audience/hard Character Card constraints.

Exit criteria:

- dynamic interest does not create runaway positive feedback;
- interest and expertise produce observably different behavior on suitable fixtures;
- conversation ownership reduces interruptive replies;
- participation fatigue reduces monopolization without suppressing explicit replies;
- relationship and stance evidence stays scoped/provenanced;
- stale learned state measurably decays/prunes.

# Phase 7 — Media + Topic relationship integration

Connect existing Media Understanding and Topic Memory to the graph without changing media perception policy.

### Media object vs Character epistemic state

Represent shared understanding separately from per-Character perception:

```text
Media object
  SHA-256
  summary
  readable text/OCR when available
  source/reference metadata

Character A ─ PERCEIVED → Media
Character B ─ SKIPPED   → Media
```

If A caused understanding to be computed and B later chooses to inspect the same SHA content, B may reuse cached understanding while gaining its own perception edge only after Runtime says B actually perceived it.

### Graph-assisted historical media recall

Keep current explicit/reply recall and semantic safeguards. Graph adds candidate narrowing:

```text
current topic/burst
→ related historical topic/event
→ linked media
→ semantic rerank
→ bounded media context
```

Graph must not resurrect stale media merely because an old relationship exists. Recency, explicit/reply references, privacy scope, and Media Recall policy remain authoritative inputs.

### Topic evolution

Topic Memory remains lifecycle authority for `active / cooling / closed / archived`. Graph adds relationships among topics/events/media/participants rather than replacing continuation classification.

Exit criteria:

- fewer irrelevant historical-media recalls;
- repeated SHA content avoids unnecessary Media Understanding calls;
- no Character gains knowledge of media it never perceived.

# Phase 8 — Durable social state and final rollout

Move only state that must survive restart/multi-replica operation to a server-side durable source of truth.

Candidates include:

- admitted proactive selections relevant to cooldown/rate limits;
- recent speaker anchor needed by lightweight follow-up;
- burst identity/status if collector recovery requires it;
- active ownership/open-loop state when correctness requires persistence;
- learned-state aggregates/provenance that cannot safely be process-local.

Keep high-frequency ephemeral caches local where correctness does not require durability.

### Final evaluation matrix

Validate at minimum:

- English, Simplified Chinese, Traditional Chinese, mixed Chinese/English, and Malay social turns;
- single-author fragmented bursts and multi-author bursts;
- direct Mention/Reply/name/group address fast paths;
- low-information acknowledgements and rapid topic switches;
- short pronoun/continuation turns such as `真的？然后呢？`;
- competing Character Card semantic profiles;
- dynamic interest vs expertise fixtures;
- positive/negative/mixed stance fixtures;
- Character↔Character and Character↔Actor relationship scope;
- directed questions and conversation ownership;
- high-frequency topic participation/fatigue;
- stale learned-state decay and contradiction updates;
- existing primary/secondary coordination;
- current image attachment behavior;
- link/video Tool-driven inspection;
- repeated media SHA reuse across different Characters;
- historical media recall and stale-media rejection;
- Utility unavailable/malformed/low-confidence behavior;
- restart and multi-replica-safe social accounting;
- Behavior Notebook trace completeness.

### Success metrics

Compare V4 to V3 baseline:

- semantic resolver calls per human message;
- Utility calls per human message;
- p50/p95 selection latency;
- Character Runtime calls per human message;
- user feedback: correct / should speak / should stay silent;
- wrong-speaker rate;
- duplicate/interruptive reply rate;
- speaker concentration / monopolization rate;
- conversation-ownership violation rate;
- learned-state shadow agreement and correction rate;
- stale-media recall rate;
- media-understanding cache reuse;
- Graph/learned-state rows, DB growth, prune/decay cost;
- Railway baseline/peak RAM and CPU under representative bursts.

### Merge policy

The PR stays Draft until intended phases are complete and the final validation matrix is recorded.

Do not merge solely because CI is green. Final merge requires:

1. Python/Web/Discord/Docker CI green;
2. Railway Smoke green;
3. no regression in explicit addressing or Smart Output delivery;
4. measured V3 vs V4 selection/latency evidence;
5. bounded Graph and learned-state storage/cleanup evidence;
6. no Character Card authority or media-epistemic regression;
7. explicit owner approval.

If Graph/learned-state reranking does not show enough measured benefit, the same PR may still ship Turn Collector + pipeline reorder + conversation-aware resolver while leaving those layers shadow-only/disabled. Derived storage must remain removable without breaking authoritative Topic/Media/Runtime records.

## Expected end state

V3 primarily asks:

> Which Character Card is semantically relevant to this message?

V4 should instead answer:

> What is this short conversation burst doing, which topic/event/media/people does it continue, who owns the current conversational obligation, what has each Character repeatedly cared about or demonstrated expertise/opinion/relationship around, who has recently spoken too much, and which already-eligible Character would most naturally take the next turn?

The implementation must achieve that without turning Character Relay into an always-on LLM router or silently rewriting the authored Character.