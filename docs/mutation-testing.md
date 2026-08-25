# Mutation Testing

Status: **required quality practice for protected decision logic; Knowledge Fabric Phase 4 adds a targeted canonical-interpretation lifecycle scope**

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
| Python | `mutmut` with pytest (`tests/test_knowledge_fabric_entity_policy.py`) | `echo_masque.knowledge_fabric_interpretation_policy` | Ubuntu CI or an installed WSL distribution |
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
# Python (Linux)
mutmut run
mutmut export-cicd-stats

# Python from Windows with an installed WSL distribution.  The wrapper copies
# the current (including uncommitted) Python source/tests to a WSL-native
# disposable directory before running mutmut, avoiding /mnt/<drive> cache I/O.
wsl.exe -d Ubuntu -- bash -lc \
  'cd /mnt/d/path/to/echo-masque && MUTMUT_COMMAND=/path/to/venv/bin/mutmut bash scripts/run_mutmut_wsl.sh --max-children 2'

# Portal
cd web
npm run test:mutation

# Discord Connector
cd connectors/discord
npm run test:mutation
```

`mutants/`, Stryker sandboxes, and local HTML reports are analysis state and are intentionally
ignored. The WSL wrapper prints `mutmut results` and CI stats before it removes its native
temporary copy, then returns the underlying `mutmut run` status. Do not apply a mutant to a dirty worktree. Resolve survivors by adding or improving
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
- Phase 3: `knowledge_fabric_ingestion_policy.py` supplies the focused mutable boundary for
  terminal job status, running-job claim/requeue decisions, source-version hash equality, and
  deterministic content-addressed artifact keys. Persistence and private S3/R2 operations remain
  covered by the Phase 3 integration suite; mutation results apply only to this deterministic
  ingestion policy module.
- Phase 4: `knowledge_fabric_interpretation_policy.py` supplies the focused mutable boundary for
  accepted resolution states, successor-only reassignment, representable interpretation states,
  and the no-automatic-Belief-promotion rule. Repository, provenance, lifecycle, and runtime graph
  boundaries remain covered by the Phase 4 integration suite; mutation results apply only to this
  deterministic interpretation policy module.
- Phases 5–6: authorization-before-ranking, epistemic filtering, and Character-context injection
  receive targeted mutation scopes.
- Phases 7–11: Projection invalidation, source/adaptor secret exclusion, Character policy, and
  privileged Portal/Connector decisions receive targeted mutation scopes as those consumers move.

The active plan records each command, result, accepted equivalent mutant, deliberate exclusion,
and remaining scope. It must not claim a mutation score for code that was not actually mutated.
