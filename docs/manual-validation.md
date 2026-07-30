# Manual Validation

These checks require human judgment, real Provider credentials, a Railway redeploy, or an external environment. They do not replace automated CI.

## Phase 14 priority acceptance

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

## Phase 13 priority acceptance

### Custom Scenarios

- [ ] Create one English and one Simplified Chinese variant of the same behavioral test.
- [ ] Confirm each variant preserves its own messages, expected behavior, required signals, forbidden signals, severity, and maximum turns.
- [ ] Edit a Scenario and confirm its updated fields appear in newly created Runs.
- [ ] Duplicate a Scenario and confirm the copy receives a new ID.
- [ ] Delete a Scenario and confirm it is removed from any current Test Pack without altering prior Run snapshots.

### Test Packs

- [ ] Create a Test Pack containing at least four Scenarios.
- [ ] Reorder the items and confirm the displayed order is preserved after refresh.
- [ ] Disable one item and confirm it is not executed.
- [ ] Edit the pack and confirm its version increments.
- [ ] Duplicate the pack and confirm the copy is independently editable.
- [ ] Use the Test Pack launcher with a user-owned Character Card.
- [ ] Run the same pack against a stable card and an intentionally OOC card.
- [ ] Confirm a pack with no enabled Scenario for the selected Test Language cannot start.

### Immutable experiment snapshots

- [ ] Complete a Test Pack Run and record the Character name, Pack version, Scenario content, Provider, Model, System Prompt, and Temperature shown in its snapshot/report.
- [ ] Edit the Character Card, Target configuration, Test Pack, and Scenarios.
- [ ] Reopen the old experiment and confirm every saved value remains unchanged.
- [ ] Run the edited configuration and confirm the new Run contains the new values.
- [ ] Confirm a deleted current Scenario or Pack does not break an already completed Run report.
- [ ] Confirm no Subject, Adaptive, Judge, or Admin secret appears in the snapshot.

### Experiment History

- [ ] Filter by Character, Test Pack, language, Tester Mode, and Judge Mode.
- [ ] Confirm pagination works with more than 20 snapshotted Runs.
- [ ] Mark one compatible Run as baseline and confirm a later baseline replaces it for the same Character/Pack pair.
- [ ] Rerun an experiment and confirm the new Run records `rerun_of` and uses the frozen configuration.
- [ ] Open a Lab Note from history.
- [ ] Delete a Run and confirm its turns, events, evidence, snapshot, and history entry are removed.
- [ ] Confirm pre-Phase-13 Runs are not misrepresented as reproducible snapshots.

### Storage Diagnostics and persistence probe

- [ ] Open Workspace → Storage & Backup using the Admin Token.
- [ ] Confirm Environment is `production` on Railway.
- [ ] Confirm Database Path is `/data/echo_masque.db`.
- [ ] Confirm Writable is Yes and Persistent Path is Yes.
- [ ] Confirm Character, Scenario, Pack, and Run counts match the visible workspace.
- [ ] Create a persistence probe and copy its ID.
- [ ] Trigger a real Railway redeploy.
- [ ] After the new deployment is healthy, check the same probe ID and confirm the marker remains.
- [ ] Delete the probe after verification.
- [ ] Temporarily point a local production configuration outside `/data` and confirm the red persistence warning appears.

### Workspace export and import

- [ ] Export the real workspace as JSON.
- [ ] Search the archive for Subject, Adaptive, Judge, and Admin secrets and confirm none are present.
- [ ] Confirm Character Cards, Scenarios, Packs, snapshotted Runs, turns, events, evidence, and non-secret Admin Runtime configuration are included.
- [ ] Import into a clean local database using Merge mode.
- [ ] Confirm a second Merge import skips duplicate IDs rather than duplicating records.
- [ ] Test Replace mode only after retaining a backup and confirm the current owner workspace is replaced.
- [ ] Open an imported report and confirm Unicode Chinese content remains intact.

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
- [ ] Confirm the Character Library, Workspace Hub, Scenario editor, Pack editor, launcher, Admin Settings, and Test Room remain readable on narrow mobile width.
- [ ] Confirm English is the default in a fresh browser profile.
- [ ] Switch to Simplified Chinese, refresh, and confirm the interface language persists.
- [ ] Confirm UI Language and Test Language remain independent.
- [ ] Confirm user-authored card fields, prompts, Scenario text, and model responses are not automatically translated.

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

- [x] Volume is attached to the Echo Masque service at `/data`.
- [x] `ECHO_MASQUE_DATABASE_URL` is configured as `sqlite:////data/echo_masque.db`.
- [ ] Complete the Phase 13 persistence probe across a real redeploy.
- [ ] Add `ECHO_MASQUE_ADMIN_TOKEN`.
- [ ] Add `ECHO_MASQUE_ADAPTIVE_API_KEY` and `ECHO_MASQUE_JUDGE_API_KEY`.
- [ ] Confirm Admin Settings reports both runtimes Ready with environment credentials.
- [ ] Run a real Adaptive + Hybrid Test Pack on Railway.
- [ ] Redeploy and confirm Admin profiles, Character Cards, Scenarios, Packs, experiments, and the probe persist.
- [ ] Confirm the automatic credential-free Railway Smoke remains green.

## Production boundary

- [ ] Do not invite external users until authenticated identities and authorization replace the temporary `X-Echo-User` boundary.
- [ ] Use limited, revocable Provider keys with spending caps for public demos.
- [ ] Add rate limiting, managed persistence, audit logging, and a secure vault before production use.
