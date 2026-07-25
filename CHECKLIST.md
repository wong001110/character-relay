# Echo Masque MVP Checklist

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
- [x] Stable and Fragile demo targets
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
- [x] Demo target selection and trial execution
- [x] Breakpoint and evidence display
- [x] Session replay
- [ ] Manual: visual hierarchy and responsive behavior

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
- [ ] Manual: real provider smoke test
- [ ] Manual: end-to-end browser acceptance

## Phase 8 — Character Cards and Live Test Room
- [x] Per-user Character Card persistence
- [x] Demo Stable and Fragile Character Cards
- [x] Character Card create, list, detail, and delete API
- [x] Persisted Tester, Subject, Judge, and Breakpoint events
- [x] Watch Mode and Fast Mode
- [x] Character Shelf and Character Card creator
- [x] Left/right live chatroom UI
- [x] Scrapbook visual system and lightweight SVG assets
- [x] Existing replay, comparison, and reports retained
- [ ] Manual: card shelf visual quality
- [ ] Manual: Watch Mode pacing and breakpoint clarity
- [ ] Manual: desktop, tablet, and mobile acceptance

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
- [ ] Manual: real provider smoke test with a user-owned key
- [ ] Manual: revised Watch Mode pacing acceptance
- [ ] Manual: Lab Note and JSON modal readability

## Automated acceptance
- [x] Credential-free deterministic demo works
- [x] Python unit and integration suite is present
- [x] Python source and tests compile
- [x] Frontend strict TypeScript configuration is present
- [x] Phase-by-phase commits are pushed
- [x] Phase 8 GitHub-hosted Ruff, mypy, pytest, Vitest, and production build passed
- [ ] MVP polish GitHub-hosted Ruff, mypy, pytest, Vitest, and production build passed
