# Conversation Intelligence Decision Log

Status: **historical decision log for PR #169**

> These decisions explain the pre-v3 design process. Intelligence Core v3 supersedes them wherever they rely on Topic authority, Topic-scoped Memory/Wiki/Discovery, or a shadow/parity migration that the hard cutover removed. Use `docs/intelligence-core-v3-architecture.md` for current authority.

This file records architecture decisions explicitly accepted during review. When it conflicts with earlier proposal text in `conversation-intelligence-architecture.md`, **this decision log takes precedence** until the proposal is reconciled.

## D-001 — Multi-participant admission replaces Primary/Secondary

**Status:** Accepted

A conversation turn is not limited to one Primary plus one Secondary Character.

The core model is:

```text
Candidate Pool
    -> Admission
    -> 0..N admitted participants
    -> Ordered Participation Plan
    -> Character generation / visible social actions
```

A turn may admit zero, one, many, or all eligible Characters. `primary` / `secondary` may remain as presentation or trace labels in legacy code, but they are not architecture-level admission categories.

A candidate is only considered. It must not consume Roleplay-model tokens merely to decide whether to participate.

Once admitted, Runtime has already decided that the Character participates. The Roleplay LLM may not overturn admission with voluntary `ignore`.

Provider failure, schema failure, Runtime abort, not-selected, and voluntary silence are separate states and must not be disguised as `ignore`.

---

## D-002 — Participation actions use detailed action classes

**Status:** Accepted

Do not collapse admitted behavior into only `verbal | lightweight`.

The v1 planning contract should use more explicit action classes. Initial accepted direction:

```text
message
short_message
reaction
sticker
```

The exact payload schema for each class may evolve, but the planner-assigned class must constrain the Roleplay output schema for that turn.

Examples:

```text
action_class=message
-> normal text message is required

action_class=short_message
-> bounded short text response

action_class=reaction
-> reaction-only contract

action_class=sticker
-> sticker-only contract
```

An admitted Character must produce a visible action compatible with its assigned class. It may not change the class into silence.

`participation_intent` remains separate from `action_class`. The planner may use a bounded intent enum such as:

```text
respond
add_perspective
agree
disagree
challenge
joke
support
react
clarify
```

The intent guides persona behavior without writing the line for the Character.

---

## D-003 — Multi-speaker verbal execution is sequential

**Status:** Accepted

When multiple admitted Characters produce text, execute them sequentially in the plan order.

```text
Planner
  -> Character A generates
  -> A's actual visible output enters current-turn context
  -> Character B generates with A visible
  -> B's output enters context
  -> Character C generates
  -> ...
```

This is intended to reduce duplicate answers and allow natural follow-up, disagreement, jokes, support, and perspective shifts.

Reaction/sticker delivery may remain operationally lightweight, but the architecture should preserve the participation order and must not rely on parallel text generation as the default.

---

## D-004 — Participant count is not hard-coded into the architecture

**Status:** Accepted

The data model supports `0..N` admitted participants and all eligible Characters.

A Runtime/product safety or cost cap may exist and may be configurable or dynamically adjusted, but it is not a structural limit such as "maximum two speakers".

The planner should still require positive conversational value rather than selecting everyone by default.

---

## D-005 — Media-only turns use two-stage objective resolution before admission when needed

**Status:** Accepted

When media is the only meaningful semantic payload, Character Relay should obtain enough objective understanding before Topic/admission planning so that models do not blindly attach themselves to unknown content.

Use a two-stage model:

```text
unresolved media-only turn
    -> lightweight objective resolution
    -> enough evidence for Topic + Admission + dependency planning
    -> only if deeper content is required:
       full media resolution
```

The lightweight stage should not automatically perform the maximum-cost analysis of every long video. It should obtain enough trustworthy content evidence to avoid blind Topic and speaker decisions.

Discord preview metadata remains preview evidence, not equivalent to inspected content.

