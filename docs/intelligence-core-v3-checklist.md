# Intelligence Core v3 Implementation Checklist

Branch: `feat/intelligence-core-v3-hard-cutover`
Base: `main@99e20eb247e0dbaadb061aa2152f7b3acb637feb`
Merge policy: **do not merge until explicit user instruction**. When authorized, merge method is squash only.

OpenWiki remains a generated orientation layer for merged baseline. Do not regenerate it to represent this unmerged branch.

## Global drift guards
- [x] Dedicated branch exists.
- [x] OpenWiki/AGENTS workflow reviewed.
- [x] Architecture contract recorded in `docs/intelligence-core-v3-architecture.md`.
- [ ] No migrated consumer falls back to Topic runtime.
- [ ] No new `topic_id` authority dependency.
- [ ] ConversationThread never becomes durable knowledge authority.
- [ ] `unresolved` remains legal for ambiguous structure/entity/social interpretations.
- [ ] Planner-only media knowledge never becomes Character perception implicitly.
- [ ] Raw evidence/provenance survives hard cutover.
- [ ] Final PR remains unmerged until explicit user instruction.

## Phase 0 — Contract + dependency inventory
- [x] Architecture contract.
- [ ] Topic models/repositories/services/config/contracts inventory.
- [ ] `topic_id` DB/API/trace/tool consumer inventory.
- [ ] Segment/SemanticThread producer/consumer inventory.
- [ ] Episode producer/consumer/index inventory.
- [ ] Pending Action/Tool continuation inventory.
- [ ] Memory V2/vNext/Core/Freshness inventory.
- [ ] Graph implementation/projector inventory.
- [ ] Relationship/Impression runtime inventory.
- [ ] Knowledge/RAG/Wiki/internal context inventory.
- [ ] Media planner/runtime/conversation-media inventory.
- [ ] Discovery Topic seed inventory.
- [ ] Participation/Turn Intelligence overlap inventory.
- [ ] Portal Intelligence Topic dependency inventory.
- [ ] Destructive DB migration inventory.
- [ ] Repo-wide final Topic grep gate defined.

Exit: every old authority consumer has a named replacement phase.

## Phase 1 — Conversation Structure v3
### Relations
- [ ] Persist typed Message Relations.
- [ ] Interaction: REPLY_TO, ADDRESSED_TO, ANSWERS, CLARIFIES, REACTS_TO, CONTINUES.
- [ ] Semantic: REFERS_TO, EVALUATES, INSULTS, PRAISES, AGREES_WITH, DISAGREES_WITH, DEPICTS.
- [ ] confidence/source/evidence/status.
- [ ] unresolved/rejected/superseded support.
- [ ] addressee kept separate from semantic target.

### Segment / Thread / Membership
- [ ] Burst remains only a temporal window.
- [ ] Single-message ambiguity may use Utility Judge.
- [ ] Utility use depends on ambiguity, not message count.
- [ ] SemanticThread evolves to ConversationThread.
- [ ] canonical_label + anchor_summary + working_summary.
- [ ] representative segments + participants/entities.
- [ ] Stable anchor is not overwritten by rolling evidence.
- [ ] Add reversible ThreadMembership.
- [ ] belongs_to/context_of/reaction_to/unresolved.
- [ ] reassignment/merge/split/supersede.
- [ ] Direct `segment.semantic_thread_id` stops being permanent truth.

### Resolution
- [ ] reply/address first.
- [ ] immediate interaction continuity.
- [ ] participant continuity.
- [ ] entity/object continuity.
- [ ] media continuity.
- [ ] embedding only candidate retrieval/ranking.
- [ ] top1/top2 ambiguity margin.
- [ ] ambiguous → Utility Judge.
- [ ] uncertain → unresolved.

Golden: T1→T2→T1, ambiguous single follow-up, explicit reply outranks similarity, wrong membership can be revised, merge/split preserve provenance.

## Phase 2 — Episode v3 + Thread Working State + PendingAction
- [ ] Segment(s) → Episode; Burst not Episode identity.
- [ ] Remove Episode Topic authority.
- [ ] source messages/segments/thread/participants/entities/media/key events.
- [ ] cooling/end/inactivity/size checkpoints.
- [ ] ThreadWorkingState for open questions/current object/waiting states.
- [ ] Working State expires/archives; not durable Memory.
- [ ] standalone PendingAction with source message/segment, optional thread, requester, target, tool, intent, state, expiry.
- [ ] Tool continuation uses reply/clarification/intent, not Topic.

Milestone A: Conversation + Episode + Action targeted/integration suites pass.

## Phase 3 — Entity + unified Evidence Graph
- [ ] Canonical/provisional Entity layer + aliases/scope/status.
- [ ] Initial Person/Character/GameCharacter/Game/Project/Organization/Concept/Place/MediaWork types.
- [ ] Unify ConversationGraph + AuthorityGraph semantics.
- [ ] Typed relation/confidence/authority/evidence/validity/status/source-model.
- [ ] Media PERCEIVED/DEPICTS and Segment/Episode relations use unified graph.
- [ ] Association reject/supersede.
- [ ] Episodic entity index becomes derived/read-optimized projection.

