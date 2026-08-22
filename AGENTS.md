# Character Relay — AI Coding Agent Contract

Character Relay uses AI-assisted development across parallel branches. Do not rely on chat memory or plausible inference when repository evidence is available.

## Required reading before coding

1. `docs/ai-agent-development-workflow.md`
2. `openwiki/quickstart.md` if it exists, then only the relevant generated pages
3. `docs/agent-handoff.md` and `docs/README.md`
4. task-relevant canonical docs/status/decision files
5. current source/types/tests for the subsystem
6. for UI work: `docs/ui-ux-contract.md`, `docs/ui-component-library.md`, `docs/ui-page-migration-plan.md`, and the approved reference image when one exists

## Non-negotiable grounding rules

- Never invent an endpoint, field, status, metric, limit, config key, or database behavior.
- Never treat generated UI reference text/numbers as product data.
- Never assume an open/stacked PR is already on `main`.
- Never treat OpenWiki output as stronger evidence than code/tests/canonical contracts.
- When sources conflict, surface the conflict instead of silently choosing a plausible answer.
- Preserve scope/authority/security boundaries; do not broaden user/server/character visibility by inference.
- Do not expose secrets or credentials in code, logs, docs, tests, or wiki output.
- Keep PRs scoped and avoid unrelated rewrites.

## Before implementation

State the evidence map you are using: source files/types, canonical docs, tests, and UI reference (if any). Identify invariants that must remain unchanged.

## Before completion

Run relevant checks, review the diff for unrelated changes, update canonical status/decision docs if architecture changed, and record intentional deviations in the PR description.

<!-- OPENWIKI:START -->
## OpenWiki orientation

This repository uses OpenWiki as a generated orientation/synthesis layer for coding agents. If `openwiki/quickstart.md` exists, start there and trace important claims back to the cited source paths before editing behavior.

The stable OpenWiki generation brief is `openwiki/INSTRUCTIONS.md`. Generated wiki pages are not canonical product contracts and should normally be refreshed from updated `main` in a dedicated documentation pass after architectural changes are merged.
<!-- OPENWIKI:END -->
