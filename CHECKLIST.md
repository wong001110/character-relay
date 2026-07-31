# Echo Masque Delivery Checklist

## Phases 0–7 — Foundation and release baseline

- [x] Product contract, roadmap, and terminology
- [x] Installable Python package and FastAPI service
- [x] Deterministic trial engine and four test suites
- [x] Prompt-model and external target adapters
- [x] SQLite persistence, HTTP API, replay, reports, and comparisons
- [x] React/TypeScript observation interface
- [x] Recursive secret redaction and release automation

Manual follow-up:

- [ ] Narrow mobile acceptance
- [ ] Validate a separately hosted chatbot adapter
- [ ] Broad browser acceptance

## Phases 8–11 — Character testing, Adaptive pressure, deployment, and language

- [x] User-owned Character Cards and Live Test Room
- [x] Prompt + Model creation and editing
- [x] Persisted Tester, Subject, Judge, evidence, and breakpoint events
- [x] Benchmark and Adaptive Tester modes
- [x] Watch and Fast observation modes
- [x] Cross-platform local launcher
- [x] Railway Docker deployment and persistent SQLite smoke
- [x] English and Simplified Chinese interface and Test Language
- [x] Language-aware catalogs, judging, reports, and comparisons

Manual follow-up:

- [ ] Verify the launcher on Windows and macOS/Linux
- [ ] Confirm SQLite data survives a real Railway redeploy

## Phase 12 — Admin Runtime, Hybrid Judge, and scalable Character Library

- [x] Persistent non-secret Adaptive/Judge configuration
- [x] Independent Rules and grounded Semantic Judges
- [x] Hybrid disagreement becomes `REVIEW`
- [x] Strict structured and exact-evidence Semantic validation
- [x] Scalable Character Library search, filters, sorting, and pagination
- [x] Character Card editing preserves target and credential association
- [x] Python 3.12/3.13, Web, Docker, and Railway validation

## Phase 13 — Custom Test Packs, Experiment History, and persistence guardrails

- [x] Owner-scoped custom Scenario CRUD
- [x] Versioned, ordered Test Pack CRUD
- [x] Immutable Character, Target, Pack, and Scenario snapshots
- [x] Experiment History, rerun lineage, reports, and baselines
- [x] Storage diagnostics and persistence probes
- [x] Secret-free workspace export/import
- [x] Python 3.12/3.13, Web, Docker, and Railway validation

Manual follow-up:

- [ ] Run and inspect a real multilingual custom Test Pack
- [ ] Export and import a real workspace archive
- [ ] Confirm Storage Diagnostics and persistence probe after Railway redeploy

## Phase 14 — Batch Experiment Matrix and Comparative Analytics

- [x] Owner-scoped Matrix CRUD and task-count confirmation
- [x] Persistent queue, bounded concurrency, pause/resume/cancel/retry
- [x] Provider backoff and restart recovery
- [x] Prompt version capture, diff, restore, and Production marker
- [x] Repeated-run statistics and dimension breakdowns
- [x] Compatible Matrix baselines and regression classification
- [x] Secret-free JSON, CSV, and Markdown exports
- [x] Bilingual Matrix Lab
- [x] Python 3.12/3.13, Web, Docker, and Railway validation

## Phase 15 — Authentication, User Isolation, and Secure Credential Vault

### Identity and Sessions

- [x] User, Session, Invitation, Credential, Audit, rate-limit, and quota records
- [x] Argon2 password hashing
- [x] Register, login, logout, current-user, Session listing, and Session revocation APIs
- [x] Opaque expiring server-side Sessions
- [x] HttpOnly SameSite browser cookie
- [x] Bearer-token API compatibility
- [x] Production bootstrap Admin account
- [x] Invitation-controlled Production registration
- [x] `user` and `admin` role model

### Server-enforced workspace isolation

- [x] Remove caller-selected Production identity headers
- [x] Session-derived ownership for Character Cards and Targets
- [x] Session-derived ownership for Scenarios and Test Packs
- [x] Session-derived ownership for Runs, Reports, reruns, and baselines
- [x] Session-derived ownership for Matrices and Prompt versions
- [x] Session-derived ownership for storage probes, exports, and imports
- [x] Cross-user read, update, delete, rerun, baseline, Matrix, and export tests
- [x] Explicit, idempotent legacy `local-user` workspace claim

### Role-based Admin boundary

- [x] Authenticated Admin dependency
- [x] Role-protected Admin Runtime APIs
- [x] Role-protected storage and lifecycle controls
- [x] Safe role promotion and demotion with final-Admin protection
- [x] Legacy Admin token retained only as a non-Production migration fallback

### Secure credential vault

