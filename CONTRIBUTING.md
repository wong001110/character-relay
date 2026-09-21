# Contributing

Follow [AGENTS.md](AGENTS.md), the single AI-Native Development policy, and begin from
[PROJECT_STATE.md](PROJECT_STATE.md). Use [architecture.md](docs/architecture.md) to locate the
owning service and [the developer guide](docs/developer/README.md) for setup and check commands.

Keep PRs coherent and scoped. An accepted plan is not evidence of implemented behavior. Explicit
documentation-only work changes neither feature code nor runtime wiring. Later implementation
must include behavior evidence and remove replaced consumers rather than retain a second system.

Use native tools and optional bounded delegation; no generated wiki or fixed agent-role workflow
is required. Keep secrets and raw private captures out of commits. Protected boundaries, Public
Demo read-only behavior and evaluation approval rules remain server-owned.

For UI changes, follow the existing UI/data/accessibility contracts and approved references where
applicable. Reference images determine composition, not fabricated product metrics or endpoints.

Before requesting review, use [CHECKLIST.md](CHECKLIST.md) and the PR template. Report checks actually
run, missing verification, deviations and self versus independent review. Commit coherent batches;
do not create per-file commits. Squash merge requires a separate user merge instruction.
