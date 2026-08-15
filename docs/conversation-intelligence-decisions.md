# Conversation Intelligence Decision Log

Status: normative design decisions for PR #169

This file records decisions that have been explicitly accepted during architecture review. When this file conflicts with earlier proposal text in `conversation-intelligence-architecture.md`, **this decision log takes precedence** until the proposal is reconciled.

## D-001 — Multi-participant admission replaces Primary/Secondary as the core model

**Status:** Accepted

Character Relay must not model one conversation turn as inherently limited to one Primary plus one Secondary participant.

A turn may legitimately admit:

```text
0 participants
1 participant
2 participants
...
N participants
all eligible participants
```

The architecture must therefore separate:

```text
Candidate Pool
    -> Admission
    -> 0..N admitted participants
    -> Participation Plan
    -> Character generation / social actions
```

`primary` and `secondary` are no longer core admission categories. If a future UI or trace needs to call the first ordered speaker "primary", that is presentation metadata only and must not constrain the participation model.

### Admission is authoritative

A Character that is only a candidate has not been admitted and must not consume Roleplay-model tokens merely to decide whether to participate.

Once a Character is admitted, Runtime has already made the participation decision. The Roleplay LLM must not independently overturn admission by returning voluntary `ignore`.

Therefore:

```text
candidate
= considered / relevant
= no Roleplay call required

admitted
= Runtime has decided the Character participates
= Roleplay call may occur
= the resulting contract must require a visible social action
```

Provider failures, schema failures, Runtime aborts, and voluntary Character silence remain distinct states. None should be disguised as `ignore`.

### Participation Plan fields

The planned core dimensions are:

```text
ref
order
action_class
participation_intent
```

Illustrative contract:

```json
{
  "participants": [
    {
      "ref": "ann",
      "order": 1,
      "action_class": "verbal",
      "participation_intent": "respond"
    },
    {
      "ref": "ning",
      "order": 2,
      "action_class": "lightweight",
      "participation_intent": "react"
    },
    {
      "ref": "zhi",
      "order": 3,
      "action_class": "verbal",
      "participation_intent": "add_perspective"
    }
  ]
}
```

Initial conceptual action classes:

```text
verbal
= produce a message

lightweight
= reaction / sticker / another explicitly permitted lightweight visible action
```

`participation_intent` gives the Roleplay LLM a bounded social direction without writing the line for it. Potential intents include:

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

The final enum remains an implementation-contract question; the architectural decision is that intent is separate from admission.

### All participants may be admitted

There is no architecture-level assumption that only one or two Characters may participate. A deployment/runtime configuration may still impose a safety or cost cap such as `max_participants`, but the data model must support `0..N` and "all eligible".

The planner should avoid selecting everyone by default merely because it can. Admission should still require positive conversational value.

## D-002 — Multi-speaker coordination should be ordered

**Status:** Accepted as working direction

When multiple admitted participants produce verbal output, the plan should include an explicit order.

Preferred execution semantics:

```text
Planner
  -> Character A generates
  -> A's actual visible output becomes part of the current-turn context
  -> Character B generates with A visible
  -> B's output becomes part of context
  -> Character C generates
  -> ...
```

This is intended to reduce repetitive independent answers and enable natural agreement, disagreement, follow-up, jokes, and perspective shifts.

Lightweight actions such as reactions/stickers may be executed in parallel or with looser ordering where they do not depend on prior generated text.

The exact concurrency policy remains open, but **the plan must be capable of expressing order and later participants must be able to observe earlier visible outputs when sequential execution is used.**

## Closed questions from the original proposal

The following original open questions are closed/superseded:

1. "Should authoritative Primary always require message, or may it react/sticker?"
2. "Which actions may a Secondary use, and can Secondary become silent after selection?"

They are replaced by:

- admission vs candidate,
- `0..N` admitted participants,
- per-participant `action_class`,
- per-participant `participation_intent`,
- ordered coordination,
- no voluntary `ignore` after admission.

## Remaining open questions

The following decisions are still unresolved and should be reviewed before the corresponding implementation phases.

### Q-001 — Exact admitted action classes

We have accepted the separation of admission from `action_class`, but the exact contract is not final.

Questions:

- Is `verbal | lightweight` sufficient for v1?
- Should `lightweight` be split into `reaction | sticker | short_message`?
- Can an admitted Character switch from the planner-assigned action class, or must Runtime constrain the schema to that class?

Working preference: keep v1 small and make the planner-assigned class authoritative enough that the Roleplay LLM cannot turn an admitted turn back into silence.

### Q-002 — Multi-speaker concurrency policy

