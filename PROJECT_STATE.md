# Project state

Updated: **2026-10-02**. This is the only current progress and takeover record.

## Current scope and authority

| Item | State |
| --- | --- |
| Repository / baseline | `wong001110/character-relay` / `2812d79b314b25aa31fe0632dcbdd7da205b0bf0` (merged PR #207) |
| Active direction | [Lightweight Room Director refactor](docs/plans/discord-group-chat-core.md) |
| Current instruction | Finish the accepted refactor in Execution mode; user will perform live testing afterward. External Agent Continuity stays outside the checkout. |
| Development branch | `refactor/lightweight-room-director` |
| Direction receipt | `94be0361ef5c4c77bdbf180146beb6f49a5dc6d2`; documentation only, before implementation |
| R1 source receipt | `f3933d01f43cfe40d42369db0e927d0151f1480f`; final fixture/docs/dependency guard are in its follow-up commit |
| Merge / production deploy | User authorized squash merge of the completed refactor plus Web Room Participant to main on 2026-10-02; not yet performed. No manual production purge. |
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
| R2 | IMPLEMENTED / OFFLINE VERIFIED: Room source/selection records, origin-scoped SDK ancestry/history, canonical requester binding, ordered permission observations, continuous edits/deletes, separate bounded work/publication queues, atomic delivered-response source links. Recovered R2 full suite: 1,433 passed, 7 skipped; see R3 review for current source/claim checks. |
| R3 | RUNTIME SAFETY IMPLEMENTED: delivery-bound re-entry, attempt/room/member limits, server-owned preflight and one tool-free refresh, atomic delivery claim. Existing Free Pool caller remains qualification-gated; user-owned real-model validation is DEFERRED. Old-selector/composition retirement remains to be completed with R4/R5. |
| R4 | IMPLEMENTED / OFFLINE VERIFIED: explicit scoped notes, source-linked raw-history/media recall, retrieval-only index contracts and intent-first sparse expressions. Old composition/API/configuration is explicitly pending R5 removal. |
| R5 | BACKEND RETIREMENT VERIFIED: independent pending effects, scoped lifecycle, old selection/cognitive/Discovery/Roast composition and ORM consumers removed. Connector/Portal consumers and observations remain R5-C work. |
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

Continue R5: remove replaced runtime, configuration, API and Portal consumers; extract only
required pending-action/effect state and complete requester-bound controls. Then perform the
R6 integration/reset/card rehearsal.
Live Discord/model quality tests are explicitly user-owned and deferred, not an implementation
blocker or a claimed pass. Keep ambient unqualified by default; provide the evaluated-member setup
for later testing. Squash merge is authorized after verification; live data deletion is not performed by development.

## R3 implementation checkpoint (2026-10-01)

Resumed from exact remote R2 `2c7ce413f4c6930fbb8ee837978f0482355849dc`; the prior unpublished
R3 did not survive and was rebuilt, not assumed recovered. The implemented guards are documented
in [the R3 review](docs/reviews/room-director-r3-2026-10-01.md). Bounded manual mutation checks:
8/8 killed, each with a passing unmutated counterpart. Connector typecheck, 162 tests and build
passed; mypy passed over 418 sources. Whole Python: **1,457 passed, 7 skipped**; exact checks are recorded in the review. This remains self-review, not independent signoff or full-refactor completion.

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

## R4 implementation checkpoint (2026-10-01)

From R3 `e7d4731519047fccda25078dfd44354a8ca79127`, explicit notes replace ordinary
Belief/relationship injection and raw room messages replace summary-as-evidence recall.
Post-generation expression intents resolve sparsely; model prompts no longer receive catalogs.
See [R4 review](docs/reviews/room-director-r4-2026-10-01.md) for the tested boundaries.
Whole Python: **1,514 passed, 7 skipped**; Ruff and mypy (**424 files**) passed. Connector:
**162 tests**, typecheck and build passed. Eight targeted manual mutants were killed after two
initial surviving test gaps were strengthened and rerun. These are self-reviewed offline results;
no live model, PostgreSQL, browser, full retirement or cost/quality superiority is claimed.


## R5-A checkpoint (2026-10-02)

Reconstructed from the exact R4 tree; earlier unpublished R5 work was unavailable. Pending
side effects now use `PendingActionRepository`/`pending_actions` with real room/requester/source
identity and no semantic Thread/Segment fields. Production composition uses this store. Native
Thread continuation, atomic claims, suppression of uncertain tools, terminal idempotence and
expiry-at-claim are tested; no old-task migration or live data reset has occurred.

Local Python 3.13.5: `pytest tests/test_pending_actions.py tests/test_tool_continuation_review.py
 tests/test_room_context.py`: **34 passed**. Whole-source mypy: **426 files passed**. Changed Python
Ruff passes. These are self-reviewed focused results, not R5 completion or full integration CI.
Next: remove the old selection/cognitive composition and its UI/configuration consumers, then R6.

## R5-B checkpoint (2026-10-02)

Backend composition/API/storage retirement implemented; source details and exact test-disposition
map: [R5-B review](docs/reviews/room-director-r5b-2026-10-02.md). Full core backend regression:
**1,373 passed, 7 skipped**, followed by focused final knowledge-bridge cleanup checks. Whole-source
mypy and Ruff pass. This is self-review and not a production deployment, live-model acceptance,
or complete R5. Next: remove Connector/Portal consumers and implement daily notes/observations; R6
reset/card/fence and integrated checks remain. Source checkpoint and recovery snapshot are separate
from the earlier unpublished work, which was not restored or claimed complete.

## R5-C Portal checkpoint (2026-10-02)

Reconciled actual remote R5-B `7c076c9f5dafef67940c5a5d94083b18bc58998b` rather than
rebuilding already published work. Retired the old Portal simulation/semantic participation,
Discovery and Roast consumers. Existing authenticated note CRUD now has a scope-explicit UI;
expression metadata uses the supported catalog API; Free Pool settings move to Administration
with the existing credential modal and explicit Room Director qualification import.

Frontend typecheck, **60 tests**, and production build pass. The build retains a size warning;
no browser or full-refactor pass is claimed yet. Deleted tests described only retired features;
new note transport tests preserve scope, expected-version and safe failure behavior.
Connector retirement, correlated observations, R6 and Web Room remain in progress.

## R5-C Connector + Web Room checkpoint (2026-10-02)

Connector now has one durable group-chat path, with no local semantic scoring, old profile API,
Roast/session calls, eager expression candidate pipeline or backup bot-tag loop. Existing grants,
draft preflight, receipts, recovery and bounded attempts remain. Web Room adds existing-session
SSE/REST, explicit publication + server/room membership, versioned owned profiles, a durable
at-most-once webhook outbox and receipt-bound external actor attribution. Browser identity never
becomes a Discord human or a Character/tool grant. A dedicated bot-owned webhook handles Web
participants; Discord echoes reconcile by the persisted message ID. Native Thread replies use
source links and persisted ancestry, not an invented webhook Reply feature.

Checks on this source batch: 43 focused Python integration cases passed (including 20 new Web
cases); 149 Connector tests passed; 64 Portal tests passed; Python typing (343 files), both TS
checks and Ruff passed. Portal production build passed with an existing bundle-size warning.
These are self-reviewed offline results. Local Playwright navigation was blocked by the host's
browser policy (`ERR_BLOCKED_BY_ADMINISTRATOR`); no policy was bypassed and no browser pass is
claimed. A real API-backed browser test is still required in isolated CI. Live Discord is not used.

Remaining in-scope: correlated observation UI, new-table lifecycle/closeout audit, R6 controlled
reset/epoch/card rehearsal, complete integrated checks, browser validation and exact-head CI.
Web transport fault tests use a simulated Discord boundary, not a live-send result. User-owned
Free Token Pool / real Discord evaluation remains separate. No merge, live purge or manual deploy.
