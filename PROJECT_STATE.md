# Project state

Updated: **2026-10-01**. This is the only current progress and takeover record.

## Current scope and authority

| Item | State |
| --- | --- |
| Repository / baseline | `wong001110/character-relay` / `2812d79b314b25aa31fe0632dcbdd7da205b0bf0` (merged PR #207) |
| Active direction | [Lightweight Room Director refactor](docs/plans/discord-group-chat-core.md) |
| Current instruction | Write direction first, then develop in execution mode by coherent phases using external Agent Continuity |
| Development branch | `refactor/lightweight-room-director` (created from verified main) |
| Merge / production deploy | Not authorized by this assignment |
| Old application data | May be discarded in a controlled future cutover; do not maintain compatibility for its own sake |
| Character cards | Prefer portable authored-content preservation; old schema must not block the refactor |
| Full refactor | **INCOMPLETE**; accepted target is not current production behavior |

## Baseline correction

Only Git-backed source is implementation evidence. PR #207 delivered foundation/P2a provenance,
room-buffer and partial/uncertain delivery protections, not the lost unpushed P3-P6 work. Historical
logs for that missing code cannot be attributed to main or this branch. The prior checkpoint and
receipts remain in [the merge review](docs/reviews/group-chat-checkpoint-2026-09-22.md) and Git history.

At this direction commit the existing Planner, semantic participation/structure, numerical social
state, character-internal Turn Director, ordinary automatic writers and Roast remain present.
No runtime/dependency/schema changes or data deletion are part of the direction commit.

## Refactor progress

R0-R6 are the new initiative's checkpoints; they are not old P0-P6 completion claims.

| Phase | Status / evidence |
| --- | --- |
| R0 | Direction written: responsibility split, replacement/data/card policy, phases and A01-A29 acceptance. Documentation source/link/coverage self-review; runtime unchanged. |
| R1 | NEXT: build offline rules/Planner/Director replay spike and metrics; no fabricated model-quality baseline. |
| R2 | NOT STARTED: focused source/direct routing and transport/job integration. |
| R3 | NOT STARTED: evaluated Room Director production replacement, bounded continuation and freshness. |
| R4 | NOT STARTED: explicit notes/history, relationships, retrieval and expressions. |
| R5 | NOT STARTED: Portal/observation and actual retired-consumer cleanup. |
| R6 | NOT STARTED: complete integration/deletion audit, isolated card/reset rehearsal and release preparation. |

## Environment and evidence boundaries

- Railway plugin read calls succeed. Character Relay has `character-relay`, `discord-connector`
  and `pgvector` services in production. Both application services follow `main`; no Railway
  configuration, deployment, database or secret values were changed/read in this inspection.
- Agent Continuity v0.4.0 was read from the user's Library. Assignment state/evidence stays outside
  the checkout; no project continuity infrastructure is added. Self-review is not independent review.
- The execution sandbox cannot directly resolve GitHub for clone. Connected GitHub tools can read
  and commit source. Source acquisition/verification limitations must be recorded, not disguised as
  a complete local checkout or a passed integration run.
- No new runtime tests, live model comparison, real Discord acceptance, savings or latency claims
  are made by this documentation checkpoint. Existing main CI is not evidence for future changes.

## Next concrete action

Implement the R1 spike with current source/API contracts, deterministic negative fixtures and a
reproducible comparison interface. Test the harness and validator before any production selection
cutover. Keep rule-only, mocked/fake-encoder, real Planner, real Director and human-label evidence
separate. Continue independent authorized safety work when a model-quality dependency is unavailable;
never promote ambient behavior or mark the complete refactor done on synthetic evidence alone.
