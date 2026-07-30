from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new))


replace(
    "README.md",
    "- [x] Phase 13 — Custom Test Packs, Experiment History, and persistence guardrails\n"
    "- [x] Production release gate — Railway Volume-backed SQLite, persistent Live Demo data, real Adaptive + Hybrid validation, and bounded Semantic evidence repair\n",
    "- [x] Phase 13 — Custom Test Packs, Experiment History, and persistence guardrails\n"
    "- [x] Production release gate — Railway Volume-backed SQLite, persistent Live Demo data, real Adaptive + Hybrid validation, and bounded Semantic evidence repair\n"
    "- [x] Phase 14 — Batch Experiment Matrix and Comparative Analytics\n",
)
replace(
    "README.md",
    "- [ ] Phase 14 — Batch Experiment Matrix and Comparative Analytics\n"
    "- [ ] Phase 15 — Authentication, User Isolation, and Secure Credential Vault\n",
    "- [ ] Phase 15 — Authentication, User Isolation, and Secure Credential Vault\n",
)
replace(
    "README.md",
    "Planned deliverables:\n",
    "Implemented deliverables:\n",
)
replace(
    "README.md",
    "Phase 14 does not introduce public accounts, billing, a distributed worker fleet, or a Scenario marketplace.\n",
    "Phase 14 is available through the bilingual **Matrix Lab**. The server requires an exact run-count confirmation before launch, enforces a 200-task cap, persists queue state in SQLite, and pauses interrupted work after restart. Phase 14 does not introduce public accounts, billing, a distributed worker fleet, or a Scenario marketplace.\n\n"
    "See `docs/phase-14-experiment-matrix.md` for the execution, analytics, regression, and export contracts.\n",
)
replace(
    "README.md",
    "Phase 13 and the production release gate are complete. Echo Masque now supports user-authored Scenarios, versioned Test Packs, immutable Run snapshots, Experiment History, workspace backup and restore, Railway Volume-backed SQLite, Admin-managed Adaptive Tester, and Rules, Semantic, or Hybrid judging.\n\n"
    "The retained Live Demo verifies the intended contrast under real Adaptive + Hybrid execution: Stable Ann completed the bilingual integrity pack at 100, while Drift Ann produced lower scores, FAIL results, and REVIEW cases. The next implementation phase is Phase 14 — Batch Experiment Matrix and Comparative Analytics.\n",
    "Phase 14 and the production release gate are complete. Echo Masque now supports user-authored Scenarios, versioned Test Packs, immutable Run snapshots, Experiment History, Prompt version history, controlled batch Matrices, a persistent queue, repeated-run statistics, regression comparisons, and secret-free Matrix exports.\n\n"
    "The retained Live Demo verifies the intended Stable/OOC contrast under real Adaptive + Hybrid execution. A separate retained Live Matrix validates the Phase 14 production API, Temperature variants, persisted tasks, and aggregate analytics. The next implementation phase is Phase 15 — Authentication, User Isolation, and Secure Credential Vault.\n",
)

phase14_checklist = """## Phase 14 — Batch Experiment Matrix and Comparative Analytics

### Matrix definitions and launch safety
- [x] Add owner-scoped Matrix CRUD and paginated listing
- [x] Expand Character/Prompt, Model, Temperature, Pack, Language, Tester, Judge, and repeat combinations
- [x] Preview the exact server-side task count before launch
- [x] Require the caller to confirm the same task count
- [x] Enforce a 200-task server cap
- [x] Preflight Adaptive and Semantic Admin Runtime readiness

### Persistent queue and controls
- [x] Add migration-safe Matrix and Matrix Task tables
- [x] Persist pending, running, completed, failed, and cancelled state
- [x] Add bounded concurrency
- [x] Add pause, resume, cancel remaining, and retry failed controls
- [x] Store attempt, retry, error, and provider backoff metadata
- [x] Recover interrupted running tasks as pending and pause their Matrix after restart
- [x] Keep all Subject, Adaptive, Judge, and Admin credentials outside Matrix persistence

### Prompt versions and immutable execution
- [x] Capture Prompt + Model configuration versions automatically
- [x] Preserve Provider, Base URL, Model, System Prompt, and Temperature
- [x] Add version diff, restore, and production marker
- [x] Apply selected Prompt, Model, and Temperature overrides to immutable Run snapshots
- [x] Keep previous Run snapshots unchanged after version restoration

### Analytics, regression, and exports
- [x] Aggregate mean, minimum, maximum, variance, and standard deviation
- [x] Aggregate pass, review, and failure rates
- [x] Aggregate failure types and first-breakpoint frequency
- [x] Aggregate token usage, latency, provider errors, and retries
- [x] Break down results by Character, Prompt, Model, Temperature, Language, Tester, Judge, and Scenario
- [x] Add compatible Matrix baseline regression classification
- [x] Reject misleading regression when Pack, Language, Tester, or Judge dimensions differ
- [x] Add secret-free JSON, CSV, and Markdown export

### Matrix Lab
- [x] Add a separate bilingual Matrix Lab entry from the Character Library
- [x] Add Builder, Queue, Analytics, Regression, and Prompt Version views
- [x] Add combination-count and Provider-call warnings
- [x] Add responsive desktop, tablet, and narrow-layout styling
- [x] Add typed frontend API contracts and Vitest coverage

### Automated validation
- [x] Matrix preview, task cap, and stale-confirmation tests
- [x] Deterministic repeated-run Matrix and analytics tests
- [x] Queue pause, resume, cancel, retry, and restart-recovery tests
- [x] Prompt version immutability, diff, restore, and production-marker tests
- [x] Compatible regression and secret-free export tests
- [x] Python 3.12 Ruff, strict mypy, and pytest
- [x] Python 3.13 Ruff, strict mypy, and pytest
- [x] TypeScript, Vitest, and production web build
- [x] Docker persistent-volume and container smoke
- [x] Railway live smoke

"""
replace(
    "CHECKLIST.md",
    "## Automated acceptance history\n",
    phase14_checklist + "## Automated acceptance history\n",
)
replace(
    "CHECKLIST.md",
    "- [x] Phase 13 GitHub-hosted Ruff, strict mypy, pytest, TypeScript, Vitest, production build, Docker smoke, and Railway live smoke passed\n",
    "- [x] Phase 13 GitHub-hosted Ruff, strict mypy, pytest, TypeScript, Vitest, production build, Docker smoke, and Railway live smoke passed\n"
    "- [x] Phase 14 GitHub-hosted Ruff, strict mypy, pytest, TypeScript, Vitest, production build, Docker persistence smoke, and Railway live smoke passed\n",
)
replace(
    "CHECKLIST.md",
    "Phase 13 implementation and hosted validation are complete. The persistence probe remains a required human redeploy check because ordinary CI does not redeploy the production service twice around one marker.\n",
    "Phase 14 implementation and hosted validation are complete. Manual acceptance remains for large real-provider Matrices, visual queue controls, regression interpretation, exports, and narrow-screen usability.\n",
)

