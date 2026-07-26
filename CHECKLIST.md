# Echo Masque Delivery Checklist

## Phase 0 — Product contract
- [x] Product purpose and terminology documented
- [x] MVP scope and exclusions documented
- [x] Delivery phases created as GitHub issues

## Phase 1 — Python foundation
- [x] Installable Python package
- [x] FastAPI health endpoint
- [x] Environment-based settings
- [x] Domain primitives
- [x] Automated Python tests
- [x] CI workflow

## Phase 2 — Deterministic trial engine
- [x] Target protocol and reset lifecycle
- [x] Stable and Fragile deterministic targets
- [x] Four deterministic test suites
- [x] Rule-based evidence and verdicts
- [x] First breakpoint detection
- [x] CLI demo runner
- [x] Unit and integration tests

## Phase 3 — Prompt-model target
- [x] OpenAI-compatible provider
- [x] Safe credential handling
- [x] Retry, timeout, usage, and latency metadata
- [x] Offline mock provider tests

## Phase 4 — Persistence and API
- [x] SQLite persistence
- [x] Target and trial endpoints
- [x] Trial status, result, cancellation, and replay
- [x] Restart-safe completed results

## Phase 5 — Observation interface
- [x] React and TypeScript client
- [x] Target selection and trial execution
- [x] Breakpoint and evidence display
- [x] Session replay
- [x] User accepted MVP visual hierarchy
- [ ] Manual: narrow mobile acceptance

## Phase 6 — External targets
- [x] Custom HTTP target
- [x] Transcript import
- [x] Contract validation and redaction
- [ ] Manual: validate against a separately hosted chatbot

## Phase 7 — Comparison and release
- [x] Run comparison and regression gates
- [x] Markdown and JSON reports
- [x] Recursive secret redaction
- [x] Security and privacy review document
- [x] Container and tagged release workflow
- [x] Fixed direct frontend dependency versions
- [ ] Manual: broad end-to-end browser acceptance

## Phase 8 — Character Cards and Live Test Room
- [x] Per-user Character Card persistence
- [x] Character Card create, list, detail, and delete API
- [x] Persisted Tester, Subject, Judge, and Breakpoint events
- [x] Watch Mode and Fast Mode
- [x] Character Library and Character Card creator
- [x] Left/right live chatroom UI
- [x] Scrapbook visual system and lightweight SVG assets
- [x] Existing replay, comparison, and reports retained
- [x] Built-in Character Cards retired in Phase 12

## MVP polish — provider configuration and reports
- [x] Slower multi-beat Watch Mode pacing
- [x] Fast Mode remains delay-free
- [x] Prompt + Model Character Card creation
- [x] DeepSeek, OpenAI, OpenRouter, and custom compatible presets
- [x] Provider, base URL, model, system prompt, temperature, and API key fields
- [x] API keys remain process-memory only and are not persisted
- [x] API key reconfiguration after backend restart
- [x] Prompt-model cards execute through the OpenAI-compatible provider
- [x] Lab Note and JSON report modals
- [x] Copy and download actions inside report modals
- [x] User completed a real provider Subject test

## Phase 9 — Adaptive Tester and efficient local development
- [x] Single trial snapshot endpoint returns run state and incremental events
- [x] Watch Mode snapshot interval is approximately 1.2 seconds
- [x] Fast Mode snapshot interval is approximately 450 milliseconds
- [x] Previous two-request polling loop removed from the live observer
- [x] Benchmark Tester remains fixed and reproducible
- [x] Adaptive Tester follows Subject replies
- [x] Separate Adaptive Tester provider, model, prompt, temperature, turns, and key
- [x] Adaptive Tester key remains active-run memory only
- [x] Tester planning and generated messages appear in the live room
- [x] Clear forbidden-phrase fractures stop further adaptive pressure
- [x] Existing deterministic Judge remains independent
- [x] Cross-platform `python run.py` launcher
- [x] Launcher creates `.venv` and skips unchanged dependency installation
- [x] Launcher starts and stops FastAPI and Vite together
- [x] User completed a real Adaptive Tester run
- [ ] Manual: verify launcher on both Windows and macOS/Linux

## Phase 10 — Railway deployment readiness
- [x] Railway config-as-code selects the root Dockerfile
- [x] Production container listens on Railway-provided `PORT`
- [x] React production build is served by FastAPI from one service
- [x] Railway healthcheck uses `/health`
- [x] SQLite production path remains `/data/echo_masque.db`
- [x] Remote deterministic smoke-test script
- [x] Automatic GitHub Actions Railway Smoke workflow
- [x] CI builds and starts the production Docker image
- [x] CI mounts a persistent Docker volume and runs a real Trial
- [x] Railway deployment and persistence guide
- [x] Public Railway domain created
- [x] GitHub-hosted bilingual Railway Smoke passes
- [ ] Manual: confirm SQLite data survives a Railway redeploy

