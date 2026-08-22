# Manual validation

Status: **current checks that need human judgment, real providers, Discord, or Railway**

These checks supplement automated CI. Do not use production credentials in screenshots, artifacts, issue comments, browser storage, or logs.

## Before a release

- [ ] Python Ruff, strict mypy, and pytest pass for every supported CI Python version.
- [ ] Portal typecheck, Vitest, and production build pass from a clean `npm ci` install.
- [ ] Discord Connector typecheck, Vitest, build, and container checks pass from a clean `npm ci` install.
- [ ] Root production Docker image starts and `/health` becomes healthy with a mounted test Volume.
- [ ] Review the final diff for unrelated changes, new secrets, scope widening, and obsolete Topic authority.
- [ ] Confirm changed behavior has a source/test evidence map and changed architecture has an updated canonical contract.

## Authentication and ownership

- [ ] Sign in as a normal User and confirm Admin-only account/runtime/trace surfaces are unavailable.
- [ ] With two temporary accounts, confirm one owner cannot list, read, update, or delete the other's private resources.
- [ ] Confirm the Portal uses the HttpOnly authenticated Session and does not ask for or persist an Admin token.
- [ ] Create and revoke a Session; confirm the revoked Session can no longer access authenticated routes.
- [ ] Export an account workspace and search it for passwords, Session tokens, invitation codes, raw keys, and encrypted credential blobs.
- [ ] Verify account deletion removes owned resources and credentials without breaking retained audit references.

## Credential vault and providers

- [ ] Save a limited, revocable provider key through the encrypted Vault and confirm the UI receives status/metadata, not the raw key.
- [ ] Exercise one successful and one rejected provider call; confirm logs, Runtime Trace, Provider Trace, reports, and exports remain redacted.
- [ ] Rotate `CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS` with `<new>,<old>`, rotate stored credentials, verify they remain usable, then remove the old key only after acceptance.
- [ ] Confirm optional Adaptive, Judge, and Authoring environment fallbacks use `CHARACTER_RELAY_*` settings and are reported as environment sources without exposing values.

## Character and evaluation loop

- [ ] Create/edit a Character Card and verify prompt/model/version changes affect only new Runs.
- [ ] Inspect a Character Runtime Prompt: raw creator prompt remains distinct from the compiled runtime prompt and every export stays secret-free.
- [ ] Run a Test Pack in Rules and a model-backed Judge mode; confirm evidence excerpts point to actual Subject turns.
- [ ] Run a small Matrix and verify task counts, pause/resume/cancel/retry behavior, aggregates, and immutable snapshots.
- [ ] Create an AI-assisted authoring Draft and verify it cannot become an executable Scenario/Test Pack without explicit approval.
- [ ] Export/import a Share Bundle and confirm import creates Drafts only.

## Intelligence, tools, and media

- [ ] Exercise direct reply, mention, interleaved discussion, and ambiguous follow-up flows; verify Conversation Structure can remain unresolved instead of forcing a wrong Thread/target.
- [ ] Verify a correction supersedes or disputes a lower-authority Belief without rewriting raw message evidence.
- [ ] Confirm no runtime/API/UI path uses Topic fallback, Topic-scoped durable Memory, or `topic_id` continuation authority.
- [ ] Trigger a tool continuation and verify Runtime authorization, scope, expiry, and side-effect idempotency.
- [ ] Test media context-only, preview-grounded, content-grounded, failed-inspection, and declined-inspection behavior; planner-only media detail must never appear as Character perception.
- [ ] Confirm observability failure does not break a Character response.

## Discord end-to-end

- [ ] Connect a test Server, synchronize its profile/channels, and deploy two Character Cards with distinct identities.
- [ ] Verify explicit mentions/replies, Smart Participation, multi-character ordering, cooldown/rate limits, and excluded-channel scope.
- [ ] Restart the Connector during an in-flight delivery test and confirm deduplication/recovery prevents duplicate visible output.
- [ ] Exercise an authorized tool, attachment/link preview, generated media, and a failed provider/tool path.
- [ ] Confirm Connector and backend logs contain no Bot token, connector shared secret, provider key, or raw authorization header.
- [ ] Confirm ordinary Discord events contain source IDs and structured decisions but no message preview, prompt, response, planning text, or nested raw payload.
- [ ] As a normal User and a non-Bootstrap Admin, confirm temporary Discord capture APIs and controls are unavailable.
- [ ] As Bootstrap Admin, enable a 15-minute capture for one test Server; confirm another Server is not captured, raw detail requires an explicit reveal, the response is `no-store`, and start/reveal/stop/clear audits contain no raw text.
- [ ] Exercise direct `/messages`, a non-durable Social Turn, a newly generated durable Social Turn step, and a durable replay; confirm the three generation paths are captured and the replay is not duplicated.
- [ ] Stop, expire, clear, and restart during test captures; confirm new messages are not captured after stop/expiry, records disappear after clear/restart, and capture-store failure does not change the Character Turn response.

## Portal and accessibility

- [ ] Test the changed flow at desktop, tablet, and narrow mobile widths.
- [ ] Verify keyboard navigation, visible focus, dialog dismissal/focus return, labels, contrast, loading, empty, error, and disabled states.
- [ ] Switch English/Simplified Chinese and confirm interface language is independent from evaluation language.
- [ ] For approved renovated pages, compare composition against the exact `docs/ui-references/` image without copying generated sample values.

## Public Demo

- [ ] Start with stale Demo-owned sample data and restart; confirm reconciliation leaves only the intended Demo Cards/resources without changing Admin-owned source Cards.
- [ ] Confirm every mutation path is denied server-side for the shared Demo account, including direct API calls.
- [ ] Run the retained Public Demo smoke/status workflows and inspect their redacted artifacts/job summaries.
- [ ] Confirm limited Demo provider credentials are ready for every selected Demo Character without exposing their values.

## Railway storage and deployment

- [ ] Confirm the Production environment owns the public domain, exact service, and Volume mounted at `/data`.
- [ ] Confirm `CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db` and exactly one replica while using SQLite.
- [ ] Confirm Railway sets `RAILWAY_RUN_UID=0`, then verify Uvicorn runs as the image user UID `10001` after startup ownership repair.
- [ ] Record `/health` storage metadata and `storage_instance_id`, create a Persistence Probe, redeploy, and confirm the same ID and Probe remain.
- [ ] Back up the secret-free Workspace before infrastructure or migration changes; test restore in a disposable environment.
- [ ] Run Railway smoke and the relevant live security/release acceptance workflows after deployment.

## External target

- [ ] Connect a separately hosted chatbot through `docs/http-target-contract.md`.
- [ ] Verify isolated sessions, reset, timeout, authentication rejection, malformed response diagnostics, and recursive header/body redaction.