---

## D-006 — Media Dependency is deterministic-first with Utility gray-zone judgment

**Status:** Accepted

Use:

```text
required | optional | none
```

Decision ownership:

```text
clear deterministic case
-> Runtime decides

ambiguous semantic case
-> Utility Intelligence decides from a bounded structured contract
```

Examples of obvious REQUIRED cases include requests whose answer depends on unseen media contents.

A Runtime-locked REQUIRED dependency cannot be downgraded by Utility.

For REQUIRED media, Runtime owns the resolution before the final Character response. OPTIONAL media may remain Character-driven through `media.inspect`.

---

## D-007 — Conversation planning is burst/turn based with bypass paths

**Status:** Accepted

The semantic planning unit is a collected conversation burst / conversational turn, not necessarily one Discord message.

This allows sequences such as:

```text
A: 你还记得之前那个吗
B: 绝区零那个？
A: 对，就是那个反派
```

to be planned as one coherent unit.

Deterministic bypass paths should remain for cases where waiting for the normal burst is inappropriate, including explicit mentions/replies, interaction/tool continuations, and other already-authoritative direct routes.

---

## D-008 — Keep Smart Participation V4 authoritative first; introduce planner by shadow/parity

**Status:** Accepted

Do not immediately replace the current production admission path.

Implementation direction:

```text
existing Smart Participation V4
-> remains authoritative initially

new Conversation Planner
-> runs in shadow/parity mode
-> compare admission decisions and traces
-> prove acceptable parity/quality
-> only then decide/implement ownership transfer into a later plan contract
```

The long-term architecture may consolidate admission into Conversation Planning, but the migration must be staged rather than a one-shot rewrite.

---

## D-009 — Do not migrate existing Memory; delete dirty legacy data and restart on the new model

**Status:** Accepted

Existing Memory data is considered dirty/test-era data and should not be semantically promoted or migrated into the new scope model.

When the new Memory schema/runtime is ready:

```text
legacy Memory data
-> remove/reset

new Memory system
-> starts clean
-> accumulates only under the new scope/provenance rules
```

This is intentionally different from lazy migration.

The cleanup must be scoped to obsolete conversation-memory data only; authoritative raw conversation/source records must not be deleted merely because derived Memory is reset.

---

## D-010 — Episode is a projection over authoritative source messages

**Status:** Accepted

Do not make every raw message itself the Episode, and do not duplicate the full transcript into a second authoritative store.

Use an Episode projection that references source records:

```text
Episode
├─ episode_id
├─ source_message_ids / burst refs
├─ topic_id
├─ participants
├─ media_refs
├─ started_at / ended_at
├─ compact derived summary
└─ provenance
```

Raw messages remain authoritative evidence. Episodes organize raw events into meaningful retrievable experiences.

Topic, Memory, Wiki, and Graph may cite/project from Episodes while provenance still leads back to raw sources.

---

## D-011 — Roleplay-driven Internal Tool retrieval gets one round by default

**Status:** Accepted

Planner/Runtime prefetch should satisfy most context needs before the Roleplay call.

The Character keeps Internal Context Tools as a bounded escape hatch.

Default:

```text
max_internal_tool_rounds = 1
```

Internal read tools should support batched queries so several related retrieval requests can be issued within that one round.

Explicit deeper recall/research modes may later allow an increased budget such as two rounds, but ordinary group chat should not repeatedly loop through Roleplay-model tool calls.

---

## D-012 — Wiki visibility may stay the same or become narrower, never automatically wider

**Status:** Accepted

Derived knowledge must not automatically become more visible than its source evidence.

```text
source scope
-> same Wiki scope: allowed
-> narrower Wiki scope: allowed
-> wider Wiki scope: not automatic
```

Private/relationship/Character-scoped evidence must not silently become server/shared Wiki knowledge.

Any future promotion to a wider visibility boundary requires a separate explicit authorization/evidence rule.

