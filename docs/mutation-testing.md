# Mutation Testing

Status: **required quality practice for protected decision logic; Knowledge Fabric Phase 2 adds its first targeted authorization/lifecycle scope**

Mutation testing evaluates whether tests detect a small semantic change in production code. It
does not replace ordinary unit, integration, migration, authorization, or live-deployment tests.
It complements line/branch coverage: execution coverage alone does not show that an assertion
would reject a changed behavior.

## Policy

- Use mutation testing for changed authorization, ownership, scope, lifecycle, safety,
  persistence-invariant, and deterministic domain-decision code when the configured scope covers
  it.
- Start with a small, directly tested module for a new subsystem. Expand the configured scope only
  after its tests are deterministic and fast enough to make mutant results actionable.
- A surviving mutant is an investigation item, not an automatic request to add a white-box test.
  Prefer a behavior-level test that explains the missing contract.
- Classify every reviewed survivor as killed, equivalent, timeout, or tooling/compile failure.
  Equivalent-mutant and exclusion decisions require a short rationale in the phase plan or PR;
  no mutation pragma or broad glob may hide an authorization or scope decision without that
  evidence.
- Phase 1 records baselines and proves runner reproducibility. It deliberately sets no repository-
  wide percentage target. Subsequent protected scopes must not introduce an unreviewed,
  non-equivalent survivor or regress their accepted baseline.
- Mutation runs are intentionally not added to the ordinary push/PR CI matrix. They run in the
  scheduled/manual workflow and as targeted phase checks, because full mutation analysis is much
  more expensive than ordinary unit tests.

## Supported runners

| Surface | Runner | Initial bounded scope | Where to run |
| --- | --- | --- | --- |
| Python | `mutmut` with pytest (`tests/test_knowledge_fabric_policy.py`) | `echo_masque.knowledge_fabric_policy` | Ubuntu CI or an installed WSL distribution |
| Portal | StrykerJS with Vitest and TypeScript checking | `web/src/portalEnvironment.ts` | Node 22+ |
| Discord Connector | StrykerJS with Vitest and TypeScript checking | `connectors/discord/src/audiencePreflight.ts` | Node 24.17+ |

The initial modules are runner smoke/baseline scopes, not a claim that they are the only parts of
the product that require mutation testing. Each Knowledge Fabric phase expands the relevant scope
only after it has a focused, fast test boundary.

## Commands

Python requires a platform with `fork` support. The scheduled GitHub workflow uses Ubuntu; WSL is
also supported. Native Windows does not support mutmut execution, so run its scope under WSL or
CI. Portal and Connector reports remain platform-specific Stryker evidence.

```bash
# Python (Linux or WSL)
mutmut run
mutmut export-cicd-stats

# Portal
cd web
npm run test:mutation

# Discord Connector
cd connectors/discord
npm run test:mutation
```

`mutants/`, Stryker sandboxes, and local HTML reports are analysis state and are intentionally
ignored. Do not apply a mutant to a dirty worktree. Resolve survivors by adding or improving
behavioral tests, then re-run the same bounded scope. A timeout or compile failure is not evidence
that the mutant was killed.

## Knowledge Fabric gates

- Phase 1: install/configure the runners, prove the three bounded commands on their supported
  platform, and record the initial reports without a global score threshold.
- Phase 2: `knowledge_fabric_policy.py` supplies the focused mutable boundary for global-library
  Super Admin restriction, explicit Server Administrator membership, Public Demo exclusion,
  grant-before-access, overlay precedence, and user-only lifecycle/claim rules. Repository/API
  integration remains covered by the Phase 2 regression suite; mutation results apply only to
  this deterministic policy module.
- Phases 3–6: version/job idempotency, canonical/runtime-entity resolution, authorization-before-
  ranking, epistemic filtering, and Character-context injection receive targeted mutation scopes.
- Phases 7–11: Projection invalidation, source/adaptor secret exclusion, Character policy, and
  privileged Portal/Connector decisions receive targeted mutation scopes as those consumers move.

The active plan records each command, result, accepted equivalent mutant, deliberate exclusion,
and remaining scope. It must not claim a mutation score for code that was not actually mutated.
