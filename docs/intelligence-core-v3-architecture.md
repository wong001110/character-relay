# Intelligence Core v3 Architecture Contract

Status: **canonical architecture contract**

This document is the canonical architecture contract for Intelligence Core v3. Repository source, schemas, migrations, and tests remain authoritative for implemented details; OpenWiki is derived navigation/context.

## Goal

The ordinary Character-turn path is intentionally small:

```text
Raw Evidence
    ↓
Conversation Structure
    ↓
Participation Planner (speaker + Segment)
    ↓
Focused Context Resolver
    ↓
Character / Tool Runtime
```

Durable interpretation and recall remain separate from that hot path:

```text
Raw Evidence → Episode / Entity / Belief / Social State
                           ↓
          Runtime-owned on-demand read tools
 memory.search / conversation.search / knowledge.search
                           ↓
                 Character when needed
```

Derived/behavioral loops remain separate:

```text
Behavior State → Discovery
Belief / Entity / Knowledge Evidence → derived Projection Layer
Media Observation → Entity Association
External Search → turn-local evidence
```

## Non-negotiable authority rules

1. Raw messages, raw media references, completed Tool results, and external source results are provenance evidence.
2. Conversation Thread is a short/medium-lived conversation track, not durable knowledge and not a replacement Topic authority.
3. Episode answers “what happened”; it is a durable projection over raw evidence and conversation structure.
4. Belief answers “what is currently believed”; beliefs are revisable, disputable, supersedable, and evidence-backed.
5. Projections are derived readable caches. Projection text never outranks its source evidence.
6. Evidence Graph records typed relations and provenance; it must not become an independent duplicate truth store.
7. Relationship and Impression belong to Social Intelligence, not factual Memory.
8. Behavior State contains decaying behavioral signals such as interest, salience, expertise, stance, conversation ownership, and participation fatigue. It does not own Relationship truth.
9. Web/Image Search is for current-turn epistemic need. Deployment Discovery remains autonomous curiosity/content discovery.
10. Media Observation is objective perception. Entity identity/association is a separate revisable relation.
11. Planner-only hidden media information may route a turn, but cannot silently become Character perception.
12. `unresolved` is a valid result. The runtime must not force a low-confidence identity, relation, thread membership, or social target.
13. Relationship closeness is style context, not speaker-admission authority.
14. A proactive Smart Participation nomination is permission to consider speaking, not an obligation to produce a visible message.
15. The Segment selected for a turn is the authority for downstream visible conversation focus; unrelated simultaneous Burst discussion must not leak in through a second context path.

## Explicitly forbidden reintroductions

The implementation must not reintroduce any of these as authority or compatibility fallback:

- `ACTIVE_TOPIC`
- Topic runtime fallback
- Topic compatibility UI
- `topic.search`
- Topic lifecycle authority
- `topic_id` as Memory/Episode/RAG/Tool continuation authority
- `topic_local` durable Memory
- Topic Wiki page identity
- Topic-driven Discovery authority
- Topic-contained Pending Action state
- Topic-driven Episode formation

A temporary source file/table may remain while downstream consumers are being switched, but once a consumer is migrated it must not use the old Topic path as fallback. This is implementation sequencing, not shadow mode.

## Conversation Structure v3

### Message Relations

Message relation semantics are split into two categories.

Interaction relations answer “who/what is this message interacting with?”

- `REPLY_TO`
- `ADDRESSED_TO`
- `ANSWERS`
- `CLARIFIES`
- `REACTS_TO`
- `CONTINUES`

Semantic relations answer “who/what is the content actually about?”

- `REFERS_TO`
- `EVALUATES`
- `INSULTS`
- `PRAISES`
- `AGREES_WITH`
- `DISAGREES_WITH`
- `DEPICTS`

Every persisted inferred relation must carry bounded evidence metadata, source, confidence, and status. Supported interpretation states must include resolved/unresolved/rejected/superseded semantics where applicable.

Address target and semantic target must remain distinct. For example, replying to a Character with an insult establishes a strong `ADDRESSED_TO` relation, but the object of the insult may remain unresolved until clarification.

### Segment

A Burst is only a temporal collection window. One Burst can contain several interleaved discussions. Segmentation must preserve explicit reply structure and must not assume one active conversation.

