# Project state

Updated: **2026-10-01**. This is the only current progress and takeover record.

## Current scope and authority

| Item | State |
| --- | --- |
| Repository / baseline | `wong001110/character-relay` / `2812d79b314b25aa31fe0632dcbdd7da205b0bf0` (merged PR #207) |
| Active direction | [Lightweight Room Director refactor](docs/plans/discord-group-chat-core.md) |
| Current instruction | Direction first, then execution-mode phased development with external Agent Continuity |
| Development branch | `refactor/lightweight-room-director` |
| Direction receipt | `94be0361ef5c4c77bdbf180146beb6f49a5dc6d2`; documentation only, before implementation |
| R1 source receipt | `f3933d01f43cfe40d42369db0e927d0151f1480f`; final fixture/docs/dependency guard are in its follow-up commit |
| Merge / production deploy | Not authorized by this assignment; not performed |
| Old application data | May be discarded at a controlled future cutover; no compatibility requirement for its own sake |
| Character cards | Prefer portable authored content; old schema must not block the refactor |
| Full refactor | **INCOMPLETE**; source-focused production routing is wired; continuation/freshness and retirement are still in progress |

## Baseline correction

Only Git-backed source is implementation evidence. PR #207 delivered foundation/P2a provenance,
room-buffer and partial/uncertain delivery protections, not the lost unpushed P3-P6 work. Historical
logs for that missing code cannot attest main or this branch. The old checkpoint remains in
[the merge review](docs/reviews/group-chat-checkpoint-2026-09-22.md) and Git history.

The ordinary Discord Connector now calls the Room Routing API, and Character context uses raw
source focus rather than a semantic Thread prerequisite. The inner Character Turn Director has
been removed from the generation path. Old selection APIs/composition and cognitive consumers
still exist pending their explicit retirement; this checkpoint does not claim that cleanup is done.

## Refactor progress

R0-R6 are this initiative's checkpoints, not old P0-P6 completion claims.

| Phase | Status / evidence |
| --- | --- |
| R0 | COMPLETE: direction/replacement/data/card policy and A01-A29 acceptance committed first; three documentation paths only. |
| R1 | OFFLINE SLICE VERIFIED: rules, strict decision/input validation, replay metrics, recorded-provider and native Planner seams, 240 synthetic/unreviewed cases. Actual Free Token Pool qualification, human-reviewed labels and complete old-pipeline comparison remain **NOT RUN**. |
| R2 | IMPLEMENTED / INTEGRATION VERIFYING: Room source/selection records, origin-scoped SDK ancestry/history, canonical requester binding, ordered permission observations, continuous edits/deletes, separate bounded work/publication queues, atomic delivered-response source links. Full suite rerun and mutation evidence pending. |
| R3 | IN PROGRESS: Free Token Pool adapter and strict qualification seam wired, default ambient disabled; inner Director removed. No real qualification installed. Bounded continuation, freshness and complete old-selector retirement remain. |
| R4 | NOT STARTED: explicit notes/history, relationships, retrieval-only encoders and sparse expressions. |
| R5 | NOT STARTED: Portal/observation and retired-consumer cleanup. |
| R6 | NOT STARTED: complete integration/deletion audit, isolated card/reset rehearsal and release preparation. |

## Evidence and limitations

[The R1 review](docs/reviews/room-director-r1-2026-10-01.md) binds source/corpus identities, commands,
mutation scope and survivor disposition. [Replay usage](docs/developer/room-routing-replay.md)
describes the actual entry points and missing live adapter.

- Local Python 3.13.5: **346 focused tests passed**, whole-repo Ruff passed, whole-source mypy
  passed across **406 files**. This is not the full Python/Portal/Connector/PostgreSQL suite.
- Bounded mutation: **240 executed, 222 killed, 18 self-reviewed equivalent/error-text survivors**;
  no timeout/tool-error in that executed set. Not all generated mutants were executed.
- Corpus: 240 parameterized examples in 30 families, 192 development/48 reserved. All labels are
  synthetic and unreviewed. The reserved set is not a human-reviewed model qualification set.
- Actual Planner class was exercised with an explicitly fake semantic service in adapter tests.
  No production FastEmbed quality baseline, live Director latency/cost, or superiority claim.
- SQLAlchemy is constrained to the compatible 2.0 series. Resolver-selected 2.1.1 reproduced the
  same 18 type errors on pristine baseline and this branch; no unrelated SQLAlchemy migration.
- A temporary GitHub workflow recovered exact source/offline dependencies because direct clone
  DNS was unavailable. The reconstructed source tree matched GitHub. A second bounded run rebuilt
  the fixture and verified its content hash. **The temporary workflow is removed from this tree**;
  its successful artifact jobs are not application CI or runtime acceptance.
- Railway read calls work; API/Discord services still follow main. No service/config/secret value,
  deployment or database was changed or exported. Card export/reset is still future isolated work.
- Agent Continuity v0.4.0 state/evidence is outside the checkout. No project continuity infrastructure
  is installed. All review in this checkpoint is self-review, not independent signoff.
- Final-head GitHub CI/PR conclusions belong to their exact remote receipts; local checks and the
  artifact workflow do not imply a green full CI. No merge/deploy/data deletion has occurred.

## Next concrete action

Implement R2 source/direct-route integration in the existing supported runtime: authenticated
normalized inputs, source persistence, permission-aware ancestry, requester/selected-author separation
and current grants at execution/delivery. Do not expose the spike's normalized schema as authority.
In parallel, prepare an evaluated Free Token Pool caller with bounded deadlines/attempts, no paid
fallback and honest missing-usage accounting. Existing utility JSON salvage/usage defaults must not
silently weaken the new contract. Obtain actual model/label evidence before ambient activation.
Retire old consumers at the planned production replacement boundary, not while the offline spike
is the only replacement. Keep every A01-A29 check visible; update this file after coherent work.

## R2 checkpoint (2026-10-01)

Source/test checkpoint follows verified R1 head `5870748009e86a741d7c39679799277ef9460b74`.
Connector **156 tests** passed; backend source/delivery subset **62 passed**. Whole-source mypy
passed across **414 files**, Ruff passed. The first full Python run was **19 failed, 1414 passed,
7 skipped**; failures were reviewed, contract fixtures/reproducible corpus corrected, and the
61-test affected subset passed. A subsequent full run is still required. Counts overlap and are
not additive. This is self-review. No new protected-boundary mutation, PostgreSQL, browser/live
Discord/model qualification or production rollout is claimed at this checkpoint.

Unpublished source and exact evidence are preserved externally as an Agent Continuity snapshot;
GitHub remains the delivery truth. R3-R6 acceptance must not be inferred from the new classes.