manual_phase14 = """## Phase 14 priority acceptance

### Matrix Builder

- [ ] Select multiple Character Cards and Prompt versions and confirm the preview count matches the Cartesian product.
- [ ] Add Model and Temperature variants and confirm leaving either list empty preserves each card's current configuration.
- [ ] Combine English and Simplified Chinese with multiple Tester and Judge modes.
- [ ] Confirm a stale confirmation count cannot launch and a Matrix above 200 tasks is rejected.
- [ ] Confirm the Provider-call warning is visible before launching Adaptive or Semantic combinations.

### Queue controls and recovery

- [ ] Launch a Matrix with at least eight tasks and observe pending, running, completed, failed, and retry metadata.
- [ ] Pause while tasks remain and confirm no new tasks start.
- [ ] Resume and confirm pending work continues.
- [ ] Cancel remaining work and confirm already completed Runs remain available.
- [ ] Force one Provider failure, retry failed tasks, and confirm attempt/backoff metadata is understandable.
- [ ] Restart the backend during a Matrix and confirm the Matrix returns as paused with interrupted tasks pending.

### Prompt versions

- [ ] Edit a Prompt + Model card twice and confirm immutable versions appear.
- [ ] Compare two versions and inspect changed fields plus the full Prompt diff.
- [ ] Restore an old version and confirm it becomes active without rewriting old Run snapshots.
- [ ] Mark and clear a production version.
- [ ] Run a Matrix using a non-current version and confirm the frozen Run snapshot identifies that version.

### Analytics and regression

- [ ] Run at least three repeats per variant and inspect mean, min, max, variance, and standard deviation.
- [ ] Confirm pass, review, and failure rates match the underlying Runs.
- [ ] Inspect breakdowns by Character, Prompt, Model, Temperature, Language, Tester, Judge, and Scenario.
- [ ] Confirm token, latency, Provider-error, retry, failure-type, and breakpoint totals are credible.
- [ ] Compare a compatible baseline and candidate and inspect improved/no-change/regression classification.
- [ ] Compare incompatible Packs, languages, Tester modes, or Judge modes and confirm no misleading regression verdict is produced.

### Exports and interface

- [ ] Download JSON, CSV, and Markdown Matrix exports and confirm all tasks and aggregate metrics are represented.
- [ ] Search each export for Subject, Adaptive, Judge, and Admin credentials and confirm none appear.
- [ ] Inspect Matrix Lab Builder, Queue, Analytics, Regression, and Prompt Versions in English and Simplified Chinese.
- [ ] Inspect Matrix Lab at desktop, tablet, and narrow mobile widths.
- [ ] On Railway, run one retained Benchmark + Rules Matrix and one limited Adaptive + Hybrid Matrix with spending-capped keys.

"""
replace(
    "docs/manual-validation.md",
    "## Phase 13 priority acceptance\n",
    manual_phase14 + "## Phase 13 priority acceptance\n",
)

Path("scripts/phase14_docs_finalize.py").unlink()
Path(".github/workflows/phase14-docs-finalize.yml").unlink()
