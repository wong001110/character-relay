# Project state

Updated: **2026-10-05**. This is the only current progress and takeover record.

## Current scope and authority

| Item | State |
| --- | --- |
| Repository / baseline | `wong001110/character-relay` / fetched main `b0f05540aa33b2ae60dbe35cd5a1e0631ac2f649` (through squash-merged PR #224) |
| Active direction | [Room Companion MVP](docs/plans/web-room-companion-2026-10-04.md): shared Web Room session and Document PiP |
| Current instruction | Continue the requested Companion repair with Dots feedback: latest-position layout, custom emoji and readable GIF descriptions/viewing. PR #224 is merged; no further merge/manual deploy. Dots launch attribution and earlier permission-error cause remain unconfirmed; preserve Open full room behavior, live-message/send gates and independent PR #219. |
| Development branch | `fix/room-companion-reading-20261005`, from the documentation closeout of main `b0f05540aa33b2ae60dbe35cd5a1e0631ac2f649`. |
| Sizing follow-up | MERGED / VERIFIED: small/medium/custom sizes, explicit native restoration, current-page size memory and tiny-window layout. Both headed Chromium/Xfwm4 full journeys and exact-head PR checks passed; actual Dots runtime acceptance remains open. |
| Reading follow-up | IMPLEMENTED / LOCAL VERIFIED: layout-aware latest position, shared rich-text presentation, visible supplied media descriptions and explicit viewing links. Dots runtime validation remains separate. |
| Follow-up code receipts | PR #214 squash `b44ced4b67dc7713dae895a5c75a534213c7f49e`; PR #215 squash `4ab31aae04c6ddb11d6817eaf0f699cdb54a54c6`; PR #217 squash `f243918043ae711d86ff27f38fce5bbaa556b98a`; PR #218 squash `8e459af1d39060b4e7008d780bcb392e977592eb`; PR #221 squash `3223130996afacc78590aa43c26141ec7d78c753`; PR #219 MYT fix remains separate/open |
| Merge / production deploy | PR #214, #215, #217, #218, #221, #223 and #224 are squash-merged. PR #219 remains separate and unmerged. No manual production deploy or production data change occurred in this batch. |
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

Review the focused reading follow-up and its remote checks, then verify latest position, emoji
and GIF descriptions/viewing in Dots after delivery. Continue user-owned observation of a natural incoming message and an
intentional quick-text send, including full-room convergence and the delivery receipt.
Actual Dots launch parameters/root cause remain unconfirmed. Open full
room retains the Companion by design. PR #219 remains separate; no manual production deployment
was performed.

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

## Room Companion implementation checkpoint (2026-10-04)

Portal now owns a single account/room-scoped Web Room session across routes. Full Room and
Companion share snapshot, read/unread state, draft, pending lock and immutable retry payload.
Document PiP uses a React portal plus same-origin styles; absent/rejected PiP has an explicitly
in-app fallback. Management/pickers remain local. Scope and stream epochs are separate so
reconnect permits REST send and does not strand in-flight requests. SSE acknowledgement prevents
late POST responses from downgrading delivered receipts or resurrecting reconciled echoes.
Page restoration rechecks auth, is actor-bound, and rejects stale pre-logout responses.

Web typecheck, **157 tests**, production and mock builds passed. Full Python **1,411 passed,
7 skipped, 11 warnings**; focused Web Room/Portal **54 passed** (overlapping, not additive).
Ruff passed; mypy passed across **343 sources**. Independent controller/source review and
**15 targeted manual mutants killed** supplement these checks. One actor-restore test gap
was strengthened with a shared-access-room counterexample and rerun; no unresolved survivor.
The current application code `7c40a995b41c8c7896317c0981009bfd292cbc6e` passed the real isolated
API browser journey with Chromium 151 headless, native PiP/CSS/input/SSE, one EventSource
(max active 1), shared draft, structured reply/media, unread 0/1/2/0, real pending/idempotent
send and synthetic Connector claim→uncertain receipt. Closing PiP/routes retain session;
logout closes/clears it. Absent and rejected PiP fallbacks pass. Persisted page event handlers
recheck real auth, and a held real 200 response released after actual logout cannot revive
user/session/stream. `.venv/bin/python scripts/verify_room_companion.py --chromium /usr/bin/chromium`
exited 0; script Ruff/format checks passed. This verifies handlers, not actual BFCache navigation. Dots desktop
visibility/input and real Gemini foreground behavior remain unverified. No backend routes,
credentials/dependency contracts, live sends, production data or deployments were changed.


Delivery: focused [PR #223](https://github.com/wong001110/character-relay/pull/223) was
squash-merged to main on the user's explicit request as
`f1461249cfd44532167a7f9ad985b2e98a8283a0`. Its final head
`22375262014a884489a2ca80615caac5f43a7f66` passed GitHub CI **37179054225** (Python 3.12/3.13,
Web, Discord Connector, PostgreSQL foundation and Docker), Railway Smoke **37179054240**, and
Public Demo contract check **37179054237**; the shared-deployment health job was skipped on the PR.
GitHub reported `MERGED`; fetched origin/main and the clean local checkout matched the squash SHA.
The initial Git push transport 503 was corrected with per-command HTTP/1.1; remote branch
identity was verified. GitHub API access subsequently succeeded and PR creation is confirmed;
the earlier API network blocker is resolved, with no duplicate credential request.
The required `api.github.com` domain addition was saved in the environment draft while
preserving package-manager presets. No manual deployment was performed.

The seven local Python skips remain environment-gated; CI evidence is distinct from the local
browser run and does not establish live Discord/provider qualification or actual BFCache navigation.

## Room Companion Dots feedback (2026-10-04)

Evidence is the Dots report relayed by the user, not a fresh run by the coding agent:

- Pop-out, visibility across pages, bidirectional draft synchronization, minimize/expand, and
  close/reopen worked. The test draft was cleared, and Dots returned to the connected full room.
- The initial window was approximately **1091×819 on a 1364×1024 desktop**, larger than expected
  for a small companion. `documentPip.ts` already requests **380×480** from the native API.
  At feedback intake the discrepancy was unresolved; the subsequent native sizing investigation
  below reproduces a matching browser-launch cause without changing implementation.
- Open full room focused/navigated the parent while retaining the PiP window. This matches
  `RoomCompanionHost.openFull` and the accepted plan; closing the presentation is a separate action.
- There was no natural new message, so live incoming-message synchronization and sending from
  Companion remain **UNVERIFIED in Dots**. Do not infer these passes from draft synchronization
  or the earlier isolated browser journey. Gemini-specific foreground behavior and actual BFCache
  navigation are not established by this report.

This documentation follow-up changes no source, tests, dependencies or live behavior. Verification:
inspected the native size request, Open full room call site and accepted plan; `git diff --check`
passed. Next gate is the live-message/send observation and a bounded native-window sizing diagnosis.

## Room Companion native sizing investigation (2026-10-04)

The reported **1091×819** was reproduced exactly in **headed Chromium 151.0.7922.173** on
an isolated **Xvfb 1364×1024** display, using a synthetic loopback page, real clicks and native
Document PiP. No simulated Playwright viewport, application CSS, live account or Discord send
was used. Native CDP window bounds agreed with `outerWidth/outerHeight`:

| Browser launch / request | PiP inner size | PiP outer size |
| --- | --- | --- |
| Ordinary launch; request `380×480` | `380×480` | `388×518` |
| Launch `--window-size=1364,1024`; same request | `1083×781` | **`1091×819`** |
| Same global flag; request also sets `preferInitialWindowPlacement: true` | `1083×781` | **`1091×819`** |
| Same global flag; subsequently call `resizeTo(388,518)` | `380×480` | `388×518` |
| No global flag; CDP resizes only the parent to `1364×1024` | `380×480` | `388×518` |

Pinned [Chromium's sizing code](https://github.com/chromium/chromium/blob/151.0.7922.173/chrome/browser/picture_in_picture/picture_in_picture_window_manager.cc#L433)
accepts the requested viewport plus frame margins but caps the outer window to **80% of the
display**, yielding `round(1364×0.8)=1091`, `round(1024×0.8)=819`. Cached bounds can override
size hints on same-tab reopen; preferred initial placement bypasses that cache, but not the
global launcher override reproduced here. A page-zoom multiplier does not explain the unequal
width/height enlargement. Application CSS only fills the resulting viewport.

The pinned [browser window-placement helper](https://github.com/chromium/chromium/blob/151.0.7922.173/chrome/browser/ui/browser_window_state.cc#L148)
applies `--window-size` after computing the requested bounds, with no PiP exception. That override
then meets the native PiP maximum constraint, explaining the exact reproduction. Source and a
separate headed probe independently agree on this causal path.

The strongest reproduced cause is the browser-wide `--window-size` launch override. Dots actual
browser version and launch arguments are not yet supplied; the subsequent report below confirms
the native measurement method and matching inner size. This is a confirmed reproduction rather
than confirmation of its actual startup configuration. Headless `--window-size` and simulated viewport runs also distort
native geometry; the existing functional browser runner did not establish native small-window size.

Preferred environment correction: remove the global `--window-size` override and resize only the
parent window. A native `resizeTo` correction is technically possible; its arguments are outer
dimensions, so preserve the measured frame delta to obtain the intended inner viewport. A product
change must preserve intentional user resizing/placement; no automatic resizing or cache-reset
change was made during this investigation. Live incoming-message/send acceptance remains pending.

Evidence: `.venv/bin/python /tmp/character-relay-pip-headed/probe.py` and the native geometry
receipt `/tmp/character-relay-pip-headed/probe-result.json`; pinned-source research is under
`/tmp/pip-native-research`. Xvfb and synthetic browser/server resources are temporary and cleaned
up by the probes. Documentation-only verification: `git diff --check`. Next gate: confirm the
matching browser launch flag in Dots and apply the parent-only window sizing correction there.

## Dots native-window follow-up (2026-10-04)

User-relayed Dots evidence confirms Linux/Xfce with Xfwm4 and Chromium. Browser version is
unconfirmed because its browser tool denies `chrome://version`; no attempt was made to bypass
that tool's URL restriction. The original **1091×819** is a native-window-list measurement,
with document client area **1083×781**, exactly matching the launcher-override probe above.
Dots manually shrank the outer window to **620×532** (client **612×494**), clicked Close Room
Companion, and reopened it. The outer window returned to **1091×819** at its original position.
This report covers one close/reopen cycle and does not establish the actual browser launch args.

Both reported states have the same **8×38** frame delta as the isolated headed Chromium probe.
The native measurements remove the earlier screenshot/emulated-viewport ambiguity. The application
still requests `380×480` on reopen; it does not request `1091×819` or set
`preferInitialWindowPlacement`.

A further isolated **real Xfwm4 + Chromium 151** probe confirms EWMH `_NET_WM_NAME="Xfwm4"` on
private Xvfb `:130` (1364×1024). Each case uses a fresh browser context without viewport emulation,
a real Open click, native CDP resize to **620×532** at `(50,60)`, a child Close click, then reopen:

| Launch parameter | Initial outer / inner | Default reopen outer / inner |
| --- | --- | --- |
| None | `406×518` / `398×480` | `638×532` / `630×494` |
| `--start-maximized` only | `406×518` / `398×480` | `638×532` / `630×494` |
| `--window-size=1364,1024` | **`1091×819` / `1083×781`** | **`1091×819` / `1083×781`** |
| Both launch parameters | **`1091×819` / `1083×781`** | **`1091×819` / `1083×781`** |

All native resizes independently measured client **612×494**, matching Dots. Ordinary cache
reuse stayed small, though this Chromium build added 18px width on reopen. Default Xfwm4 and a
maximized parent do not explain the giant reset in this controlled environment. Preferred initial
placement still cannot defeat the global window-size override. The probe moved the window before
closing: default reopen positions remained near the cached location `(32,60)`; an unchanged
position in Dots is compatible if it only resized. Dots actual movement and launch-position args
are unconfirmed, so its position report is not independently reproduced as a separate reset.

Evidence: `.venv/bin/python /tmp/character-relay-pip-xfwm/probe.py`, receipt
`/tmp/character-relay-pip-xfwm/probe-result.json` (client metrics, native bounds and X window tree).
Private browser, Xvfb, Xfwm4 and D-Bus services were stopped; no real desktop/account was used.
`git diff --check` passed; no application source or behavior change. Next gate is reading only
the actual Chromium `--window-size` launch argument/configuration, which does not require access
to `chrome://version`. If present, use parent-only resizing and a controlled removal comparison;
browser version and actual environment attribution remain unconfirmed.

## Sizing repair evidence correction (2026-10-04)

The first real-API implementation journey did **not** pass automatic default sizing: a prepared
PiP stayed at **1091×819** despite a post-open resize attempt. Pinned Chromium 151
[resizeTo source](https://github.com/chromium/chromium/blob/151.0.7922.173/third_party/blink/renderer/core/frame/local_dom_window.cc#L2151)
requires and consumes transient activation in the **PiP receiver window**; opening consumes the
parent's activation. Delaying or retrying cannot create a valid gesture.

The earlier isolated `child.evaluate(resizeTo(...))` success included Playwright-injected user
activation. It proves resizing under activation, **not an automatic post-open correction**.
The original launch-parameter/window-limit reproduction remains valid, while that automatic-resize
inference is withdrawn. A clean CDP `Runtime.evaluate` with `userGesture:false`, without preceding
parent/child page.evaluate calls, reproduced `NotAllowedError` and unchanged dimensions; a genuine
PiP preset click then succeeded. Corrected probe receipt is under
`/tmp/character-relay-resize-browser`.

The authorized implementation now requests the default small size, makes at most one best-effort
post-open attempt, displays the actual size, and offers a directly visible **Use W×H** action when
it differs from the remembered selection. That action and custom/preset controls execute resize
synchronously within a real PiP click. Under a browser override, first-open/reopen physical size
cannot be guaranteed without that click. No synthetic gesture or security-policy bypass is used.
Verification must separately record the browser-controlled initial bounds and the explicit-action
result; it must not grant activation while measuring the automatic path.

## Room Companion sizing checkpoint (2026-10-04)

Implemented the authorized frontend repair: default request **380×480**, Small and Medium
**480×640** presets, labelled custom integer inputs (width **320–2000**, height **320–1600**),
actual content-size display, denied-resize/validation feedback, and direct **Use W×H** restoration.
The separate sizing form cannot submit a Room message. Explicit and manual dimensions are
remembered across routes/close/reopen within the authenticated Portal lifetime; refresh or
auth/access loss resets the preference. Existing Open full room behavior is retained.

Ordinary Xfwm4 opening widened the initial content from 380 to 398 about **403.5ms** after the
native promise resolved. An early quiet sample incorrectly remembered that as manual input.
The Host now observes the full **500ms** before establishing its native baseline, requires usable
native bounds, and uses child timers with scope/window guards and cleanup. Explicit Apply/Use
ends observation immediately. Native border resizing during that short initialization period
may not be remembered; this heuristic covers the measured timing, not every possible WM.
Tiny PiP independently scrolls sizing/composer controls and removes the history padding floor.

Final headed **Chromium 151.0.7922.173 + real Xfwm4**, private **1364×1024** desktop, real isolated
API/SQLite/native SSE, without sizing viewport emulation:

| Scenario | Observed content / outer size |
| --- | --- |
| Global `--window-size` override, before explicit action | `1083×781` / `1091×819` |
| Ordinary opening, before explicit action | `398×480` / `406×518` |
| Default after real Use click, both launch modes | **`380×480` / `388×518`** |
| Custom/manual after close/reopen + Use | **`612×494` / `620×532`** |
| Minimum custom with panel expanded | `320×320` / `328×358`; composer inside viewport, input focus and Send pointer hit verified |
| Valid oversized `2000×1600` selection | Browser clamped to `674×474` / `682×512`; actual display and Small recovery verified |

Both **full** journeys passed the original receipt/idempotency/unread/draft/route/fallback/auth and
persisted-handler checks plus native sizing. Sizing created no message POST, retained one SSE,
and reset selection/draft after same-document logout/relogin. Clean CDP `userGesture:false`
measurements confirmed `NotAllowedError` without dimension change; only real child clicks resize.
The runner waits at least 500ms plus 300ms of stable geometry, avoiding a false early-size pass.

Verification: `cd web && npm test` **175 passed**; production build (including TypeScript) and
`npm run build:mock -- --outDir /tmp/character-relay-resize-mock-final` passed. Runner Ruff check,
format check, py_compile/help and `git diff --check` passed. The two browser runs were invoked by
`.venv/bin/python /tmp/character-relay-resize-browser/run.py`; reproducible application entry is
`scripts/verify_room_companion.py --headed --verify-sizing` with the optional launch override.
Immutable local receipts: `final-dual-full-summary.json` and `final-full-{launcher_override,ordinary_launch}.json`
under `/tmp/character-relay-resize-browser`; initial timeline is `ordinary-opening-timeline.json`.
Temporary graph/browser/API resources were cleaned. Independent source review passed the helper,
Host lifecycle, controls and preference guards; root reviewed the integrated diff and receipts.

No backend, dependency, credential, delivery or persistence contract changed. New protected
authorization/delivery policy was not introduced; existing scope tests and actual auth cleanup
provide the relevant regression evidence. No new bounded mutation campaign was run. Dots actual
runtime sizing, live incoming messages/send, browser launch attribution and actual BFCache remain
unverified. Physical first-open/reopen size under browser override still needs the explicit click.
At this implementation checkpoint, no new merge/manual production deployment or unrelated
PR #219 action had occurred; the subsequently authorized merge is recorded below.

Delivery: the user explicitly authorized squash merge, and
[PR #224](https://github.com/wong001110/character-relay/pull/224) was merged at **2026-10-04 09:35:07 UTC**
as **`b0f05540aa33b2ae60dbe35cd5a1e0631ac2f649`**.
Application commit **`a35961a1559f6b69c3dc716726dd05c34a790050`** contains the locally verified
implementation. Exact pre-merge head **`ea224ac07a050e68f8255520785eef630d6d0bba`** included only
documentation changes after that application commit. Its remote receipts passed:

- [CI 37191858755](https://github.com/wong001110/character-relay/actions/runs/37191858755):
  Python 3.12/3.13, Web, Discord Connector, PostgreSQL foundation and Docker all successful.
- [Railway Smoke 37191858733](https://github.com/wong001110/character-relay/actions/runs/37191858733)
  and [Public Demo contract 37191858763](https://github.com/wong001110/character-relay/actions/runs/37191858763)
  successful; shared deployment health was skipped by the PR condition.

Root and independent read-only review both confirmed the expected head and clean merge state.
The squash used `--match-head-commit` without bypassing checks. GitHub reports MERGED;
fetched remote main and fast-forwarded local main both match the squash SHA, and their source
tree exactly matches the tested PR head. HTTP/1.1 fetch succeeded. This receipt is a separate
documentation-only follow-up; no application code changed after verification. No manual production
deployment or unrelated PR #219 action was performed, and automatic deployment success is not
claimed. Dots sizing/live-message/send qualification remains the next runtime gate.

## Dots reading feedback and repair (2026-10-05)

Dots reports that the Companion stays visible while visiting other websites, shares the full-room
draft and retains the draft across close/reopen. The synthetic draft was cleared without sending
to the group. Reopening with a selected 380×480 size still initially opens large and needs the
child's Use-size click. This matches the qualified Chromium limitation, but actual Dots launch
arguments/root cause remain unconfirmed. No permission error occurred in this run; that does
not establish the earlier error's cause. Dots has not yet qualified live incoming updates or
Companion delivery during a suitable real conversation.

The reported older opening position has a reproducible layout path: on pristine main
`b0f05540aa33b2ae60dbe35cd5a1e0631ac2f649`, enable copied PiP CSS after mounting a long newest
message. The native history remains at scrollTop 0 with **723px** below it. The latest message ID
does not change when styles load, so the old effect does not run again. The repaired build reaches
the bottom (**0px remaining**) without marking the window as an active reader. This demonstrates
a cause the repair covers; it does not prove which layout event occurred in Dots.

The Companion now observes its child-document history viewport/content with ResizeObserver,
following layout and same-ID content changes only while at latest. The observer disconnects on
minimize/close; a reader scrolling up retains that position. It reuses full-room emoji/mention
rendering with readable emoji names and filtered Companion asset URLs, preserving structured-reply
prefix removal. Existing attachment/embed descriptions appear in visible text, with explicit
View image/View GIF links to separate documents. Missing descriptions are labelled honestly;
no generated semantic descriptions or media-analysis service was added.

Frontend tests: **178 passed**; `npm run build` (including TypeScript) and
`npm run build:mock -- --outDir /tmp/character-relay-reading-mock` passed. Runner Ruff check/format,
py_compile and `git diff --check` passed. The real isolated API/native PiP reading journey passed
delayed CSS, same-ID media insertion/edit following, actual wheel-scroll retention, unread
preservation, readable emoji names, supplied GIF attachment/embed descriptions, real GIF viewing
in a new document, one SSE and cleanup. Reproducible entry remains
`scripts/verify_room_companion.py --chromium /usr/bin/chromium`; the reading journey is now included.

Final headed **Chromium 151.0.7922.173 / Xfwm4 / 1364×1024** full acceptance also passed the
reading journey, existing receipt/idempotency/shared-draft/unread/route/auth/fallback/persisted-handler
checks and native sizing (including no-gesture denial, 320×320 composer reachability and
close/reopen restoration). Command: `.venv/bin/python /tmp/character-relay-reading-browser/run.py
--ordinary-only`; native application entry is `scripts/verify_room_companion.py --chromium
/usr/bin/chromium --headed --verify-sizing`. Receipt:
`/tmp/character-relay-reading-browser/ordinary_launch.json`. Private browser/API/desktop resources
and synthetic GIF assets were cleaned. The launch override was qualified in PR #224; this
frontend reading change did not repeat that launch mode or alter sizing implementation.

This is self-reviewed source/browser evidence; no independent review or new bounded mutation
campaign was run. Auth/delivery policy, backend, API/schema, dependencies and sizing implementation
are unchanged. Existing scope/auth/fallback/send regressions provide the relevant protection checks.
Dots' new reading behavior and live-message/send remain runtime gates; actual BFCache remains
unverified. No new merge, manual deployment, production message/data change or PR #219 action.