## Phase 4 — Belief Store + current-turn revision
- [ ] Unified Belief schema/repository.
- [ ] Core Memory represented as authored high-authority Belief.
- [ ] vNext/V2/freshness consumer consolidation.
- [ ] No Topic-scoped recall authority.
- [ ] Current-turn correction detector + related belief retrieval.
- [ ] reinforce/supersede/dispute/reject/expire/stale.
- [ ] Correction Shield blocks contradicted/superseded fact in same prompt.
- [ ] Character-generated hallucination cannot become factual evidence.
- [ ] Evidence invalidation cascade.

Golden: self-correction same turn; third-party conflict disputed; superseded absent from recall; rejected media identity invalidates dependent belief.

## Phase 5 — Social Intelligence
- [ ] Keep canonical Relationship Prior.
- [ ] Keep directional familiarity/affinity/trust/comfort + baseline/delta/decay.
- [ ] Remove admission-only familiarity increment.
- [ ] Remove LearnedState.relationship authority.
- [ ] SocialEvent from relations/segment/episode/grounding.
- [ ] direct/support/help/insult/teasing/apology/betrayal/praise/conflict.
- [ ] semantic target resolved before durable social effect.
- [ ] Impression version/supersede/provenance.
- [ ] automatic Impression synthesis/update.
- [ ] bot→user and bot→bot Impression.
- [ ] relevant Impression injected into live Character context.

Golden: ambient participation no auto relationship increase; teasing ≠ hostile by default; insult addressee/target ambiguity can be clarified; Impression affects later reply context.

Milestone B: Entity/Evidence/Belief/Social full relevant integration passes.

## Phase 6 — Context Resolver
- [ ] Unified ContextBundle: live, beliefs, episodes, entities, knowledge, wiki, social.
- [ ] sufficiency: sufficient / insufficient_nonblocking / external_lookup_needed / unresolved.
- [ ] absorb useful Knowledge Route/RAG algorithms.
- [ ] remove `topic.search`.
- [ ] no Topic-scoped Memory retrieval.
- [ ] bounded ranking/token budget/source authority.

## Phase 7 — Participation Planner + media epistemic contract
- [ ] Consolidate speaker/admission/segment selection responsibility.
- [ ] planner output includes deployment, admitted, segment, reason, grounding.
- [ ] relationship/behavior/directness/fatigue/ownership/media evidence.
- [ ] grounding = context_only / preview_grounded / content_grounded.
- [ ] content_grounded requires actual media perception.
- [ ] inspect fail/decline → safe downgrade or silence.
- [ ] preview-grounded cannot claim unseen content.
- [ ] planner hidden media dependency handed off epistemically.
- [ ] Character final visible autonomy preserved.

Milestone C: Context + Participation + Media targeted/integration suites pass.

## Phase 8 — Discovery + Wiki rewiring
- [ ] Discovery seeds: recent Entities/Threads/Episodes + Behavior interests + Character priors.
- [ ] Remove Topic Discovery authority.
- [ ] Keep per-deployment source config.
- [ ] Wiki remains projection.
- [ ] Server Wiki becomes Entity/Concept/Project/Event derived knowledge.
- [ ] remove `page_key=topic:*` and `source_topic_ids`.

## Phase 9 — Intelligence UI + observability
- [ ] Conversation Structure: Active Threads, Segments, Relations, Episodes, Resolution Evidence.
- [ ] Thread inspector: label/anchor/working/memberships/messages/entities/reasons/confidence.
- [ ] Belief inspector: active/disputed/superseded/evidence/authority/revisions.
- [ ] Social inspector: Relationship + Impression provenance/revision.
- [ ] Media epistemic trace.
- [ ] Context Resolver trace.
- [ ] Participation decision trace.
- [ ] Legacy Topic UI/audit removed.

## Phase 10 — hard delete + destructive migration + stabilization
- [ ] Delete Topic models/repositories/services/lifecycle/utility/config/tests/UI.
- [ ] Delete Topic consolidation/checkpoints/wiki/listeners/search.
- [ ] Delete Topic graph nodes and Discovery seeds.
- [ ] Physically remove Topic tables/indexes/columns/`topic_id`/`source_topic_ids`.
- [ ] Remove duplicate old Memory/Graph compatibility code after consumers switch.
- [ ] Preserve raw messages/media/useful episodes/authored memory meaning/evidence/social/behavior data.
- [ ] Do not migrate old Topic identity into new Threads.
- [ ] Final repo-wide Topic authority grep passes.
- [ ] Python lint/typecheck/tests pass.
- [ ] Connector TS typecheck/tests pass.
- [ ] Web TS/Vitest/build pass.
- [ ] Migration/storage tests pass.
- [ ] Relevant Docker/runtime smoke pass.
- [ ] Final diff review shows no unrelated scope drift.
- [ ] PR review has no blocking findings.

Milestone D: full release gate green.

## Commit/Test cadence
Small edits do not trigger commits/tests. Commit coherent subsystem slices, runtime authority switches, destructive schema migrations, or completed phases. Run targeted tests after coherent batches; run phase integration tests at phase gates; run full suites at Milestones A/B/C/D.

## Merge gate
- [ ] All implementation phases complete.
- [ ] Milestone D green.
- [ ] PR ready for review/merge.
- [ ] **Explicit user instruction to merge received.**
- [ ] Squash merge to `main` performed only after that instruction.