Single-message ambiguity is eligible for Utility judgment. Utility use is determined by ambiguity, not message count.

### ConversationThread

The current Semantic Thread evolves into `ConversationThread` with at least:

```text
ConversationThread
├ canonical_label
├ anchor_summary
├ working_summary
├ representative_segment_ids
├ participants
├ active_entities
├ status
└ last_active_at
```

`anchor_summary` is a stable description of the conversation line. `working_summary` describes current progress and may roll forward. Old discussion history belongs in Episodes rather than accumulating indefinitely inside Thread identity.

### ThreadMembership

Direct `segment.semantic_thread_id` must stop being permanent truth. Persist reversible membership interpretation:

```text
ThreadMembership
├ segment_id
├ thread_id
├ relation
├ confidence
├ source
├ reason
├ version
└ superseded_at
```

Membership relations include `belongs_to`, `context_of`, `reaction_to`, and `unresolved`.

The runtime must support reassignment, merge, split, supersession, and unresolved membership.

### Thread resolution order

Use structure before semantics:

1. explicit reply relation
2. explicit mention/address target
3. immediate interaction continuity
4. participant continuity
5. entity/object continuity
6. media/context continuity
7. semantic similarity for candidate retrieval/ranking only
8. top-1 vs top-2 margin
9. ambiguous → Utility Judge
10. still uncertain → unresolved

Embedding is candidate retrieval/ranking evidence, never final authority by itself.

## Episode v3

Episode formation must follow Segments, not raw Burst identity and not Topic lifecycle.

```text
Episode
├ source_message_ids
├ segment_ids
├ conversation_thread_id
├ participants
├ entity_refs
├ media_refs
├ summary
├ key_events
├ started_at
└ ended_at
```

Episode formation may be triggered by thread cooling, explicit event end, inactivity, or size checkpoint. Raw messages remain provenance truth and are never rewritten when later interpretation changes.

Episodes are not automatically inserted into every Character prompt. When older conversational history is actually needed, the Runtime-owned `conversation.search` read tool performs scoped recall and applies the existing perception contract.

## Thread Working State

Transient conversational state such as unresolved questions, pending upload references, current media objects, or short-lived intentions belongs in `ThreadWorkingState`. It is not durable Belief/Memory and expires or archives with the conversation line.

Active, unexpired Thread Working State may enter focused turn context because it describes the currently selected conversation line rather than broad historical recall.

## Pending Action

Pending Tool state is standalone:

```text
PendingAction
├ source_message_id
├ source_segment_id
├ conversation_thread_id
├ requested_by
├ target_character
├ tool_id
├ intent_summary
├ state
└ expires_at
```

Continuation uses reply/clarification relations, source message/segment, current conversation structure, and semantic intent. Topic continuity is not required.

## Entity and Evidence Graph

Create/upgrade a canonical Entity layer supporting provisional identities. Initial entity classes include Person, Character, GameCharacter, Game, Project, Organization, Concept, Place, and MediaWork.

Unify the current Conversation Graph and Conversation Authority Graph into one Evidence Graph abstraction. Nodes can reference Message, Media, Segment, Thread, Episode, Entity, Belief, Character, KnowledgeDocument, and ExternalSource. Edges hold typed relation, confidence, authority class, evidence references, validity/expiry, status, and producing model/source where relevant.

The existing episodic SQL entity index remains a read-optimized derived index rather than a separate truth store.

## Belief Store

Unify overlapping Core Memory, Conversation Memory V2, Memory vNext, freshness, and revision semantics into an evidence-backed Belief model.

```text
Belief
├ subject_entity
├ predicate/type
├ value/content
├ scope
├ authority
├ origin
├ confidence
├ importance
├ status
├ supersedes_id
├ evidence_refs
├ valid_from
├ valid_to
├ last_confirmed_at
└ stale_after
```

Author/Core Memory becomes high-authority authored Belief rather than a separate retrieval universe. Conversation-derived beliefs use lower authority based on evidence class.

Beliefs are not bulk-scanned into ordinary Character turns. The Runtime-owned `memory.search` read tool performs scoped, current-status recall when the model actually needs durable remembered information.

### Current-turn belief revision