## Phase 11 — English and Simplified Chinese
- [x] Typed i18n provider without an additional runtime package
- [x] English interface remains the default
- [x] Simplified Chinese interface option
- [x] Interface language persists and updates document language
- [x] Interface language remains separate from Test Language
- [x] English and Simplified Chinese Benchmark catalogs
- [x] Language-specific Judge signals
- [x] Bilingual deterministic targets
- [x] Adaptive Tester follows the selected test language
- [x] Trial Run persists `test_language` with old-run English fallback
- [x] English and Chinese runs use separate regression baselines
- [x] Cross-language comparison is rejected
- [x] English and Chinese transcript-analysis rules
- [x] English and Chinese Markdown trial reports
- [x] User-authored data and model responses are not automatically translated
- [x] Multilingual frontend, backend, Docker, and Railway tests
- [x] User accepted the multilingual MVP interface

## Phase 12 — Admin Runtime, Hybrid Judge, and scalable Character Library

### Admin Runtime
- [x] Persist non-secret Adaptive Tester and Semantic Judge profiles
- [x] Add `ECHO_MASQUE_ADMIN_TOKEN`
- [x] Add `ECHO_MASQUE_ADAPTIVE_API_KEY`
- [x] Add `ECHO_MASQUE_JUDGE_API_KEY`
- [x] Protect Admin APIs with `X-Echo-Admin`
- [x] Add public runtime readiness status
- [x] Add bilingual Admin Settings UI
- [x] Store browser Admin token in session storage only
- [x] Support process-memory key overrides
- [x] Never persist or expose raw Admin runtime keys

### Adaptive Tester
- [x] Resolve Adaptive Tester from Admin configuration
- [x] Remove the per-run Adaptive configuration modal
- [x] Disable Adaptive mode with a clear status when Admin runtime is unavailable
- [x] Preserve legacy API payload compatibility for existing integrations

### Hybrid Judge
- [x] Keep Rules Mode deterministic and credential-free
- [x] Add strict structured Semantic Judge output
- [x] Validate Semantic evidence against real Subject turns and exact excerpts
- [x] Add Rules, Semantic, and Hybrid Judge Modes
- [x] Store Rule and Semantic verdicts separately
- [x] Mark Rule/Semantic disagreement as REVIEW
- [x] Add English and Simplified Chinese Semantic Judge instructions
- [x] Store Provider, Model, rubric, confidence, dimensions, and usage metadata
- [x] Include grounded Hybrid Judge detail in Markdown and JSON reports
- [x] Reject comparisons across different Judge Modes
- [x] Reject REVIEW runs as regression baselines

### Character Library
- [x] Stop seeding user-facing built-in Character Cards
- [x] Remove previously seeded built-in cards without deleting Trial runs
- [x] Keep deterministic targets internal for CI and Railway smoke
- [x] Add Character Card update API
- [x] Edit prompt-model Provider, Model, System Prompt, Base URL, and Temperature
- [x] Preserve Subject credential association during edits
- [x] Add Edit action to Character Cards
- [x] Add search, subject/tag filters, sorting, fixed-width cards, and pagination
- [x] Add an empty-library state

### Automated validation
- [x] Fresh database contains no built-in Character Cards
- [x] Character edits persist and preserve target/key association
- [x] Admin non-secret settings survive restart
- [x] Process-memory runtime keys clear on restart
- [x] Environment runtime keys remain available after restart
- [x] Adaptive/Semantic modes require configured Admin runtimes
- [x] Ungrounded Semantic evidence is rejected
- [x] Hybrid disagreement becomes REVIEW
- [x] Python 3.12 Ruff, strict mypy, and pytest passed
- [x] Python 3.13 Ruff, strict mypy, and pytest passed
- [x] TypeScript, Vitest, and production web build passed
- [x] Docker image and container smoke passed
- [x] Final documentation commit CI and Railway live smoke passed

### Manual validation
- [ ] Configure Admin Runtime once and reuse it across browser sessions
- [ ] Confirm Test Room never asks for Adaptive or Judge credentials
- [ ] Configure real Semantic and Hybrid Judge models
- [ ] Compare Stable and OOC cards with real Hybrid Judge
- [ ] Confirm disagreement evidence is useful for manual review
- [ ] Create enough cards to exercise search, filters, and pagination
- [ ] Edit a card and confirm the next Trial uses the updated prompt
- [ ] Configure Railway Admin/Adaptive/Judge environment variables
- [ ] Redeploy Railway and confirm runtime profiles and environment readiness survive

## Automated acceptance history
- [x] Phase 8 GitHub-hosted Ruff, mypy, pytest, Vitest, and production build passed
- [x] MVP polish GitHub-hosted Ruff, mypy, pytest, Vitest, and production build passed
- [x] Phase 9 GitHub-hosted Ruff, mypy, pytest, Vitest, and production build passed
- [x] Phase 10 GitHub-hosted Ruff, mypy, pytest, web build, and Docker smoke passed
- [x] Phase 11 GitHub-hosted Ruff, mypy, pytest, web build, Docker smoke, and Railway live smoke passed
- [x] Phase 12 GitHub-hosted Ruff, strict mypy, pytest, TypeScript, Vitest, production build, Docker smoke, and Railway live smoke passed

Phase 12 implementation and automated validation are complete. Remaining checks require real Admin Provider credentials, Railway environment configuration, or human UI judgment.
