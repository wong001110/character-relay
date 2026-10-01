# R2 source-focused production checkpoint

This review describes source after R1 `5870748009e86a741d7c39679799277ef9460b74`, not a deployed release.

## Changes

The Connector routes normalized explicit mentions/Reply/context actions through `/rooms/resolve`.
Room source records preserve original destination, edits/tombstones and permission observation
ordering. Runtime-issued selections bind requester separately from selected-source author. Character
prompt focus follows raw Reply ancestry and recent permitted evidence; inner Character Turn Director
is retired. Default Room Director remains unqualified/disabled; the Free Token Pool adapter counts
physical attempts, enforces a total deadline and never falls back to paid or legacy selection.

Confirmed response-to-source links are written in the delivery ACK/uncertainty transaction before
response scrubbing. Partial receipts remain partial and do not advance dialogue. The Connector uses
bounded concurrent work with separate per-room publication serialization and coalesced event writes.

## Evidence and limitations

Connector: 156 tests passed (including new evidence/queue/publisher checks). Source/delivery subset:
62 Python tests passed. Ruff and whole-source mypy (414 files) passed. The initial full Python run:
19 failed, 1414 passed, 7 skipped; reviewed contract-fixture and corpus fixes then passed the affected
61-test subset. Counts overlap. Full rerun, new mutation scope and cross-process PostgreSQL evidence
remain pending. All review is self-review; fake model qualification reports in tests are not real
operator/human approval.

The retired inner-Director tests were replaced by Room selection/pool/authority tests. Negative
retargeting and cross-scope cases remain. No fixture correction authorizes production behavior
changes unrelated to the accepted plan. Old selection APIs, social cognition, automatic writers,
Roast, expression preload, continuation and final draft checks remain for R3-R6; this checkpoint is
not complete retirement or live qualification.

## Reuse

Use existing discord.js SDK permission/history APIs, existing SQLAlchemy transactions and existing
Utility Gateway/HTTP providers. Reply-chain organization follows the llmcord pattern, not its
runtime or trust policy. No new supervisor, selector framework or hosted dependency is installed.

References: https://github.com/jakobdylanc/llmcord ;
https://docs.discord.com/developers/topics/threads ;
https://docs.discord.com/developers/topics/permissions .
