# Group-chat checkpoint and operator checklist — 2026-09-22

This is a dated evidence/acceptance snapshot, not a second live progress ledger.
Current work remains in [PROJECT_STATE.md](../../PROJECT_STATE.md).

## Scope correction

The user requested an HTML summary, a list of checks, then squash merge to main. The recoverable
remote product changes are foundation + P2a, at source `53d53d0` and remote head `219ad92`.
The prior conversation's later unpushed workspace was not retained in this environment; no
matching source patch/archive/bundle was found. Its 1084/150/14 test logs do not attest code on
this branch. The user-facing report must state this prominently, not present all phases as done.

This closeout removes the temporary package-acquisition workflow and synchronizes scope/evidence.
No further product implementation, migration, production purge or manual deployment is performed.
Squash is explicitly authorized; the definitive result is PR #207's merge receipt. An already
configured hosting integration may deploy on a main change and must be checked by the operator.

## Evidence used

- Connected PR #207 and all visible remote branches were rechecked; head was `219ad921539b8d04cd6b3db990ac62e6932cbb0c`.
- Source artifact at `5035dd7` reconstructed Git tree `e153694728d318106011a04b17bfca9d1287aa8a`.
- Connected comparison to `219ad92` contains documents + acquisition workflow only.
- `219ad92` CI: https://github.com/wong001110/character-relay/actions/runs/35606369134 (success).
- `219ad92` Railway Smoke: https://github.com/wong001110/character-relay/actions/runs/35606369053 (success).
- `219ad92` Demo Status Check: https://github.com/wong001110/character-relay/actions/runs/35606369084 (success).
- P2a configured receipt: 135 Connector tests, typecheck/build, Ruff, mypy 403 files, 42 Python integration tests; see [transport evidence](group-chat-transport-2026-09-21.md).
- Final closeout-head CI is separate; record its real conclusion on the PR. No new full local suite or live-model quality pass is claimed.

## HTML artifact

`character-relay-summary-and-checklist.html` is delivered to the user as a standalone UTF-8 file.
It has 29 editable checks, local-browser persistence, JSON export/import, search/filter and print
controls. No external script/font/analytics dependency is loaded. Static checks verify unique IDs,
anchors, labels, counts and JavaScript syntax. Browser file navigation returned
`ERR_BLOCKED_BY_ADMINISTRATOR`; no browser pass or policy bypass is claimed.
The artifact is a snapshot; the final delivered copy includes the actual merge receipt, if merged.

## Operator checks

Use isolated rooms/test users, synthetic content and low-budget credentials. A failed authorization,
privacy, duplicate-side-effect or uncontrolled-retry check blocks broader rollout. Fault injection
belongs in an isolated mock/disposable stack, not by flooding Discord or corrupting production.

| ID | Check | Required result / action |
| --- | --- | --- |
| PRE-01 | API/Connector commit or image digest | Match tested compatible versions; know this is P2a only |
| PRE-02 | Hosting auto-deploy setting | Know whether a main update triggered rollout; no manual deployment claimed |
| PRE-03 | Backup and isolated restore | Recoverable DB/image baseline; no volume/table purge |
| PRE-04 | Dedicated canary room and accounts | Consent, synthetic inputs and bounded tool spending |
| PRE-05 | Message Content intent | Developer Portal + Connector agree; missing content not mistaken for model failure |
| PRE-06 | Channel/private-Thread effective permissions | No reads or disclosure from forbidden scope |
| PRE-07 | Conservative participation settings | Start with ambient and bot-tag continuation off; new 3/6/2 limits are not delivered |
| PRE-08 | Trace mode and overrides | metadata in real environment; no new prose, no assumed historical cleanup |
| CHAT-01 | Two people/two topics with Reply | Metadata and stable source retained; record residual semantic errors |
| CHAT-02 | Same names, renames, many roles | IDs remain distinct; actual humans retain aliases |
| CHAT-03 | Delayed enrichment and ordering | Old messages do not become latest; snapshots do not mutate each other |
| CHAT-04 | Edit/delete versus old queued results | No stale buffer resurrection; not a promise to refresh running generations |
| CHAT-05 | Ambient silence versus explicit request | Distinguish ignore, handoff failure, permission and provider errors |
| CHAT-06 | Character/language/media regression | Existing real capabilities preserved; no fabricated perception |
| SEND-01 | Normal multi-chunk send | One copy per chunk with actual receipt IDs |
| SEND-02 | Partial send, timeout, malformed ACK (mock) | Preserve IDs; no whole-answer replay or repeated tool effect |
| SEND-03 | 429 (mock) | No alternate-identity limit bypass |
| SEND-04 | Wrong/repeated uncertain report (mock) | Exact operation/step/claim enforced; receipts retained |
| SEND-05 | Duplicate events and restart | No duplicate publication; missing full rehydration remains a limitation |
| SEND-06 | Delayed tool plus another human | Buffer continues receiving; incomplete queue separation recorded |
| SAFE-01 | Synthetic private marker queried publicly | No cross-scope prompt input/output; stop on violation |
| SAFE-02 | Another member/bot claims authority | No unauthorized cancellation/write/paid-tool escalation |
| SAFE-03 | Revoked grants while work runs | No unauthorized late disclosure or replay |
| SAFE-04 | Allowed mentions in every send path | No unintended everyone/role notifications |
| SAFE-05 | Trace access and retention | Admin boundaries preserved; old raw data and new metadata distinguished |
| SAFE-06 | Dependency advisories and budget | Classify four recorded moderate advisories; no blind force-upgrade |
| OBS-01 | Incident evidence | Commit/card/model + redacted source/operation/job/message IDs |
| OBS-02 | Usage and cost provenance | Count retries/tool follow-ups; unknown is not zero |
| OBS-03 | Missing implementation versus acceptance | Do not pass nonexistent P3-P6 features merely because UI loads |

## Not delivered / do not pretend these are only production checks

Remaining P2 source/history/queue work; P3 bounded A-B-A and draft refresh; P4 new notes/relationship
mechanism, writer/Discovery and Roast retirement; P5 unified Portal/observation/raw capture; P6
full structural cleanup and integrated acceptance all remain required. The short relationship
simulation replacement and new source folders reported in conversation are not in this checkpoint.
See D01-D11/A01-A22 in the accepted plan before continuing.

## Failure and recovery

Pause affected deployments/tools/ambient participation, retain sanitized receipts, and determine
whether external actions actually occurred before any replay. Canceling generation does not undo
an external effect. Do not delete an uncertain ledger to make a job look new. Offline recovery
requires all DB-sharing replicas stopped; follow [storage safety](../storage-safety.md).
A code rollback is not a data rollback or permission to repeat effects. Keep production and
isolated test databases separate and do not upload raw group-chat data in issue reports.
