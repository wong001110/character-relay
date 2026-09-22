# Project state

Updated: **2026-09-22**. This is the only current progress and takeover record.

## Current scope and authorization

| Item | State |
| --- | --- |
| Repository | `wong001110/character-relay` |
| Previous main | `3cd183d460812d16cfb0c6d8dbae305d8ef61363` (PR #205) |
| Accepted design | PR #206 / `be7a8c01e45662a8d68abbefccce46f07e6a7110` |
| Implementation checkpoint | PR #207 / `feat/discord-group-chat-core-takeover` |
| Verified product source | `53d53d0cd99f7f59b518fc367ab619ed412a10a4` (foundation and P2a) |
| Verified remote head before closeout | `219ad921539b8d04cd6b3db990ac62e6932cbb0c` |
| Current instruction | Generate an HTML summary/checklist, then squash merge to main |
| Merge authority | User explicitly authorized squash merge on 2026-09-22; actual receipt is PR #207's merged SHA |
| Deployment / production data | Not authorized or performed by this task |
| Full initiative | **INCOMPLETE: this is a foundation/P2a checkpoint, not P1-P6 completion** |

PR #206's documents are included as ancestors; no unrelated PR #203 implementation is incorporated.
This closeout changes documentation and removes the temporary dependency-acquisition workflow only.
It does not introduce the missing P3-P6 implementation, alter runtime source, or weaken normal CI.
A merge receipt must not be described as proof that the full accepted design has shipped.

## Important continuity correction

The previous conversation reported extensive unpushed changes in `/mnt/data/character-relay`.
On 2026-09-22 that directory was not present in the active environment. The available source
archives, connected branch inventory and PR #207 still contain the foundation/P2a source only.
No matching later patch, source archive or Git bundle was recovered. The 1084-test Python log,
150-test Connector log and 14-mutant policy log survive, but do not reproduce or attest code
that is not in the repository. They are not merge evidence for this checkpoint.

Do not assume those changes were pushed, complete, or available in this branch. Also do not
assume unpushed Work changes are empty: reconcile any independently recovered workspace before
integrating it. The missing source remains an implementation/recovery task, not a production
validation task that the user can resolve by checking a box.

## Phase state

All D01-D11 and A01-A22 in the accepted plan remain requirements. Initial 3-role / 6-speaking-turn
/ 2-per-role limits are target ceilings, NOT implemented settings in this checkpoint.

| Phase | Repository-backed status |
| --- | --- |
| P0 | Accepted plan and AI-Native policy/state/source navigation available |
| P1 | PARTIAL: selected source/privacy/delivery defects characterized; full quality/cost baseline still pending |
| P2 | PARTIAL: P2a metadata, buffer and uncertain-delivery work verified; ancestor fetching, persistent response-source links, restart rehydration and slow-job separation remain |
| P3 | NOT DELIVERED: bounded A-B-A, attempt/room budgets and send-time draft refresh must be recovered or implemented |
| P4 | NOT DELIVERED: explicit scoped notes, short relationship replacement, automatic-writer/Discovery and Roast retirement remain |
| P5 | PARTIAL: metadata-default trace foundation exists; unified observation, Portal and controlled provider raw capture remain |
| P6 | NOT COMPLETE: checkpoint merge preparation is not the full integration, source-cleanup or retirement audit |

## What the verified source actually implements

- Deep-copied chronological room snapshots; repeat/enrichment updates preserve position.
- Gateway create/edit/delete updates the human buffer before slow processing; bounded tombstones
  and invalidation prevent stale queued content replacing newer buffer state.
- Per-message Reply/edit/real deployment metadata through Connector/Python contracts and prompt
  reconstruction. This is not a send-time draft refresh or complete restart history solution.
- Recent humans precede unrelated roles in mention aliases; stable IDs, not display names,
  distinguish humans and actual role identities.
- Selected-source persistence failure returns `reply_target_persistence_failed` rather than
  admitting a turn that could silently choose a different source.
- `connectors/discord/src/delivery.ts` separates definitely-unsent, partial and uncertain outcomes.
  Confirmed IDs survive errors; unknown/partial sends and 429 do not cause whole-answer fallback.
- Uncertainty reports bind to operation/step/claim, preserve receipts and do not advance dialogue
  or replay effects. Existing columns are reused; this source batch adds no schema migration.
- Provider trace defaults to metadata, retaining safe category/usage/error diagnostics. Existing
  explicit summary/content configuration and historical traces are not automatically changed.

Numerical relationships, ordinary automatic writers, Roast, unique-role guards and remaining
legacy consumers are still present. Do not describe them as removed or hide this limitation.

## Evidence and limitations

- Re-queried `219ad92`: CI run **35606369134**, Railway Smoke **35606369053** and Public Demo
  Status Check **35606369084** completed successfully. These are existing exact-head results,
  not new production acceptance or a claim that this version has been deployed.
- P2a configured run **35599133605** attests source `53d53d0`, tree
  `8a88bee627c525c47f660cf80663ff990692dce5`: Node 24 typecheck/build, **135 Connector tests in
  21 files**, Ruff, mypy **403 source files**, and **42 Python integration tests** passed.
- Recovered archive `group-chat-verification-tools.zip` has source commit `5035dd7`; its local
  reconstructed Git tree equals `e153694728d318106011a04b17bfca9d1287aa8a`. The connected comparison
  from that commit to `219ad92` changes only two documents and the temporary tool workflow.
- Earlier foundation/local/manual mutation counts overlap these scopes; do not sum them.
- The remaining temporary `group-chat-local-tools.yml` is removed in this closeout. No permanent
  coding-agent bootstrap/runtime or package-download workflow remains from this transport.
- The generated HTML provides 29 human checks with steps, expectations, stop criteria, and a
  separate not-delivered list. Static structure/anchors/control counts and JavaScript syntax
  were checked. Browser file navigation was blocked by environment policy; no visual/browser
  interaction pass is claimed. No policy was disabled to obtain a pass.
- Four previously reported moderate dependency advisories remain unclassified. No force-upgrade
  or clean audit is claimed. No live Discord/model quality, measured savings, production recovery
  or independent security certification is claimed.

Receipts: [foundation](docs/reviews/group-chat-foundation-2026-09-21.md),
[P2a transport](docs/reviews/group-chat-transport-2026-09-21.md),
[2026-09-22 merge/checklist snapshot](docs/reviews/group-chat-checkpoint-2026-09-22.md).
Checks are self-reviewed unless a specific independent result is recorded. Final closeout CI and
actual squash receipt are recorded on PR #207; do not infer them from earlier head results.

## Next concrete action after this checkpoint

Start a new implementation branch from the actual merged main. Recover the missing workspace if
available, otherwise implement the remaining accepted scope without claiming the logs restore it.
Begin with P2 permission-scoped source/history and request/queue separation, then P3-P6. Preserve
original requester authority, scoped evidence and completed/uncertain tool work. Use mocks for
external/live dependencies as the user requested; keep production checks separate from missing
implementation. Commit coherent source/test batches before ending a session and retain a source
patch/archive when work cannot be pushed. Update this file, not a second status ledger.