Ordered sequential verbal generation is the working direction, but details remain open:

- Are all verbal participants always sequential?
- Can independent verbal intents be generated in parallel when repetition risk is low?
- Are reactions/stickers always allowed to execute in parallel?
- What latency budget should cause Runtime to stop or defer later admitted participants?

### Q-003 — Maximum admitted participant policy

The architecture supports `0..N`, but Runtime/product policy still needs a configurable default:

- fixed numeric cap,
- server/channel setting,
- dynamic cap based on conversation intensity,
- or effectively unlimited/all eligible with planner cost-awareness.

This is a policy/cost control, not a data-model limit.

### Q-004 — Media-only turns before speaker selection

Should unresolved media be objectively understood before admission/speaker planning:

- always when media is the only semantic payload,
- only when text/preview evidence is insufficient,
- or through a two-stage lightweight-then-full media resolution?

Working preference: two-stage resolution. Obtain enough objective evidence for Topic/admission planning first; perform full resolution only when the answer requires deeper content.

### Q-005 — Media Dependency ownership

For `required | optional | none`:

- deterministic Runtime rules only,
- Utility Intelligence every time,
- or deterministic-first with Utility only for ambiguous cases.

Working preference: deterministic-first + Utility gray-zone. Runtime-locked REQUIRED evidence must not be downgraded by Utility.

### Q-006 — Conversation Plan granularity

Should `conversation_plan` run:

- per Discord message,
- per collected burst/conversational turn,
- or hybrid with bypass paths for explicit mentions/replies/tool continuations?

Working preference: burst/turn as the semantic planning unit, with deterministic bypass paths where waiting for the burst is inappropriate.

### Q-007 — When to merge current Smart Participation V4 into Conversation Planning

Options:

- merge speaker/admission planning into `conversation_plan.v1` immediately,
- keep V4 authoritative initially and run the new planner in shadow/parity mode,
- or keep admission permanently as a separate subsystem.

Working preference: keep V4 authoritative initially, compare parity, then decide whether a later Conversation Plan version should own admission too.

### Q-008 — Memory scope migration

Existing memories may be channel/thread scoped even when the information is actually relationship-level or Character-level.

Options:

- hard migration,
- legacy memories stay where they are and only new memories use new scopes,
- lazy semantic promotion + background consolidation.

Working preference: lazy semantic migration. Preserve original provenance; promote only when the memory type/evidence justifies a wider scope.

### Q-009 — Episode storage model

Options:

- treat raw messages as Episodes,
- create a fully separate duplicated Episode store,
- create an Episode projection that references authoritative source message IDs/bursts.

Working preference: Episode projection. Raw messages remain authoritative; Episodes organize them into meaningful retrievable experiences.

### Q-010 — Roleplay-driven Internal Tool budget

The planner/runtime should prefetch most required context, but the Character may use Internal Context Tools as an escape hatch.

Need to decide:

- maximum rounds,
- batching contract,
- exceptional modes that may permit more rounds.

Working preference: one Internal Tool round by default, with batched queries; allow more only in explicitly deeper recall/research modes.

### Q-011 — Wiki visibility/privacy boundaries

Need to decide exactly which Memory/Episode scopes may feed which Wiki scopes.

Working principle already accepted:

> Derived knowledge must not automatically become more visible than its source evidence.

Still unresolved:

- exact Wiki scope types,
- cross-character shared knowledge rules,
- promotion/authorization mechanism from private/relationship knowledge to wider shared knowledge.

### Q-012 — Graph authority classes

Need to define which edges are:

- durable provenance/structural facts,
- temporal interpreted facts with validity/source,
- rebuildable semantic/index edges.

Working preference: raw Episode/source remains provenance truth; Graph is structured interpretation/index and must not silently become the only truth store.

### Q-013 — Background consolidation triggers

Options:

- time-based,
- message-count threshold,
- Topic cooling/closing,
- hybrid.

Working preference: hybrid, primarily event-driven by Topic cooling/closing, plus message-count safeguards and periodic maintenance sweeps.

## Current accepted high-level flow

```text
Incoming burst
   -> deterministic candidate/evidence preflight
   -> Utility Conversation Intelligence where semantic judgment is needed
   -> Runtime validation
   -> Candidate Pool
   -> Admission: 0..N
   -> Ordered Participation Plan
   -> required context/media retrieval
   -> Roleplay generation for admitted Characters
   -> Runtime authorization / Discord execution
   -> post-turn consolidation
```

Structured, versioned contracts remain mandatory throughout this flow. LLMs select semantic options from supplied candidates; Runtime owns identity, scope, authority, validation, provenance, lifecycle, and side effects.
