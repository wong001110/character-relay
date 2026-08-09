# LangGraph Phase 4 — Social Turn Graph

Status: 🚧 implementation validation / ⏸ production pilot deferred

Static integration cleanup is complete; the current validation pass covers strict Python typing,
Social Turn graph regressions, Discord Connector typecheck/tests/build, Docker, and Railway smoke.

## Goal

Move ordered multi-Character execution and bounded Character-to-Character continuation into
Character Relay Core while preserving the existing Smart Participation V3 and Discord transport
authority boundaries.

## What does not move

Smart Participation V3 remains the deterministic admission/scoring layer in the Discord
Connector. Phase 4 does **not** replace it with an LLM supervisor and does not change its
semantic relevance, deterministic profile scoring, explicit reply/alias precedence, group-role
coordination, cooldowns, or maximum initial participant admission.

The existing explicit Interaction Session runtime also remains on its dedicated deterministic
path. Phase 4 covers ordinary Discord social turns and Character continuation only.

## Delivery-delimited architecture

```text
Discord event
→ explicit reply / alias routing
→ Smart Participation V3 deterministic participant plan
→ SocialTurnGraph(current participant)
    → CharacterTurnGraph
    → ContinuationAuthorityNode
       ├─ validated character.invite deployment ref
       ├─ Runtime-resolved Character mention refs
       └─ unique / depth / continuation-budget guards
→ return Discord command + stateless cursor
→ Discord Connector performs the real side effect
→ ContextBuffer records actual delivered Discord message IDs
→ next SocialTurnGraph step
```

The graph intentionally stops at every real Discord delivery boundary. This preserves the
existing ordered-context behavior:

```text
A generates
→ A is actually delivered
→ A's real Discord output is appended to recent context
→ B generates with A visible
```

A monolithic graph invocation that generated A and B before delivery would violate this runtime
semantic and is therefore not used in Phase 4.

## Continuation signals

`CharacterTurnGraphResult` exposes only Runtime-resolved coordination refs:

```text
invite_candidate_deployment_id
mentioned_character_deployment_ids
```

`character.invite` remains a Tool proposal. The Character Turn exposes an invite candidate only
when the existing Runtime validated the proposal and the final accepted Smart Output actually
materialized that Character mention.

Normal Character mention continuation is derived from accepted `SmartMentionPart` deployment
refs. Social Turn never reparses natural-language Character names from generated prose.

## Continuation authority

The Social Turn cursor tracks only privacy-safe coordination data:

```text
pending deployment refs
completed deployment refs
origin: selected | invite | mention
continuation depth
continuation budget remaining
step index
```

For a continuation candidate to enter the queue it must:

- exist in the Connector-supplied Runtime-eligible deployment allowlist;
- not already be completed;
- not already be pending;
- fit the maximum continuation depth;
- fit the remaining response budget.

Validated Tool invites are considered before ordinary Character mentions. Dynamically inserted
continuations run before the remaining initially selected participants, matching the existing
recursive continuation behavior while keeping every Character unique within one social turn.

Bot-authored continuation defensively ignores `character.invite` signals even if a malformed or
test double attempts to provide one. The existing ToolRuntime already rejects such proposals;
this is a second orchestration-layer guard.

## State and durability

Phase 4 does not add a graph checkpointer or a new business table. The continuation cursor is
stateless and returned to the Connector between delivery steps. Raw Discord messages, prompts,
RAG excerpts, Provider payloads, Tool arguments/results, credentials, and final reply text are
not stored in graph state.

Durable resume, operation IDs, replay, and cross-process idempotency belong to Phase 5.

## Rollout

The Core adds its current cumulative rollout mode to the deployment snapshot:

```text
orchestration_mode
```

The Discord Connector therefore needs no additional environment variable. Only:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=social_turn
```

activates the Phase 4 social loop. Earlier modes keep the previous social orchestration.

Production remains on:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=condition_watch
```

until the combined Phase 3 + Phase 4 live verification session.

Recommended later verification order:

```text
condition_watch
→ character_turn   # isolate Phase 3 first
→ social_turn      # then add Phase 4
```

Rollback from the combined pilot remains one environment-value change.

## Implementation exit gate

- Smart Participation V3 initial selection behavior remains unchanged;
- explicit reply/alias selection stays above semantic participation;
- initial participant order is preserved across delivery-delimited graph steps;
- Character B receives context only after Character A is actually delivered;
- validated `character.invite` can expand the turn without bypassing Runtime authority;
- accepted Character mention refs can expand the turn without natural-language reparsing;
- duplicate Character turns are blocked;
- depth and continuation-response budgets are enforced;
- bot-authored continuation cannot recursively use `character.invite`;
- graph trace remains privacy-safe;
- `off`, `condition_watch`, and `character_turn` retain the earlier social path;
- only `social_turn` activates the new Social Turn endpoint/Connector loop;
- Python 3.12/3.13 Ruff, strict mypy and pytest pass;
- Web, Discord Connector and Docker regressions pass;
- Railway smoke passes.
