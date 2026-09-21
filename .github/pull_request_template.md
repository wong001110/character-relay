## Outcome and scope

What accepted requirement or defect is addressed? Is this documentation, implementation or release
work? State what is deliberately not changed. Do not describe planned behavior as implemented.

## Baseline and evidence

- Base/HEAD or tested revision:
- Active plan requirement/scenario IDs, where applicable:
- Actual source/contracts inspected:
- Verification commands, results and artifact references:
- Self-review / independent verification (state which actually occurred):

## Boundaries and retirement

Explain affected identity/data/tool/delivery/privacy boundaries, migrations and backward compatibility.
List replaced consumers/flags/routes/prompts/docs removed, or explicit remaining blockers. Preserve
historical data without preserving obsolete runtime behavior. UI data must be real, not invented.

## Limits and takeover

Record unavailable/unrun tests, live acceptance limitations, new cost/dependency decisions and
residual risks. Update PROJECT_STATE.md with the next concrete action; do not create a parallel ledger.

Documentation-only changes should prove the changed-path allowlist and unchanged runtime trees,
validate links/status consistency, and not claim application test results. Merge and production
rollout require the corresponding user authorization.
