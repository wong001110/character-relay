# R3: delivered interactions and source-bound publication

Date: 2026-10-01. Source parent: `2c7ce413f4c6930fbb8ee837978f0482355849dc`.
Current status/next work belongs only in `PROJECT_STATE.md`.

## Changed boundaries

- The server rejects stateless Social Turn execution. Claimed operation scope/cursor determine
  participants and attempts; the Connector cannot replace the persisted requester or queue.
- A-B-A is allowed within 3 distinct roles, 6 visible turns and 2 turns per role. Selected human
  requests precede optional continuation. Ignored/undelivered drafts never advance dialogue.
- Generation attempts have a separate 12-attempt interaction ceiling. Actual provider HTTP
  attempts (including retries/repairs) are transactionally bounded at 24 per operation, and
  60 per requester / 120 per room per fixed ten-minute window. These are initial limits,
  not calibrated cost claims. Owner/operation changes cannot reset a room window.
- Preflight reserves the persisted draft atomically. It rechecks raw source identity/version,
  current deployment/destination and permissions. Relevant changes allow one tool-free plain
  text refresh; another change is blocked/dropped. Direct failure is not semantic NONE.
- Current raw evidence is fetched through discord.js in the same channel/native Thread. Explicit
  deletion or lost visibility suppresses publication. Display-name/timestamp enrichment alone
  does not spend a refresh; text, identity, Reply or media changes do.
- Publication needs a recent server-issued preflight stamp and conditional delivery claim.
  Competing nonces cannot both claim a generated step on SQLite or PostgreSQL. Uncertain effects
  are not replayed. Restart during refresh fails the draft rather than replaying the tool loop.

## Checks

Recovered R2 full baseline: 1,433 passed, 7 skipped. Earlier modified runs exposed fixture
mismatches for the newly required preflight and stateless-route retirement; these were corrected
without removing authorization, capture deduplication or provenance assertions.

Connector: typecheck, 162 tests / 25 files, build passed. Python mypy: 418 sources passed.
Whole-tree Ruff passed. Full Python: **1,457 passed, 7 skipped, 11 warnings** on Python 3.13.5.
This is not a claim of green remote CI. Source changes after evidence need affected checks rerun.

Eight bounded manual mutations, each preceded by the exact unmutated test:

| Guard changed | Result |
| --- | --- |
| Remove writable-destination requirement | killed |
| Invert source-content comparison | killed |
| Remove one-refresh limit | killed |
| Remove human priority over optional continuation | killed |
| Remove generated-state compare-and-set during delivery claim | killed |
| Raise per-operation attempt cap to bypass the specified ceiling | killed |
| Put owner in the room-budget key to allow owner switching | killed |
| Remove target-source binding | killed |

All eight were applied and executed; zero survivors, tool errors or timeouts in this bounded
selection. This is manual targeted fault testing, not a repository-wide mutation score.

## Remaining acceptance boundary

Review was performed by the implementing agent. No independent review, live provider/Discord
quality, measured savings or PostgreSQL concurrency claim is made from SQLite checks. Ordinary
CI must test the exact pushed head. The existing live qualification switch stays opt-in; the user
will run real tests after implementation. R4/R5 still own explicit-memory/expression work and
old-composition/API/UI deletion. No merge, deployment or production purge occurred.
