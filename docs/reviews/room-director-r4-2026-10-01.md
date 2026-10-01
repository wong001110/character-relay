# R4: explicit recall and intent-first expressions

Date: 2026-10-01. Parent: `e7d4731519047fccda25078dfd44354a8ca79127`.
This is a coherent implementation checkpoint, not a complete refactor or deployment receipt.

## Changed boundaries

- Explicit notes have owner/card/room/subject/actor scope, current source fingerprints,
  bounded size/count, optimistic version checks and content-free creation receipts. Ordinary
  members may save their own literal source excerpts, not someone else's inferred preferences.
  Forget removes content; delayed create retries cannot resurrect it. Source edits/deletes
  invalidate derived notes. Authored operator notes use a distinct authenticated API.
- Actual Character context includes only relevant small notes. `memory.search` reads notes;
  `conversation.search` reads permitted raw messages, filters scope in SQL before ranking,
  bounds/deduplicates results and returns source identity. No Episode-summary scope shortcut.
- Conversation media recall now requires a current source fingerprint and explicit Reply
  link in the same currently readable room. An asset URI is not evidence of perception.
- Character output requests expression intent/emotion, not catalog resources. Runtime lazily
  resolves sparse metadata after generation with current scope checks before/after lookup.
  Missing/weak matches omit the expression or use the role's text fallback. Only actual
  acknowledged delivery records resource usage. No expression query embedding.
- Tool selection is lightweight and bounded; an absent query preserves assigned reads but
  does not enable effects. Knowledge dense search reads prebuilt permitted indices only.
  Provider/model/dimension/version namespace, current source hash and current grants must
  all match. Cold indices/query failures retain sparse results; queries never backfill them.
- Old expression hybrid persistence and unused dense formatting are removed. The broader
  legacy Planner/cognitive composition, settings, endpoints and Portal still require R5.

## Verification

Python 3.13.5 / SQLAlchemy 2.0.50, local offline environment:

| Check | Actual result |
| --- | --- |
| Full `python -m pytest` | 1,514 passed, 7 skipped, 6 warnings |
| `python -m ruff check .` | passed |
| `python -m mypy src` | passed, 424 source files |
| Connector typecheck / tests / build | passed, 162 tests in 25 files |
| Bounded manual mutation | 8 executed, 8 killed on final run |

Initial full runs exposed a real missing-trigger read-tool regression and obsolete candidate/
repair-prompt fixtures. The read-tool behavior was fixed without permitting effects. Format
repair keeps the existing 500-character contract rather than relaxing its test. Old ignored
`test_utility_gateway_phase2.py` imported a nonexistent module even on the parent: the permanently
ignored dead test and its ignore configuration were removed, not turned into a stubbed runtime.
Actual Utility Gateway/Free Pool suites remain exercised.

Mutation scope: own-source note authority, stale note version, post-forget creation receipt,
current expression grants, weak positive expression rank, full embedding space identity,
current corpus grants, and avoiding provider calls for cold indices. Each unmutated counterpart
passed first. Initial 6/8 kills left two gaps: direct repository replay-after-forget and a
nonempty weak expression match. Both tests were strengthened, not waived; final 8/8 killed.
This is targeted manual mutation and self-review, not exhaustive mutation or independent review.

The isolated evidence bundle binds the source tree and exact commands. Counts overlap and
are not additive. Live Discord/provider quality and actual production index/reset behavior
remain user-owned later validation. No live migration, merge or deployment was performed.