---

## D-013 — Graph has authority classes; raw Episode/source remains provenance truth

**Status:** Accepted

Graph edges must be classified rather than treated uniformly.

### Durable provenance / structural edges

Examples:

```text
message AUTHORED_BY user
message REPLY_TO message
episode CONTAINS message
topic CONTAINS episode
media ATTACHED_TO message
memory DERIVED_FROM episode
```

These represent provenance/structure and may be durable.

### Temporal interpreted facts

Examples:

```text
user LIKES entity
character BELIEVES fact
relationship HAS_STATE value
```

These require source provenance, confidence, and temporal validity such as `valid_from` / `valid_to` where appropriate.

### Rebuildable semantic/index edges

Examples:

```text
topic RELATED_TO topic
entity SEMANTICALLY_CLOSE entity
user ASSOCIATED_WITH topic
```

These are derived indexes and may be recomputed.

The Graph is structured interpretation/indexing. It must not silently become the only truth store. Raw source/Episode provenance remains authoritative.

---

## D-014 — Background consolidation uses a Hybrid trigger model

**Status:** Accepted

Use event-driven consolidation first, periodic safety nets second.

Primary triggers:

```text
Topic cooling
Topic closing
```

Safeguards:

```text
message-count / size threshold
-> prevent extremely long active Topics from never consolidating

periodic maintenance sweep
-> retry failures
-> process backlog
-> refresh stale derived knowledge
-> catch missed triggers
```

Not every consolidation task belongs on the critical Roleplay response path.

---

## D-015 — Structured contracts and Runtime authority remain mandatory across all decisions

**Status:** Accepted

All Utility/Roleplay planning surfaces use fixed versioned structured input/output.

LLMs select semantic options from supplied candidates. They do not invent IDs, scopes, permissions, lifecycle state, or arbitrary actions.

Runtime validates even schema-valid LLM output and owns identity, scope, authority, provenance, lifecycle, security, and side effects.

Internal Context Tools and External Capability Tools remain separate categories. Runtime-required operations are not optional Character tools.

---

## Current accepted high-level flow

```text
Incoming Discord burst / direct bypass
   -> deterministic candidate + evidence preflight
   -> lightweight media resolution when media is the only semantic payload
   -> Utility Conversation Intelligence only where semantic judgment is needed
   -> Runtime validates structured decisions
   -> Candidate Pool
   -> Admission: 0..N
   -> Detailed Ordered Participation Plan
      - order
      - action_class
      - participation_intent
   -> required context / full REQUIRED media retrieval
   -> sequential Roleplay generation for admitted text participants
   -> optional single-round batched Internal Tool escape hatch
   -> Runtime authorization / Discord execution
   -> post-turn Episode / Topic / Memory / Wiki / Graph consolidation
```

---

## Remaining implementation details — not architecture blockers

The major architecture questions in the previous decision log are now resolved. The following are lower-level contract/tuning details to settle during implementation design:

1. Final exact enum names and payload limits for `message`, `short_message`, `reaction`, and `sticker`.
2. Final bounded `participation_intent` enum.
3. Product/config surface for dynamic `max_participants` and any latency/cost guardrails.
4. Exact lightweight media-resolution evidence budget and escalation thresholds.
5. Shadow/parity acceptance metrics before Conversation Planner can replace Smart Participation V4 authority.
6. Exact new Memory scope taxonomy and the safe cleanup procedure for obsolete derived Memory rows.
7. Episode projection storage schema and retention policy.
8. Internal Tool batch schema and criteria for enabling exceptional deeper-recall modes.
9. Exact Wiki scope names and any future explicit wider-scope promotion mechanism.
10. Concrete Graph edge schemas and temporal-validity representation.
11. Consolidation queue thresholds, retry policy, and maintenance cadence.

These are implementation-contract/tuning questions; they no longer change the accepted architecture above.