Explicit correction/contradiction handling must run before final Character reply for a selected Character:

```text
Incoming selected turn
→ Correction/Contradiction Detector
→ related Belief revision path
→ support / contradict / correct / unrelated
→ revision
→ Correction Shield
→ Character reply
```

Explicit self-correction can supersede lower-authority claims immediately. Third-party conflicts can become `disputed`. Superseded/rejected beliefs must not be injected as current facts. Character-generated hallucinated prose must not be reused as factual evidence.

Belief authority is domain-sensitive; personal self-report rules do not automatically apply to game canon or external factual domains.

Evidence dependency invalidation must support cascade revision. If an image-to-entity association is rejected, beliefs whose only support depended on that association must be re-evaluated.

Correction extraction/revision is not a reason to admit every Smart Participation candidate. Planning selects the Character first; Character-specific correction work is then performed only for selected participants.

## Media epistemic contract

Keep objective Media Understanding separate from semantic identity association.

Participation planning must distinguish reply grounding:

- `context_only`: response does not rely on shared media content.
- `preview_grounded`: response may use only genuinely visible metadata such as sender text, title/provider, and visible preview information. It may not extrapolate unseen content.
- `content_grounded`: response requires actual perceived media content.

For `content_grounded`, Runtime must obtain reliable perception (`media.inspect` or required-media resolution) before final reply. If perception fails or the Character declines inspection, the plan must downgrade safely to preview/context grounding or become silent.

If planner-only media analysis influenced admission, the epistemic dependency must be handed off before Character generation. Hidden planner knowledge is not Character knowledge.

Media identity relations such as `Media DEPICTS Entity` are evidence graph interpretations and may be rejected/superseded.

## Context Resolver

The Context Resolver is a focused turn-context assembler, not a mandatory pre-generation RAG pipeline.

For ordinary Character turns it receives the already selected Character + Segment + Thread and returns a bounded ContextBundle containing only immediate context that is justified on every turn:

- raw visible messages belonging to the selected Segment (or a bounded Segment summary fallback),
- the selected Conversation Thread and active Thread Working State,
- current-turn Correction Shield,
- relevant standalone Pending Action state,
- server-time context,
- lightweight subjective social tone context,
- explicitly supplied evidence from a specialized caller, if any.

It does **not** automatically scan and inject Beliefs, Episodes, Entities, Knowledge Fabric results, or Knowledge Gaps on every ordinary reply. Durable recall is available on demand through Runtime-owned read tools:

- `memory.search` — scoped current Belief recall,
- `conversation.search` — scoped perceived Episode/history recall,
- `knowledge.search` — epistemically admitted Knowledge Fabric evidence.

These internal tools are visible to the Character Runtime without becoming Deployment-granted side-effect authority. The selected visible conversation remains primary context; the model should call a recall tool only when older information is actually necessary.

Sufficiency states remain part of the compatibility contract:

- `sufficient`
- `insufficient_nonblocking`
- `external_lookup_needed`
- `unresolved`

Ordinary focused context normally resolves to `sufficient`, `insufficient_nonblocking`, or `unresolved`; `external_lookup_needed` is reserved for an explicit specialized path rather than being inferred from an automatically scanned Knowledge Gap.

`topic.search` and Topic-scoped Memory retrieval remain forbidden.

## Social Intelligence

Keep the dedicated Social Model and its evidence/provenance, but separate stored detail from provider-visible chat behavior.

### Canonical Relationship

Author-controlled Character Relationship Prior is immutable to ordinary chat. Canonical relationship identity cannot be changed by lived state.

### Lived Relationship State

Directional familiarity, affinity, trust, and comfort may remain internally persisted with baseline + delta + decay for compatibility, evidence history, and future analysis. Support Character→user (`actor`) and Character→Character (`deployment`).

Ordinary Character prompts must **not** expose the multidimensional score model as a decision system. Project it to a coarse relationship tier:

- `stranger`
- `acquaintance`
- `familiar`
- `close`

and at most a few bounded tone hints such as warm, reserved, relaxed, measured, or cautious.

Relationship state must not increase Smart Participation admission probability, select a Segment, create factual Memory, or obligate a reply. It only influences style after participation has independently been justified.

