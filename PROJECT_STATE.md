# Project state

Updated: **2026-10-04**. This is the only current progress and takeover record.

## Current scope and authority

| Item | State |
| --- | --- |
| Repository / baseline | `wong001110/character-relay` / main `3223130996afacc78590aa43c26141ec7d78c753` (through merged PR #221) |
| Active direction | [Room Companion MVP](docs/plans/web-room-companion-2026-10-04.md): shared Web Room session and Document PiP |
| Current instruction | Implement and verify Room Companion on a focused branch/PR. No merge or manual production deploy. Preserve independent PR #219. |
| Development branch | `feat/web-room-companion-pip-20261004`, from fetched main `a07b9540672bf1f349079903656e5ad5e09b3162` |
| Follow-up code receipts | PR #214 squash `b44ced4b67dc7713dae895a5c75a534213c7f49e`; PR #215 squash `4ab31aae04c6ddb11d6817eaf0f699cdb54a54c6`; PR #217 squash `f243918043ae711d86ff27f38fce5bbaa556b98a`; PR #218 squash `8e459af1d39060b4e7008d780bcb392e977592eb`; PR #221 squash `3223130996afacc78590aa43c26141ec7d78c753`; PR #219 MYT fix remains separate/open |
| Merge / production deploy | PR #214, #215, #217, #218 and #221 are squash-merged. PR #219 remains separate and unmerged. No manual production deploy or production data change occurred in this batch. |
| Old application data | May be discarded at a controlled future cutover; no compatibility requirement for its own sake |
| Character cards | Prefer portable authored content; old schema must not block the refactor |
| Full refactor | **MERGED / OFFLINE CLOSEOUT COMPLETE** via PR #209, followed by Web Room parity/hotfix PRs #211-#218 and Portal UI follow-up PR #221. PR #219 is a separate Web Room timestamp fix. |

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

PR #214 was squash-merged to main as `b44ced4b67dc7713dae895a5c75a534213c7f49e`. Its application-code head
`a7103b01b8868b4861d9d3b467f6c8a5a693766e` was verified before that merge; no manual production deployment was performed.

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
  image. Select, paste and drag/drop all use the same private attachment path; selected images get
  local object-URL previews only in the browser. Actual bytes are validated server-side, stored
  short-term in the existing private generated-media store, and downloadable only by the Connector
  holding the exact outbox claim. Terminal delivery receipts delete the temporary bytes immediately;
  abandoned uploads remain TTL-bounded and are opportunistically purged. Temporary artifact
  URLs/base64 are not inserted into Agent prose.

Exact application-code evidence for `a7103b01b8868b4861d9d3b467f6c8a5a693766e`:
- GitHub CI run **37104710225**: Web, Discord Connector, Docker production image,
  PostgreSQL foundation, Python 3.12 and Python 3.13 all passed.
- Python 3.12 and 3.13: **1,409 passed, 7 skipped** each; Ruff and whole-source mypy passed.
- Web: **68 tests** plus typecheck, production build and mock build passed.
- Discord Connector: **154 tests** plus typecheck, build and image build passed.
- Railway Smoke **37104710292** passed.
- Public Demo Status Check **37104710220** passed.
- This is offline/self-reviewed evidence; no live Discord attachment send on this branch and no
  production deployment are claimed.

## Web Room reconnect-send hotfix (2026-10-03)

Dots reported two dead-click Send attempts around 18:30 and 18:52 MYT while the Web Room status
changed to `reconnecting`. Railway HTTP evidence showed the browser's SSE request cycling at the
server's intentional ~60-second stream boundary, no failed `POST /messages` during the dead-click
windows, and later retries reaching the same room with HTTP 202. Source review identified the
client-side gate: the Send button was disabled for every state except `connected`.

PR #215 keeps the read-side EventSource lifecycle unchanged and changes only send availability:
- `connected` and `reconnecting` allow the REST send path;
- `connecting`, `disconnected`, and `unavailable` remain blocked;
- reconnecting displays that sending remains available while live updates may lag;
- backend room membership, freshness, idempotency and delivery checks remain authoritative.

Exact application-code evidence for `08c65900453ee649ebc5061e98995bb4a728c9e6`:
- GitHub CI run **37120464308** passed Web, Discord Connector, Docker production image,
  PostgreSQL foundation, Python 3.12 and Python 3.13.
- Web: **69 tests** plus typecheck, production build and mock build passed.
- Discord Connector: **154 tests** plus typecheck, build and image build passed.
- Python 3.12 and 3.13: **1,409 passed, 7 skipped** each; Ruff and whole-source mypy passed.
- Railway Smoke **37120464327** passed.
- Public Demo Status Check **37120464292** passed.
- This evidence is self-reviewed CI evidence. No manual production deployment was performed.

## Web Room general-attachment extension (2026-10-03)

The user explicitly widened Web → Discord uploads from image-only to common Discord-style file
attachments. Branch `feat/web-room-general-attachments-20261003` reuses the existing private
GeneratedMediaArtifact + claim-bound Connector download + webhook `files` transaction rather than
adding public file hosting or another delivery path.

Current implementation scope:
- up to four attachments per message, 8 MiB each;
- PNG/JPEG/WebP/GIF still receive actual image-byte validation and local thumbnail previews;
- common text, PDF, Office, archive, audio and video extensions are allowlisted with compatible MIME
  checks; executable/script extensions are not accepted as generic opaque uploads;
- select, drag/drop and clipboard-file ingress share one upload path;
- non-image uploads render as attachment chips before send and as the existing file-card presentation
  after Discord observation;
- terminal delivery deletes private upload bytes; abandoned uploads remain TTL-bounded;
- Connector claim binding, send idempotency and no-temporary-URL-in-LLM-prose guarantees are unchanged.

PR #217 was squash-merged to main as `f243918043ae711d86ff27f38fce5bbaa556b98a`.
Its exact application head `9c5483dbeb6d514eef650279aacdd0f648802085` passed GitHub CI run
**37129794751**, Railway Smoke **37129794732**, and Public Demo Status Check **37129794747**
before merge.

## Web Room reply-link presentation rollback (2026-10-03)

The user asked to restore the prior Discord message-link fallback instead of the newer visible
`↪ Replying to <author>: <summary>` prose. This is presentation-only:
- same-room reply target resolution remains required before webhook delivery;
- `reply_to_message_id` remains structured RoomSource / Agent context evidence;
- Web participant webhook display name/avatar remain unchanged;
- Discord receives the prior `↪ https://discord.com/channels/.../<message>` line;
- no native Discord Reply capability is claimed.

PR #218 was squash-merged to main as `8e459af1d39060b4e7008d780bcb392e977592eb` after its exact application head passed GitHub CI, Railway Smoke and Public Demo checks.

## Portal UI follow-up (2026-10-04)

Live review by Dots found four bounded UI/product consistency issues that are accepted for this branch:
- a Server Knowledge tab can report that Knowledge Fabric is not bootstrapped even though the existing
  Super Admin Administration → Knowledge Fabric panel already owns the bootstrap action; expose a
  direct, authorization-aware route to that existing setup rather than adding a second bootstrap UI;
- Echo Masque Lab labels its close action “Character Library” even though it correctly returns to
  Toolbox; fix the stale navigation label rather than rerouting the Lab unexpectedly;
- Deployment workspace children render empty/disconnected placeholders while the first API load is
  still in progress; show an explicit loading state and avoid zero/empty claims before data resolves;
- Character Archive remains too dense around ~1170px because the four-column card shelf competes
  with the right-hand note rail; use a three-column medium-width layout and improve targeted muted
  text contrast. Server Passport should be collapsible without creating a second workspace surface.

Implemented on PR #221:
- missing Fabric scopes reuse the existing Super Admin Administration → Knowledge Fabric bootstrap
  surface through an authorization-aware deep link; no second bootstrap UI/API was added;
- Echo Masque Lab now labels its close action “Back to Toolbox” / “返回工具箱”, matching its actual owner;
- Deployment passes first-load state into the Server workspace, suppresses false empty/offline claims,
  shows an unresolved Character count as “…” and disables premature Server/Connection mutations;
- Server Passport is the same workspace content inside a controlled, default-open collapsible section;
- Character Archive caps the shelf at three columns at <=1180px before existing 2/1-column breakpoints,
  and only targeted low-contrast helper text was darkened.

Exact application-code evidence for `d36261529f1e3050b370e4055d23103e45ca702b`:
- GitHub CI **37138841099** passed Web, Discord Connector, PostgreSQL foundation, Docker production
  image, Python 3.12 and Python 3.13;
- Web: **21 files / 71 tests** plus typecheck, production build and mock build passed; the new
  settings deep-link test covers direct Administration → Knowledge Fabric routing and safe fallback;
- Discord Connector: **23 files / 154 tests** plus typecheck/build/image passed;
- Python 3.12 and 3.13: **1,411 passed, 7 skipped, 9 warnings** each; Ruff and whole-source mypy passed;
- Railway Smoke **37138841094** passed;
- Public Demo Status Check **37138841092** passed.

Mobile remains **not visually validated** by this review and no manual production deployment was
performed. PR #219 (MYT timestamp consistency) remains separate/open and is not folded into #221.

## Next concrete action

PR #221 was squash-merged to main as `3223130996afacc78590aa43c26141ec7d78c753` after final-head
GitHub CI **37139621329**, Railway Smoke **37139621316**, and Public Demo Status Check **37139621330**
all passed. Continue user-owned live UI observation. PR #219 remains separate/open; no manual
production deployment was performed.

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

## Room Companion capability checkpoint (2026-10-04)

Fetched origin/main matches actual checkout `a07b9540672bf1f349079903656e5ad5e09b3162`.
Accepted scope and phase acceptance were written before runtime refactoring. Synthetic local
Playwright spike on system Chromium 151 confirms Document PiP requestWindow via click,
same-origin CSS/DOM rendering, textarea input and Send click, including with a second local
tab foreground; close produces pagehide and keeps parent alive. Headless browser API/DOM
evidence does not establish visible always-on-top behavior or Dots Computer Control usability.
No Dots runtime is available. Bundled Playwright Chromium is absent; system Chromium is used
without bypassing browser API/security policies. Next: shared session and minimal Companion.
