# Group-chat source and delivery verification

Evidence receipt only. PROJECT_STATE.md remains the single current progress record.

## Revisions and reconciliation

Original source: `efb66eda828726cfda9cda6e3b952e0ad32153fd` (tree `11a048a950cb0bc9b2f10a2b08c1552b416fbe00`).
Newer foundation preserved: `458534bec0489583cb48d5c6d0c901ce5946da98`.
Integrated P2a source: `53d53d0cd99f7f59b518fc367ab619ed412a10a4` (tree `8a88bee627c525c47f660cf80663ff990692dce5`).
Draft PR #207; no merge, deployment or private-data purge.

The local batch was reconciled with the newly arriving foundation before publication. Its
metadata-first trace code/tests and equivalent fail-closed participation fix were preserved.
Human-first alias ordering remains; explicit deployment metadata is preferred for known role
messages, with legacy Card inference only when unambiguous. Names do not identify a role.

## Implemented surface

- Per-message Reply/edit/deployment metadata; historical Reply links survive burst reconstruction
  and appear in the role prompt when available.
- Continuous early human buffer observation; create/edit/delete/bulk-delete synchronization,
  chronological replacement, deep-copy snapshots and bounded invalidation/deletion markers.
- Shared `delivery.ts` separates definitely-unsent from partial/uncertain outcomes. Native and
  webhook chunk sends retain confirmed receipts, validate acknowledgements and prohibit blind
  whole-answer fallback after an uncertain or partial send. Asset/expression branches participate.
- Existing uncertainty endpoints accept bounded confirmed message IDs. Exact operation/step/claim
  and terminal-state checks precede mutation. Repeated reports retain receipts without advancing
  dialogue or reissuing a side effect. Existing columns are reused; no schema migration.

## Before integration: local evidence

Python 3.13.5: 11 original durability tests; updated durability/source contracts **20 passed**.
Five seed Node regressions failed on the original source and passed after changes. Expanded
Node assertions: **17 passed** against transpiled actual modules, not the configured Vitest runner.
Six selected manual mutations were caught by assertion failures (operation/nonce/state/receipt
boundaries); no original files were mutated in place. This is not a full mutmut/Stryker score.
Source compilation and whitespace checks passed. Missing local LangGraph/npm/Ruff/mypy packages
prevented the complete local gate; no stubs or weaker tests were used to manufacture a pass.

## Configured integration, actual published source

Run: `35599133605`, artifact: `10637609238`.
The workflow event was a temporary transfer commit, but the job reconstructed, reconciled and
committed the source before testing. `commit.txt` and `tree.txt` identify **53d53d0 / 8a88bee**.
The artifact archive SHA256 was verified as
`cc0abd6b3083f43249f03081224980e14dccac5cda91f98bf3deaacb7a908baa`, and its re-extracted tracked
source produced exactly the recorded Git tree locally.

| Command / scope | Observed result |
| --- | --- |
| Node 24: `npm run typecheck --prefix connectors/discord` | Passed |
| `npm test --prefix connectors/discord` | **135 passed / 21 test files** |
| `npm run build --prefix connectors/discord` | Passed |
| `python -m ruff check .` | Passed |
| `python -m mypy src` | Passed, 403 source files |
| `python -m pytest tests/test_runtime_durability.py tests/test_group_chat_source_contract.py tests/test_smart_participation_v3_route.py tests/test_character_turn_context_v3.py --tb=short` | **42 passed, 1 dependency deprecation warning** |

Do not add these counts to the local/foundation counts as unique tests. Full final-head CI is a
separate gate and cannot be inferred from this targeted integration. No source change is included
in the evidence update. Self-review only; no independent-agent security review is claimed.

`npm ci` reported **4 moderate advisories**. No audit details or production reachability analysis
were supplied by that install log. Classify affected packages and safely remediate before release;
do not force-upgrade dependencies or claim a clean dependency security audit from this run.

## Temporary tooling and remaining scope

The transfer was fixed by patch hash and baseline, limited to the existing feature branch and
normal fast-forward push, with no production credentials/data or main mutation. Temporary source,
patch-transfer workflow and parts are absent from the integrated tree. Existing CI remains.

This batch does not complete Reply-ancestor fetching/rehydration, persistent response-source links,
slow-job queue separation, send-time draft refresh, bounded A-B-A/room budgets, explicit-note and
relationship replacement, actual Roast/writer retirement, or Portal observation. All D01-D11 and
A01-A22 remain required. No live Discord/model naturalness/cost result, PostgreSQL contention
result, deployment approval or general security certification is claimed.
