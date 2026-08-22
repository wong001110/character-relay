# Character Relay — AI Coding Agent Contract

Character Relay uses AI-assisted development across parallel branches. Do not rely on chat memory or plausible inference when repository evidence is available.

## Required reading before coding

1. `docs/ai-agent-development-workflow.md`
2. `docs/active-development-plan.md` when it exists and names the current branch
3. `openwiki/quickstart.md` if it exists, then only the relevant generated pages
4. `docs/agent-handoff.md` and `docs/README.md`
5. task-relevant canonical docs/status/decision files
6. current source/types/tests for the subsystem
7. for UI work: `docs/ui-ux-contract.md`, `docs/ui-component-library.md`, `docs/ui-page-migration-plan.md`, and the approved reference image when one exists

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

State the evidence map you are using: source files/types, canonical docs, tests, and UI reference (if any). Identify invariants that must remain unchanged. When an active development plan applies, identify the current phase and keep the change inside that phase's scope and commit gate.

## Phased branch execution

When `docs/active-development-plan.md` names the current branch, it is the branch-local execution and takeover record. Update its phase status, evidence, validation, and handoff notes as work progresses. It does not outrank source/tests or canonical product contracts.

- Work in coherent phase-sized batches. Do not commit or run the full validation suite after every small file edit.
- Run focused checks after a coherent implementation batch and the phase's relevant complete checks before its commit gate.
- Create at most one implementation commit per phase. Fix validation failures before that commit instead of producing checkpoint/fixup commits.
- Sub-agents may perform bounded research, verification, testing, or editing tasks. The main agent owns scope, evidence reconciliation, shared-tree integration, diff review, validation decisions, and the phase commit.
- Sub-agents do not independently commit shared work unless the active plan explicitly delegates a separate branch and commit boundary.
- Before changing phases, leave the active plan usable by an agent with no chat history.

## Before completion

Run relevant checks, review the diff for unrelated changes, update canonical status/decision docs if architecture changed, and record intentional deviations in the PR description.

<!-- OPENWIKI:START -->
## OpenWiki orientation

This repository uses OpenWiki as a generated orientation/synthesis layer for coding agents. If `openwiki/quickstart.md` exists, start there and trace important claims back to the cited source paths before editing behavior.

The stable OpenWiki generation brief is `openwiki/INSTRUCTIONS.md`. Generated wiki pages are not canonical product contracts and should normally be refreshed from updated `main` in a dedicated documentation pass after architectural changes are merged.
<!-- OPENWIKI:END -->
