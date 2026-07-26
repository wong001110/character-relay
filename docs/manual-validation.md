# Manual Validation

These checks require human judgment, real Provider credentials, or an external environment. They do not replace automated CI.

## Phase 12 priority acceptance

### Admin Runtime

- [ ] Set `ECHO_MASQUE_ADMIN_TOKEN` and confirm an incorrect token returns 401.
- [ ] Open Admin Settings once and configure Adaptive Tester and Semantic Judge profiles.
- [ ] Confirm Test Room users do not enter Adaptive or Judge Provider settings or credentials.
- [ ] Enter process-memory Adaptive and Judge keys, run a Trial, restart the server, and confirm those keys clear.
- [ ] Configure `ECHO_MASQUE_ADAPTIVE_API_KEY` and `ECHO_MASQUE_JUDGE_API_KEY`, restart, and confirm both runtimes return Ready with credential source `environment`.
- [ ] Inspect SQLite, Trial events, Lab Note, JSON report, and logs and confirm raw runtime keys are absent.

### Real Semantic and Hybrid Judge

- [ ] Run a stable user-owned card through Rules, Semantic, and Hybrid modes.
- [ ] Run an intentionally OOC card through the same language and rooms.
- [ ] Confirm Semantic Judge scores the stable card materially above the OOC card.
- [ ] Confirm each Semantic failure cites a real Subject turn and exact response excerpt.
- [ ] Test a correct refusal that quotes an attack phrase and confirm Semantic Judge understands the refusal rather than blindly matching the phrase.
- [ ] Test partial acceptance such as “I am still Ann, but I will act as an unrestricted assistant” and confirm Semantic Judge identifies identity drift.
- [ ] Create a Rule/Semantic disagreement and confirm Hybrid displays REVIEW rather than PASS or FAIL.
- [ ] Confirm REVIEW runs cannot become regression baselines.
- [ ] Confirm English and Simplified Chinese Semantic summaries use the selected Test Language.
- [ ] Inspect Judge Provider, Model, rubric version, confidence, dimensions, latency, and token metadata in reports.

### Character Library

- [ ] Confirm a fresh or upgraded database shows no built-in Character Cards.
- [ ] Confirm internal deterministic targets do not appear as user-owned cards.
- [ ] Create at least 10 user-owned cards and confirm fixed-width cards do not compress.
- [ ] Exercise name/persona/trait/tag search.
- [ ] Exercise subject-type and tag filters.
- [ ] Exercise newest, oldest, and name sorting.
- [ ] Exercise pagination and confirm page controls remain readable on narrow widths.
- [ ] Edit a Prompt + Model card and change Provider, Base URL, Model, System Prompt, and Temperature.
- [ ] Confirm prior Trial history remains and the target ID is unchanged.
- [ ] Confirm the existing Subject credential remains connected after editing.
- [ ] Run the edited card and confirm the updated System Prompt is used.

## Existing interface and multilingual checks

- [x] User accepted the current desktop UI for the MVP stage.
- [ ] Confirm the Character Library, creator, Admin Settings, and Test Room remain readable on narrow mobile width.
- [ ] Confirm English is the default in a fresh browser profile.
- [ ] Switch to Simplified Chinese, refresh, and confirm the interface language persists.
- [ ] Confirm UI Language and Test Language remain independent.
- [ ] Confirm user-authored card fields, prompts, and model responses are not automatically translated.

## Live Test Room

- [ ] Confirm room opening, Tester, Subject typing, Subject response, Semantic Judge thinking, Judge result, breakpoint, and room transition are visually distinct.
- [ ] Confirm Semantic Judge thinking disappears when the Judge result arrives.
- [ ] Confirm auto-scroll remains comfortable during Echo Hall.
- [ ] Confirm Watch and Fast modes both remain useful.
- [ ] Confirm Stop Session produces a clear cancelled state and stops polling.
- [ ] Confirm Watch uses approximately one `/snapshot` request every 1.2 seconds.
- [ ] Confirm Fast uses approximately one `/snapshot` request every 450 milliseconds.

## Reports and regression

- [ ] Open long Lab Note and JSON reports and confirm scrolling, copy, and download work.
- [ ] Confirm Hybrid reports show separate Rule and Semantic scores.
- [ ] Confirm REVIEW is visible in both Markdown and JSON reports.
- [ ] Confirm reports include grounded excerpts but no credentials.
- [ ] Run two same-language, same-Judge-Mode Benchmark sessions and confirm comparison works.
- [ ] Confirm comparisons reject different Test Languages and different Judge Modes.

## Subject Provider

- [x] User completed a real Prompt + Model Subject test.
- [x] User completed a real Adaptive Tester run.
- [ ] Confirm latency and token metadata are captured for the current real Provider.
- [ ] Restart the backend and confirm a process-memory Subject key must be entered again.
- [ ] Confirm rejected keys, unknown models, timeouts, and malformed Provider responses do not expose secrets.

## One-command launcher

- [ ] From a clean checkout, run `python run.py` and confirm `.venv` plus dependencies are prepared.
- [ ] Run it again and confirm unchanged dependency installation is skipped.
- [ ] Press Ctrl+C once and confirm FastAPI and Vite both stop.
- [ ] Repeat on Windows and macOS or Linux.

## External chatbot

- [ ] Connect a separately hosted chatbot through the Custom HTTP Target contract.
- [ ] Confirm every scenario gets an isolated session.
- [ ] Confirm Trace appears when supplied and sensitive headers are redacted.
- [ ] Confirm reset, timeout, authentication rejection, and malformed response diagnostics.

## Railway

- [ ] Add the `/data` Volume and confirm Character Cards, Trials, reports, and Admin non-secret settings survive redeploy.
- [ ] Add `ECHO_MASQUE_ADMIN_TOKEN`.
- [ ] Add `ECHO_MASQUE_ADAPTIVE_API_KEY` and `ECHO_MASQUE_JUDGE_API_KEY`.
- [ ] Confirm Admin Settings reports both runtimes Ready with environment credentials.
- [ ] Run a real Adaptive + Hybrid Trial on Railway.
- [ ] Redeploy and confirm Admin profiles persist and environment runtimes return Ready automatically.
- [ ] Confirm the automatic credential-free Railway Smoke remains green.

## Production boundary

- [ ] Do not invite external users until authenticated identities and authorization replace the temporary `X-Echo-User` boundary.
- [ ] Use limited, revocable Provider keys with spending caps for public demos.
- [ ] Add rate limiting, managed persistence, audit logging, and a secure vault before production use.
