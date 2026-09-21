# Group-chat source and delivery verification

This is an evidence receipt, not another progress ledger. Current status is PROJECT_STATE.md.

## Revisions and scope

- Original acquired source: `efb66eda828726cfda9cda6e3b952e0ad32153fd`, tree
  `11a048a950cb0bc9b2f10a2b08c1552b416fbe00`.
- Independently arriving foundation retained: `458534bec0489583cb48d5c6d0c901ce5946da98`.
- Integrated P2a source: `53d53d0cd99f7f59b518fc367ab619ed412a10a4`, tree
  `8a88bee627c525c47f660cf80663ff990692dce5`.
- PR: #207, `feat/discord-group-chat-core-takeover`; no merge or deployment.

The P2a batch extends current-room snapshots with Reply/edit/role metadata, updates buffers on
Gateway create/update/delete events, and preserves partial/uncertain delivery receipts. Native,
webhook, asset and expression paths use the same no-blind-fallback rule. The backend checks the
exact operation/step/claim before accepting an uncertainty report and does not advance dialogue.
Existing receipt storage is reused; this slice needs no production data migration.

The newer foundation's metadata-first tracing, regression tests and fail-closed participation
persistence behavior were preserved. Its human-first alias ordering remains; explicit role
metadata is now preferred over legacy unambiguous Card inference. No display-name identity.

## Local executable evidence before reconciliation

- Original durability tests: 11 passed.
- Updated durability and additive source-contract tests: 20 passed on Python 3.13.5.
- Five seed Connector regressions failed against the original snapshot and passed after changes:
  human alias crowding, repeated-message ordering, mutable snapshots, partial receipts and lost ACKs.
- Seventeen Node behavioral tests passed against transpiled actual modules in a disposable external
  harness. The committed cases use Vitest. This local run is not a configured Vitest or Node 24 pass.
- Six manual targeted mutations were detected by assertion failures: operation binding, claim nonce,
  terminal-state guard, retained receipts, step uncertainty and operation uncertainty. Four used the
  full durability file; two used the focused receipt case after the initial runner timed out.
  No original source was mutated in place. This is not an exhaustive mutmut/Stryker score.
- Source compilation and `git diff --check` passed.

Missing local dependencies blocked full API collection (`langgraph`) and local Ruff/mypy/Vitest.
No stubs or weakened assertions were introduced to manufacture those passes.

## Configured integration

GitHub run `35599133605` reconstructs the reviewed patch, verifies its SHA256 and source tree,
reconciles the foundation and tests the resulting source commit above. Although the workflow event
is attached to a temporary transfer commit, the job records the actual checked commit/tree and
archives tracked source with the results. Use that attestation rather than assuming event HEAD.

At receipt creation, the supported Node 24 Connector typecheck, full Vitest suite and build passed;
Ruff passed. Mypy and focused Python route/integration results were still pending. The existing
complete CI is separately required for the final PR head. Do not infer completion from this receipt.

The bounded transfer used no production secrets/data, no main write and no force push. Temporary
snapshot/patch workflow and transfer parts are absent from the integrated source tree. They are
not an enduring runner, dependency or new development process.

## Still not established

No live Discord behavior, model naturalness, measured token savings, private-channel deployment
configuration, PostgreSQL contention or independent security review is claimed. Existing private
and historical data were not purged. Do not sum local and configured test counts as unique tests.

The batch does not yet implement final-draft refresh, bounded A-B-A, room budgets, explicit-note
migration, short relationship replacement, Roast retirement, complete source rehydration or Portal
observation. D01-D11 and A01-A22 remain required; a green transport slice is not programme completion.
