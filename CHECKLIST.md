# Echo Masque Delivery Checklist

## Phases 0–15

- [x] Python-first evaluation engine, persistence, FastAPI, and React interface
- [x] Character Cards, Prompt + Model targets, Live Test Room, and reports
- [x] Benchmark and Adaptive testing
- [x] Rules, Semantic, and Hybrid judging
- [x] English and Simplified Chinese interface and tests
- [x] Custom Scenarios, Test Packs, Experiment History, and immutable snapshots
- [x] Batch Experiment Matrix, Prompt versions, and comparative analytics
- [x] Railway Docker deployment with persistent SQLite volume
- [x] Authentication, invitations, roles, HttpOnly Sessions, and owner isolation
- [x] encrypted Character and shared Runtime Credential Vault
- [x] persistent quotas, Audit Events, account export/deletion, and legacy claim
- [x] Phase 15 Production multi-account, Vault-rotation, and redaction acceptance

## Phase 16 — AI-assisted Authoring, Calibration, and Evaluation Engineering

### 16A — Reviewable authoring foundation

- [x] Migration-safe Scenario Draft persistence
- [x] Migration-safe Test Pack Draft and ordered item persistence
- [x] Manual/AI provenance, review notes, revisions, rejection, and approval
- [x] Draft resources remain outside every Trial and Matrix execution path
- [x] Scenario Draft approval creates a formal Scenario
- [x] Test Pack Draft approval requires approved Scenario Draft references
- [x] Approved Drafts become immutable provenance records
- [x] Secret-free Authoring Archive merge/replace restore
- [x] Owner isolation, account deletion, and legacy workspace claim

### 16B — AI-assisted authoring

- [x] Admin-managed Authoring Runtime profile
- [x] encrypted Authoring Runtime credential
- [x] strict structured Scenario/Test Pack generation
- [x] one bounded correction for invalid model output
- [x] duplicate, risk, and coverage heuristics
- [x] English and Simplified Chinese generation
- [x] bilingual Authoring Lab
- [x] generated resources remain Drafts until explicit approval

### 16C — Human-controlled Calibration Datasets

- [x] owner-scoped Calibration Dataset and Case persistence
- [x] expected PASS, FAIL, and REVIEW labels
- [x] exact contiguous Subject evidence validation
- [x] manual Cases and completed Run Turn import
- [x] approved Dataset immutability and explicit next-version creation
- [x] secret-free Archive export/import with cross-account ID remapping
- [x] bilingual Calibration Lab
- [x] account deletion and legacy claim integration

### 16D — Judge Evaluation Analytics

- [x] Rules, Semantic, and Hybrid predictions against approved Datasets
- [x] immutable Evaluation Snapshots and per-Case predictions
- [x] confusion matrix, accuracy, precision, recall, and Macro F1
- [x] false-positive and false-negative rates
- [x] Rules/Semantic agreement and disagreement
- [x] breakdowns by failure type, language, Scenario category, and Character
- [x] partial Snapshots when Semantic Runtime is unavailable
- [x] bilingual Judge Analytics UI

### Runtime Prompt Inspector

- [x] exact current Runtime System Message inspection
- [x] Provider, Model, Temperature, active Prompt Version, and config hash
- [x] copy-to-clipboard
- [x] plain text export
- [x] Markdown export
- [x] full secret-free JSON export
- [x] OpenAI messages JSON export
- [x] runtime equivalence, owner isolation, and redaction tests

### 16E — Rubric comparison and coverage

- [x] same frozen Dataset ID/version comparison requirement
- [x] accuracy, Macro F1, false-positive, and false-negative deltas
- [x] six Semantic dimension deltas
- [x] per-Case prediction changes
- [x] coverage across identity, memory, instruction resistance, capability honesty, persona, and language
- [x] missing and weak risk reporting
- [x] coverage gaps may create AI Drafts but cannot approve them
- [x] bilingual Rubric & Coverage Lab

### 16F — Templates, sharing, quotas, and release gate

- [x] reusable bilingual identity/memory templates
- [x] reusable instruction/capability templates
- [x] reusable persona/language templates
- [x] template instantiation creates Drafts only
- [x] versioned secret-free Evaluation Share Bundle
- [x] formal Scenario and Test Pack export
- [x] Share Bundle import creates Drafts only
- [x] Share Bundle owner and credential redaction
- [x] daily AI Authoring generation quota
- [x] daily Judge Evaluation Case quota
- [x] daily template and Share Bundle import quota
- [x] server-side Share Bundle asset cap
- [x] bilingual Templates & Sharing Lab
- [x] restart-persistent quota tests
- [x] Phase 16 migration and release documentation
- [x] retained GitHub Actions Production acceptance workflow
- [x] Python 3.12 Ruff, strict mypy, and pytest
- [x] Python 3.13 Ruff, strict mypy, and pytest
- [x] TypeScript, Vitest, and Production web build
- [x] Docker persistent-volume and container smoke
- [x] Railway smoke
- [ ] Phase 16 Production live acceptance after merge
- [ ] Phase 16 Tracker closed as completed

## Remaining general manual follow-up

- [ ] Narrow mobile-browser acceptance
- [ ] Validate a separately hosted external chatbot adapter
- [ ] Verify the local launcher on Windows and macOS/Linux

Phase 16 implementation is complete. Final completion requires the retained Production live acceptance against Railway and closure of Issue #45.