- [x] Fernet encryption before credentials enter SQLite
- [x] Character provider credential persistence
- [x] Adaptive Tester and Semantic Judge credential persistence
- [x] Versioned master-key metadata
- [x] Multi-key decryption and primary-key rotation
- [x] Redacted credential status responses
- [x] Exclude plaintext and encrypted material from exports, snapshots, events, reports, and logs
- [x] Production Character credential status reports `vault`

### Quotas and abuse controls

- [x] Persistent authenticated request buckets
- [x] Persistent login failure windows and temporary blocking
- [x] Per-user Character, Scenario, Pack, Run, and Matrix limits
- [x] Daily Matrix task limit
- [x] Per-user Run and Matrix concurrency limits
- [x] Total workspace-record limit
- [x] `429` and `Retry-After` behavior

### Audit and account lifecycle

- [x] Append-only redacted Audit Events
- [x] Audit authentication, Session, credential, Admin, import/export, deletion, and role changes
- [x] Single-use invitation creation, acceptance, expiry, and revocation
- [x] Secret-free user-scoped account export
- [x] Destructive account deletion with email and confirmation phrase
- [x] Workspace, Session, credential, and rate-limit cleanup
- [x] User anonymization while retaining Audit referential integrity

### Authenticated UI

- [x] Bilingual sign-in and invitation registration
- [x] Workspace loading gated behind authenticated Session
- [x] Browser owner headers and persistent Admin tokens removed
- [x] Session/device management
- [x] Account export and deletion
- [x] Admin invitations and user-role management
- [x] Audit inspection, legacy workspace claim, and credential rotation
- [x] Session-authenticated Admin Runtime settings

### Migration and Production release gate

- [x] Backup-first idempotent Phase 15 migration script
- [x] Railway environment, quota, migration, deletion, and key-rotation documentation
- [x] Automated multi-account isolation and Vault-rotation acceptance script
- [x] GitHub Actions workflow with secret-free JSON evidence
- [x] Automatic post-merge wait for the authenticated Railway deployment
- [x] Pull-request Python 3.12 Ruff, strict mypy, and pytest
- [x] Pull-request Python 3.13 Ruff, strict mypy, and pytest
- [x] Pull-request TypeScript, Vitest, and Production web build
- [x] Pull-request Docker persistent-volume and container smoke
- [x] Pull-request Railway smoke
- [x] Main-branch Phase 15 live multi-account and Vault-rotation acceptance

## Phase 16 — AI-assisted Authoring, Calibration, and Evaluation Analytics

### 16A — Reviewable authoring foundation

- [x] Migration-safe Scenario Draft persistence
- [x] Migration-safe Test Pack Draft and ordered item persistence
- [x] Manual/AI provenance, review notes, revisions, and status metadata
- [x] Owner-scoped Scenario Draft CRUD, reject, revise, and approve APIs
- [x] Owner-scoped Test Pack Draft CRUD, reject, revise, and approve APIs
- [x] Draft resources remain outside formal Scenario/Test Pack execution paths
- [x] Scenario Draft approval creates a normal Phase 13 Scenario
- [x] Test Pack Draft approval requires approved Scenario Draft references
- [x] Approved Draft provenance becomes immutable
- [x] Append-only Audit Events for Draft and archive operations
- [x] Secret-free Authoring Archive export and merge/replace import
- [x] Approved archive references require formal Workspace resources first
- [x] Account deletion removes Scenario Drafts, Pack Drafts, and Draft items
- [x] Legacy `local-user` claim includes authoring resources
- [x] Cross-user isolation, persistence, approval-boundary, archive, and deletion tests
- [x] Python 3.12/3.13 Ruff, strict mypy, and pytest
- [x] TypeScript, Vitest, Production web build, Docker, and Railway smoke

### 16B–16F — Remaining

- [ ] Admin-managed Authoring Runtime and encrypted credential
- [ ] Strict AI Scenario and Test Pack drafting with bounded correction
- [ ] Duplicate, risk, and coverage heuristics
- [ ] English and Simplified Chinese Authoring Lab
- [ ] Calibration Datasets and human-approved Calibration Cases
- [ ] Judge confusion matrix, agreement, false-positive, and false-negative analytics
- [ ] Rubric-version comparison and dimension coverage reports
- [ ] Reusable templates, secret-free sharing, quotas, and Production release gate

## Automated acceptance history

- [x] Phases 8–14 passed their GitHub-hosted Python, Web, Docker, and Railway gates
- [x] Phase 15 pull-request validation passed
- [x] Phase 15 Production security gate passed after merge
- [x] Phase 16A reviewable authoring foundation passed pull-request validation

Phase 16 is in progress. Phase 16A establishes the non-executable Draft and human-approval boundary; AI generation begins in Phase 16B.