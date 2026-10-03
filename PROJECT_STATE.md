# Project state

Updated: **2026-10-03**. This is the only current progress and takeover record.

## Current scope and authority

| Item | State |
| --- | --- |
| Repository / baseline | `wong001110/character-relay` / main `468dd81660913d35b69d35b13024e329a70e4a1a` (through merged PR #213) |
| Active direction | [Web Room live follow-up](docs/plans/web-room-followup-2026-10-03.md) on top of the completed Lightweight Room Director refactor |
| Current instruction | Execution mode for bounded defects found during live Web Room use plus the explicitly requested Web → Discord image-attachment extension. The user will continue reporting real-use findings. |
| Development branch | `fix/web-room-followup-20261003`; Draft PR #214 |
| Follow-up code receipts | `29c9e4139f1c1642a43502b537dd0de5fdd7ce5a` (send/delivery/reply/reaction fixes) and `301b2c5e77f2b83bfea40cc8cef31a74c98b8105` (image attachments) |
| Merge / production deploy | **Not authorized for this follow-up yet.** Keep PR #214 draft/open until the user closes the observation pass. No manual deploy or production data change. |
| Old application data | May be discarded at a controlled future cutover; no compatibility requirement for its own sake |
| Character cards | Prefer portable authored content; old schema must not block the refactor |
| Full refactor | **MERGED / OFFLINE CLOSEOUT COMPLETE** via PR #209, followed by Web Room parity/hotfix PRs #211-#213. Live follow-up remains in progress. |

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
| R5 | COMPLETE / OFFLINE VERIFIED: backend, Connector and Portal legacy consumers retired; scoped notes/recall, sparse expressions, pending effects and Web Room transport are on the supported path. |
| R6 | OFFLINE CLOSEOUT VERIFIED: fresh schema excludes retired chat tables, lifecycle isolation is covered, portable character authoring remains independent of retired chat state, Docker browser Rooms smoke and exact-head integration gates passed. No live purge was performed. |

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

## Web Room live follow-up checkpoint (2026-10-03)

Draft PR #214 contains the current bounded follow-up. Application-code head
`301b2c5e77f2b83bfea40cc8cef31a74c98b8105` is verified but not merged or manually deployed.

- Delivered-card lifecycle: a delivered receipt is retired once its Discord echo is durably present
  in Room source storage; it no longer reappears merely because that echo leaves the 64-message UI
  history window.
- Send reliability: a successful POST receipt is surfaced immediately and releases the composer;
  the browser no longer waits for SSE convergence before another send. The request has a bounded
  timeout and keeps the same client message ID for explicit safe retry after an unknown result.
- Reply presentation: Web → Discord reply fallback uses bounded referenced-author/source text
  instead of injecting a bare Discord message URL. Structured `reply_to_message_id` remains the
  Agent-facing evidence.
- Discord reactions: add/remove reaction events force-fetch the exact Discord message before
  publishing presentation state, avoiding stale Message-cache counts.
- Web → Discord image attachments: PNG/JPEG/WebP/GIF, maximum four images per message and 8 MiB per
  image. Actual bytes are validated server-side, stored short-term in the existing private generated
  media store, and downloadable only by the Connector holding the exact outbox claim. Temporary
  artifact URLs/base64 are not inserted into Agent prose.

Exact application-code evidence for `301b2c5e77f2b83bfea40cc8cef31a74c98b8105`:
- GitHub CI run **37101994857**: Web, Discord Connector, Docker production image,
  PostgreSQL foundation, Python 3.12 and Python 3.13 all passed.
- Python 3.12 and 3.13: **1,409 passed, 7 skipped** each; Ruff and whole-source mypy passed.
- Railway Smoke **37101994916** passed.
- Public Demo Status Check **37101994961** passed.
- This is offline/self-reviewed evidence; no live Discord attachment send on this branch and no
  production deployment are claimed.

## Next concrete action

Continue user-owned live observation on the currently deployed main behavior and add reproducible
findings to the follow-up plan. When the user decides the pass is complete, review PR #214 as one
batch, decide whether a live branch/deployment check is needed, and only then request merge/deploy
authorization. Free Token Pool Director quality evaluation remains a separate user-owned live check.

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


## R6 offline closeout (2026-10-02)

Source head `3adda1760f2cff6949cf134ce0f9916511ce5706` passed GitHub CI run **37028507484**: Python 3.12 and 3.13 each **1,394 passed, 7 skipped**; Web, Discord Connector, PostgreSQL foundation and Docker production-image/browser jobs passed. Exact-head Railway Smoke **37028506680** and Public Demo Status Check **37028507390** also passed. The Docker browser journey now opens the current Rooms workspace rather than retired Intelligence/Belief surfaces.

The fresh-schema retirement contract verifies that retired selection/cognitive/workflow tables are not recreated, while account-scoped room evidence, explicit character notes and pending effects retain isolation. Web Room remains deliberately bounded to authenticated session + explicit membership, owned display profile, text/reply, bounded SSE history and durable webhook delivery/echo reconciliation. Real Discord sends and Free Token Pool model quality remain deferred to the user's post-merge testing and are not claimed by these offline gates.

No manual Railway deployment, production reset, live credential export or data deletion was performed during development. The production cutover policy may discard old chat-state data later; portable authored Character content is not coupled to those retired tables.


## Web Room follow-up checkpoint (2026-10-03)

Live testing after PR #211/#212/#213 exposed four bounded defects on the supported Web Room path.
Draft PR #214 at head `29c9e4139f1c1642a43502b537dd0de5fdd7ce5a` implements the current repair batch:

- a successful Web POST now surfaces its accepted outbox receipt immediately and clears the local
  submit lock instead of waiting for SSE convergence; the POST is bounded to 15 seconds and an
  unknown network effect retains the existing same-client-ID safe retry path;
- delivered receipts retire once their exact Discord echo exists in durable Room source evidence,
  so they do not reappear merely because that echo later falls outside the 64-message Web snapshot;
- Web → Discord reply presentation no longer prepends a bare Discord jump URL; the Connector
  re-fetches the referenced same-room message and emits a bounded author + summary fallback while
  keeping `reply_to_message_id` structured for Agent context;
- Discord reaction events now force-fetch the exact message before publishing Room evidence, rather
  than trusting a potentially stale cached Message object.

Exact-head GitHub evidence for PR #214:
- CI run **37101121680**: Python 3.12 and 3.13 each **1,407 passed, 7 skipped**; Ruff and mypy passed;
  Web **67 tests** + typecheck + production/mock builds passed; Discord Connector **152 tests** +
  typecheck + build/image passed; PostgreSQL foundation and Docker production-image checks passed.
- Railway Smoke **37101121676** passed.
- Public Demo Status Check **37101121674** passed.
- These are offline/CI results. The reaction fix still requires the user's real Discord → Web
  observation, and PR #214 remains draft with no merge or manual production deployment.
