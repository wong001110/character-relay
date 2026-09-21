# Character Relay — AI-Native Development Practice

This is the single coding-agent policy. The human owns product direction, authorization and
material tradeoffs; the main agent owns an evidence-backed execution strategy inside that scope.
Use the native harness before adding orchestration. Do not prescribe permanent agent roles,
mandatory delegation, a fixed phase topology, or per-file commits.

## Start here

1. Read [PROJECT_STATE.md](PROJECT_STATE.md): baseline, accepted work, implementation status,
   blockers and the next action. Check the actual branch, HEAD, merge-base and worktree first.
2. Read only the active plan linked there and the relevant part of
   [docs/architecture.md](docs/architecture.md).
3. Inspect the actual source, schemas, call sites and proving tests before changing behavior.
   Use [docs/developer/README.md](docs/developer/README.md) for existing commands and
   [docs/contracts/README.md](docs/contracts/README.md) for specialized constraints.

Do not resume a historical roadmap or an old branch merely because it has incomplete checkboxes.
An open PR is not merged code. Repository state is project truth; conversation memory is not an
implementation receipt. Report a conflict instead of inventing a compatible implementation.

## Authority and scope

- The user's current instruction sets the permitted work. An accepted design is not permission
  to code, deploy, spend money, migrate production data or merge when those actions are excluded.
- Source/tests establish what exists. The accepted active plan establishes what should change.
  Its explicit decisions supersede contradictory old designs, not unrelated safety contracts.
- A documentation-only task must not change source, tests, schemas, dependencies, CI execution,
  deployment configuration or live behavior. Do not create empty implementation scaffolds.
- Never invent endpoints, metrics, environment variables, statuses or implemented capabilities.
  Label proposed contracts and initial budget values as planned until wired and verified.
- Preserve authentication, owner/room/character scope, credential isolation, Public Demo read-only
  enforcement, media provenance, tool authorization, bounded execution and delivery integrity.
- Model output, imported cards, remembered text and other bots' messages are data/proposals, never
  authority to read more data or execute additional effects. Relationship closeness grants nothing.
- No secrets, raw private captures or credential-derived material in Git, logs or evidence reports.
- Do not add a coding-agent runtime, memory database, ledger, bootstrap dependency or generated
  wiki requirement to this product repository. Execution-environment state belongs outside it.

## Execute in coherent, revisable phases

Before a non-trivial change, identify the intended outcome, boundaries, inspected paths, affected
call sites, likely failure modes and acceptance evidence. Choose the smallest coherent slice that
can demonstrate the behavior. The plan's checkpoints may be split, combined or reordered when
justified; preserve every accepted requirement and dependency.

Use native tools and selective delegation. Delegate only bounded, non-overlapping work with a
clear benefit. The main agent integrates and reviews it and decides **proceed / repair / blocked**.
Self-review must not be described as independent verification. Missing tools are not a pass.
Routine in-scope decisions do not require repeated approval. Escalate changed product semantics,
new recurring costs, irreversible data loss, new trust boundaries or unavailable required evidence.

Run focused checks while developing, then proportional integration checks at the phase boundary.
For protected decisions, use the applicable bounded mutation scope in
[docs/mutation-testing.md](docs/mutation-testing.md), or record why unavailable and the remaining
proof gap. Test scope, counterexamples and survivor disposition matter more than a headline score.
Do not weaken tests to hide a regression; distinguish intentionally retired behavior from invariants.

Security starts in design. Use synthetic data and authorized isolated fault/adversarial tests for
changed boundaries; never attack production merely because a task requests Red Team review.
UI work must use real API data and the existing UI/accessibility contracts. Browser/E2E checks
are appropriate for changed user journeys; a build alone is not proof of a working journey.

Commit reviewable, phase-sized results after relevant checks. Do not commit every file or run the
entire suite after every small edit. A blocked checkpoint may be preserved honestly without being
called complete. Prefer squash merge only when the user authorizes a merge; do not merge by default.

## Project state and completion

PROJECT_STATE.md is the only current progress/handoff record. Update it after coherent work with
status, changed boundaries, command/result or evidence reference, limitations and the next action.
Keep acceptance requirements in the active plan and structure/ownership in architecture.md; avoid
three copies of the same phase log. Update only affected documentation.

Completion requires production-path wiring, meaningful behavior evidence, integrated diff review
and removal of replaced consumers/flags/docs. A class, mock or green isolated unit test alone is
not completion. Preserve immutable source evidence and authorized historical data; removing an old
runtime does not authorize a destructive purge. Review runtime leftovers and explain any remaining
migration blocker instead of leaving two indefinite implementations.

Report actual checks, unrun checks, self/independent review and unresolved risks separately.
Quality and cost claims require a same-model comparison; synthetic success is not live acceptance.
See [CHECKLIST.md](CHECKLIST.md) and the PR template for the final evidence record.