Do not update Relationship merely because Smart Participation nominated or admitted a Character. Actual interpreted Social Events provide evidence.

### SocialEvent

Derive meaningful social events from Message Relations, Segment/Episode context, Interaction Grounding, and (when needed) bounded Utility judgment. Examples include direct interaction, support/help, insult, teasing, apology, betrayal, praise, and conflict.

Address target and semantic target must be resolved separately before durable social effects are written.

### Impression

Person Impression remains directional subjective interpretation, not factual Belief. Keep version/supersession/provenance semantics. Ordinary live context may include at most a short high-confidence subjective impression, explicitly labeled as subjective tone context rather than canon.

Remove the legacy scalar `CharacterLearnedState.relationship`; Relationship truth belongs only to Social Intelligence.

## Behavior State

Retain decaying behavioral signals such as interest, expertise, stance, salience, conversation ownership, and participation fatigue. Conceptually treat the current Learned State as Character Behavior State after removing relationship authority.

## Participation Planner

The bounded Participation Planner decides which eligible Character may participate and which Segment is targeted before Character-specific context recall.

Admission evidence may include:

- direct address / explicit mention,
- immediate conversational continuation,
- strong semantic relevance between the Character profile and the candidate Segment,
- bounded behavior/conversation-ownership signals,
- participation fatigue,
- media dependency and epistemic grounding.

Relationship closeness and Impression are **not** participation evidence.

For proactive participation, the mere existence of an active discussion is insufficient. The planner requires actual Segment relevance rather than a generic baseline score. Direct-address/continuation evidence may select the current Segment even without a strong semantic profile match.

Planner admission remains a nomination. Smart Output may still choose `ignore` for a proactive candidate when the final visible context is unclear, already adequately answered, off-topic, or does not warrant a useful contribution. Explicit mention/reply and an active interaction session retain their visible-response obligation.

The Segment chosen by the planner must be reused by downstream context resolution. A second independent “current segment” calculation must not silently switch the model to another simultaneous discussion.

Character final visible behavior remains controlled by the Character runtime/model within deterministic safety/runtime authority.

## Discovery and external search

Deployment Discovery remains autonomous curiosity/content discovery. It is not a fallback for current-turn factual lookup. Rewire Discovery seeds away from Topic and toward recent Entities, Threads, Episodes, Behavior State interests, and Character definition priors.

Existing Web/Image Search tools serve current-turn epistemic need when they are assigned/available and the Character determines that fresh external evidence is actually required. Ordinary Context Resolver construction does not need to pre-classify every turn as an external lookup before the model can use an authorized read tool.

## Projection Layer and Wiki compatibility

Fabric Projections are materialized readable caches with explicit SourceVersion/Evidence dependencies, source hashes, and stale invalidation. Preserve the rule that raw Knowledge documents remain authority for any derived view. The Character-facing internal tool is `knowledge.search` through the fail-closed Fabric Context boundary; it never uses Server Wiki lookup. Phase 11c directly retired the old Wiki tables/API/Portal surfaces with no migration or archive path. Entity/Concept/Project/Event views, when needed, are Fabric Projections derived from validated evidence rather than Server Wiki pages. Remove `page_key=topic:*` and `source_topic_ids`.

## Hard cutover and old data

No shadow mode, Topic fallback, compatibility UI, or dual runtime.

Preserve useful raw evidence, Episodes where still meaningful, media, authored Memory meaning/evidence, Relationship priors/state/impressions, and Behavior evidence. Do not migrate old Topic identity or Topic-message/Topic-Episode/Topic-Wiki associations into new Threads.

This conversation-core simplification is deliberately non-destructive: existing Belief/Episode/Relationship data remains persisted and queryable. The hot path stops eagerly injecting it; no destructive schema migration is required.

New Conversation Threads begin from the cutover runtime.

## Ongoing change contract

- Keep changes bounded to a coherent subsystem and name the source/test evidence used.
- Run targeted tests after coherent batches and the relevant full validation before handoff.
- Update this contract when authority or architecture changes; implementation detail belongs with source/tests.
- Refresh OpenWiki from updated `main` after accepted architectural work merges.
- Do not restore Topic compatibility or fallback as a shortcut around a v3 consumer.
