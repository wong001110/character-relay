# Intelligence repair scope

Status: **implemented in the working tree; integrated validation passed**

This document records the seven follow-up items identified in the Conversation and Discovery
runtime audit. It is the branch handoff and scope record for this repair batch. Source, schemas,
tests, and the current v3 contract remain authoritative.

## Current execution

Phase 1 is implemented: Conversation and Discovery list contracts expose stable cursor
continuation, and the Portal requests later pages instead of slicing one bounded response.
Phase 2 is implemented conservatively: only already-persisted, same-scope Entity names/aliases
are reused; provisional identity gaps may trigger the existing Discovery preview asynchronously,
while candidates remain non-authoritative until Content Understanding accepts evidence. Phase 3
adds bounded, evidence-backed self-claim extraction and revision idempotency without weakening
the correction shield. Phase 4 carries opaque per-message media references through
Burst/Segment into Episode and Thread Working State without turning planner summaries into
Character perception. Phase 5 is covered by the existing scoped Social Impression contract and
the Bilibili title/cache repair; no new semantic-target authority was added.

The coherent working-tree batch passed the full Python suite, strict mypy, Ruff, Portal tests,
and Discord Connector typecheck/tests. It remains uncommitted because the checkout already had
unrelated dirty changes; the main agent must perform the final diff split/commit decision.

## Scope

| Priority | Workstream | Completion boundary |
| --- | --- | --- |
| P1 | Server-side pagination | **Implemented.** Conversation and Discovery list APIs expose stable cursor continuation; the Portal requests later pages instead of slicing one bounded response locally. |
| P1 | Entity grounding | **Implemented conservatively.** Conversation processing reuses only same-scope persisted Entities; unsupported new-name extraction remains intentionally absent. |
| P1 | Knowledge Gap loop | **Implemented.** An eligible unresolved Gap can trigger existing Discovery, remains unresolved until Content Understanding accepts evidence, and records the transition. |
| P1 | Belief expansion | **Implemented.** Explicit self-correction remains the fast path; conservative self-claim extraction includes evidence, scope, confidence, idempotency, revision, and fail-silent behavior. |
| P1 | Multi-media Conversation provenance | **Implemented within the existing six-descriptor budget.** Multiple attachments/embeds/media descriptors retain message-scoped opaque refs through Segment, Episode, and Thread Working State without collapsing items or promoting planner content to perception. |
| P2 | Social Impression lifecycle | **Contract verified.** Explicit interactions update Relationship State; scoped, revisable Impression projection has provenance and no semantic-target guessing. Rich semantic events remain unresolved until a target is confirmed. |
| P2 | Bilibili production parity | **Implemented/tested bounded parity.** URL-title cache repair, metadata extraction mode, query/result bounds, and failure handling are covered. External live-source acceptance remains a deployment/release check. |

## Non-goals and invariants

- Do not reintroduce Topic authority, Topic fallback, or Topic-driven Discovery.
- Keep `unresolved`, safe silence, and downgrade as valid outcomes when evidence is insufficient.
- Preserve owner, Server, channel/thread, deployment, Character, credential, and relationship scopes.
- Discovery candidates are not knowledge authority. A Gap is resolved only after explicit evidence
  acceptance by the Content Understanding path.
- Planner media descriptors are routing evidence; they do not by themselves establish Character
  perception of unseen media.
- No raw Discord content, credentials, or provider secrets belong in ordinary logs or docs.

## Suggested execution phases

1. Add API cursor contracts and Portal data loaders for Conversation and Discovery.
2. Wire Entity grounding and Knowledge Gap lifecycle into the actual Conversation runtime, with
   idempotent scope tests.
3. Extend Belief extraction/revision conservatively and preserve the current correction shield.
4. Carry multi-media provenance through Burst → Segment → Episode → Context.
5. Complete Social Impression projection and Bilibili parity, then run live acceptance.

## Current Discovery Share trigger

The current implementation has two distinct milestones: `WOULD_SHARE` is a decision record, while
`SHARE` is the post-delivery record. A candidate is eligible for the share path only after a
complete Discovery activity has opened it, selectively inspected its media, and produced a scoped
Episode/Thread or relationship association. The coordinator then requires `would_share=true` and a
resolved Conversation Thread.

- `shadow` and `off` never create a share proposal.
- `review` creates `pending_review`; the Portal Shares tab must approve it before it is queued.
- `auto` requires both the Deployment auto-share policy and the global
  `discovery_auto_share_global_enabled` switch, then queues the proposal subject to daily budget
  and cooldown.
- A background outbox poll performs the actual Discord send after rechecking Deployment status,
  Presence, destination scope, identity/webhook credentials, and the current policy.
- The current Portal `Run browse` action is observation-only because it does not request
  `allow_sharing`; it can produce exposures/decisions but not a share proposal by itself.

Each phase should be implemented as one coherent batch, validated once at its phase gate, and
committed at most once. This scope intentionally does not claim that the stale branch-local
`docs/active-development-plan.md` applies to the current checkout; the active plan must name the
branch before it is used as an execution ledger.
