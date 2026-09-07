# Security review — 2026-09-07

Status: **defensive source assessment and local regression evidence; adversarial validation blocked**.

Branch: `codex/ai-native-reliability-review`. Baseline: `d23e7f22229788068dbb76abf9e403fd0a4bcc7d`.
This review covers the integrated working-tree changes on that baseline, not a frozen release
commit. The integration owner must record the final commit and final validation results below.

## Recommendation and limits

The corrective changes are suitable for an independently reviewed PR with explicit residual
risks. **Do not describe this as a completed whole-project red-team exercise, a secure-production
certification, or proof of prompt-injection resistance.** An automatic cybersecurity check
rejected the proposed adversarial reproduction work. That work was stopped; no exploit scripts,
credential extraction, outbound target probes, invitation race demonstration, live model calls,
or production testing were performed by this reviewer. Subsequent work was limited to source
inspection, corrective import authorization code, and ordinary local defensive regression tests.

The latest corrective sources address the original target-client admission and invitation
atomicity gaps within the scopes stated below. An unqualified production security recommendation
is still unsupported: the new endpoint policy covers two clients, not every outbound client;
general HTTP/browser transport pinning and replica-safe quotas remain incomplete. Enablement of
other configurable outbound clients requires its own admission/egress decision. The branch's
improved worker behavior does not establish production resource capacity, latency isolation, or
incident root cause.

The workspace import patch was authored by this reviewer after discovering the gap. Its tests
are defensive evidence, **not an independent review of that patch**. The root integration owner
reported independently reviewing the pre-mutation graph/ownership checks and accepted the patch
for the corrective PR, with the incomplete-historical-archive limitation. Other source changes
were inspected independently of their authors; the integrated working tree was still changing
during inspection.

## Findings and disposition

| ID / priority | Finding and source evidence | Disposition / required acceptance |
| --- | --- | --- |
| S01 / P1, corrected in source | User-configurable target credential names reached process environment lookup in `targets/http_target.py`, `services/trials.py`, `connector_runtime.py`, and `condition_watch_runtime.py`; readiness routes repeated the fallback. | Ambient lookups removed across those paths. HTTP adapters require an explicit resolver; application trials supply the current owner's vault credential. Existing persisted targets receive the same restriction. `tests/test_target_credential_review.py` exercises missing-credential rejection before provider/network invocation and owner vault configuration. No extraction was attempted. |
| S02 / P1, corrected; root review accepted | Ordinary authenticated workspace import validated target conflicts but did not close the relational graph: child records and references could name parents without owner validation. Sources: `api/routes/workspace.py`, `persistence/workspace_repository.py`. | New `_validate_import_graph` checks record identity conflicts and target/card/scenario/pack/run/snapshot/child references inside the transaction before replace deletion. New runs require a scoped snapshot; imports cannot create the public Demo target namespace or set shared Admin Runtime. 40 local defensive tests passed. Root reported independent review and acceptance for the corrective PR. |
| S03 / P1, corrected for two named clients; broader egress remains open | Custom HTTP and prompt-model target requests previously had no operator-origin admission. | `target_endpoint_policy.py` now enforces exact production HTTPS origins before `HttpTarget` sends either message or reset requests and before `OpenAICompatibleProvider` sends completions. HTTP targets default to an empty production allowlist; known provider origins are explicit. Redirect following is disabled. Trials/Connector/watch application construction passes resolved Settings. This is origin admission, **not DNS pinning or a universal network boundary**. `OpenAIMultimodalProvider`, other direct media clients, and general HTTP/browser tools are outside this correction; deployment must restrict or separately secure those configurable paths. No network reproduction performed. |
| S04 / P1, corrected in source | Invitation acceptance previously used read/check/write without an atomic consume. | `AuthRepository.claim_invitation_for_registration` now performs one conditional UPDATE checking unaccepted/unrevoked/unexpired and matching-email state. `AuthService` creates the user and attaches `accepted_by` in the same transaction; failed user creation rolls the claim back. Latest source independently inspected. Sequential/rejection/rollback defensive tests are retained; this reviewer performed no PostgreSQL invitation race demonstration. |
| S05 / P2, open | `PublicUrlGuard` checks and caches resolved addresses, while general HTTP tools and browser route continuation subsequently resolve the original hostname independently. Relevant files: `network_safety.py`, `tool_external.py`, `browser_runtime.py`. | Validation is not destination pinning. Extend the connection-bound policy or enforce network egress isolation, including redirects and browser subresources. Static Fabric pinned acquisition is a separate, stronger path and must not be generalized as proof for all network clients. |
| S06 / P2, open | `QuotaService._consume` uses read/increment/write for persistent counters. Multiple API processes can lose increments; resource count checks are also separate from record creation. | Use atomic database updates/admission or explicitly constrain deployments. Sequential quota tests establish sequential behavior, not replica-safe quotas. No concurrency/load reproduction performed. |
| S07 / P2, partially corrected | Original redaction did not parse stored `*_json` strings or sanitize provider trace payloads at their persistence boundary. | Integrated `security/redact.py` parses explicitly structured JSON fields, redacts common key forms and credential URL components; provider trace emission/persistence and historical backfill use it. This is structured redaction, not guaranteed arbitrary-secret detection in natural-language messages, unusual URL paths, or unrecognized fields. Keep that limit explicit. |
| S08 / P1 candidate, corrected in latest source | An intermediate same-thread continuation implementation selected the sole resumable action without inspecting current-message intent and checked cancellation only on explicit replies. | Tools owner corrected both branches: cancellation precedes resumption, and a continuation cue is now required. Latest source inspected. Cue matching is deterministic and bounded, not a live-model understanding guarantee; retain ordinary unrelated-message/cancel regression tests in the final tools gate. No unintended side effect was demonstrated. |
| S09 / P2, corrected in source | Some manually dispatched live workflows interpolated `LIVE_URL` directly into Python source in a heredoc. Sources: `.github/workflows/live-security-smoke.yml`, `phase16-live-acceptance.yml`. | Both now use `os.environ["LIVE_URL"]`. Latest source independently inspected. This was a trusted workflow-dispatcher boundary, not an untrusted-PR execution finding. No workflow was dispatched. |

Import compatibility is deliberately fail-closed: historical archives with missing/deleted parent
references may require repair or an explicit provenance-preserving import contract. Complete own
merge/replace roundtrips and complete restoration into an empty database are covered. This patch
does not independently validate arbitrary provider configuration embedded in target snapshots;
runtime credential and endpoint policies remain necessary on restored data.

## Whole-project coverage map

This is a surface inventory with sampled source review and named regression evidence. It is not
a claim that every repository line or every endpoint was exhaustively tested.

| Surface | Boundary inspected / relevant sources | Evidence and remaining limits |
| --- | --- | --- |
| Authentication and sessions | `auth.py`, `api/dependencies.py`, `api/routes/auth.py`, auth persistence | Production ignores legacy identity headers; opaque token hashes, expiry/revocation and active-user checks; HttpOnly/SameSite cookies. Standard auth regression suite passed. Invitation conditional-update transaction inspected (S04). No live cookie/browser/session assessment. |
| Admin and credential vault | `credentials.py`, `provider_credentials.py`, account routes and target runtime construction | Owner/scope tuples and encrypted Fernet storage retained; root environment-fallback removal inspected. No real credentials or production rotation performed. |
| Public Demo | `public_demo_middleware.py`, public Demo routes/quota and tests | Server-side mutation denial remains; trial/comparison/rerun allowances are intentional and depend on execution quotas. Standard Demo suite selected. Not an exhaustive method/path fuzzing run. |
| Workspace, exports and API ownership | Workspace repository/routes; phase15 workspace tests; account export | Closed-graph import patch and own roundtrips tested. Exports exclude shared Admin Runtime at account routes; structured JSON redaction added. No raw vault/session tables added to archive. Root reported independent import patch review acceptance. |
| Server/deployment/Character isolation | Connector destination validation, server workspace/catalog repositories, Fabric access and epistemic policy | Owner/server/deployment bindings preserved in inspected paths. Catalog-isolation suite selected; memory and Fabric regression files reviewed by name/source. Shared connector secret remains a privileged whole-connector trust boundary, not one credential per tenant. |
| Discord ingress and delivery | `api/routes/connectors.py`, Connector routing/webhook sending, generated-media route | Constant-time connector secret comparison; destination matching; durable operation/step/claim nonces; generated media requires connector credential and matching deployment; mention allowlists in sending paths. No real Discord delivery or connector-compromise exercise. |
| Tools and continuation | `tool_runtime.py`, `targets/prompt_model.py`, `connector_runtime.py`, `pending_actions_v3.py`, media tool dispatch | Runtime retains schema, assigned/available tool and side-effect-ledger checks. Internal reads are exposed with scoped context; pending actions bind owner/user/server/channel/thread/Character/deployment. S08 corrected in latest source; final tools tests remain integration evidence. Model-generated arguments are not an authority grant. |
| Memory and prompt injection | `internal_context.py`, `context_resolver_v3.py`, conversation/Belief repositories | New internal recall removes aggregate Thread text and checks deployment perception for Episode candidates. Fabric budget packing retains a JSON evidence envelope and provenance. Episode perception still relies on source-message route semantics; mixed-episode assumptions need product evidence. No live-model injection resistance claim. |
| Knowledge Fabric retrieval | Query/context/epistemic policy and packing changes | Character corpus policy constrains candidate ranking; final prompt-packed references and omission reasons are recorded. Dense wiring/freshness/product relevance are separate delivery claims, not implied security evidence. |
| External acquisition and browser | Static pinned fetcher, external policies, browser guard, rendered collection and sync | URL guards and static pinned fetch differ (S03/S05). JSON length/encoding prechecks and in-page DOM estimates reduce copies; Chromium/page behavior remains untrusted and needs process/network limits. Local Compose limits are examples, not production measurements. |
| Worker lifecycle and recovery | Worker composition, background scheduler/invalidation supervision, offline recovery CLI, health route | Worker no longer composes the API; startup no longer performs blanket durable recovery; explicit offline recovery requires operator quiescence. Live DB readiness replaces cached-only health. No production multi-process kill, restore, or load test by this reviewer. |
| Traces and diagnostics | Provider trace sink/repository/routes; runtime trace and Discord debug-capture boundaries | Trace routes remain Bootstrap/Super Admin restricted; structured redaction correction inspected. Debug capture stays separately privileged/ephemeral by contract. S07 limits remain. |
| Portal rendering | `web/src` text/URL rendering scan; API-client ownership use | No `dangerouslySetInnerHTML`/HTML assignment/eval rendering found in the scanned source. Remote image URLs remain `<img src>` values; React text escaping is not a complete browser security review. Root owns JS validation. |
| Deployment and CI | Dockerfile, Compose, workflows and production-storage guard | Non-root image, production PostgreSQL guard, separate local worker resource examples and default CI read permissions inspected. Live workflows use privileged secrets only in their configured live jobs; no live workflow run here. S09 fixed. New default test fixture suppresses implicit real embedding model builds; production encoder disables ONNX Runtime telemetry before session creation. |

## Defensive verification

Executed by this reviewer, using the isolated local Python environment and synthetic data:

- `tests/test_workspace_import_authorization_review.py`: **40 passed**. Covers foreign record
  identities/references, child relations, pre-mutation denial, scoped new Runs, public namespace,
  own merge/replace, and complete restoration into an empty database.
- Earlier combined run with `tests/test_phase13.py` and
  `tests/test_phase15_workspace_isolation.py`: **34 passed** at the then-current smaller import
  test count. Added import cases were subsequently run separately as the 40-test result above.
- Ruff for the import source/test and scoped mypy for `workspace_repository.py`: **passed**.
- Existing auth/vault/security/Demo/catalog tests plus new target/redaction regression tests:
  **26 passed**, using `tests/test_phase15_auth.py`, `tests/test_phase15_admin_vault.py`,
  `tests/test_phase15_security_controls.py`, `tests/test_public_demo.py`,
  `tests/test_discord_catalog_isolation.py`, `tests/test_target_credential_review.py`, and
  `tests/test_trace_redaction_review.py`. Target transport is mocked and required-credential
  regressions reject before invocation; no external service was exercised.
- After the endpoint/invitation fixes, a further independent run of
  `tests/test_target_endpoint_policy_review.py`, `tests/test_invitation_atomic_review.py`, and
  `tests/test_phase15_auth.py`: **13 passed** under the default offline encoder fixture.
  Endpoint transports were mocked; invitation checks covered sequential single-use, rejection,
  and rollback. This is not a database concurrency or network isolation demonstration.

No workspace import mutation-test scope is configured in the inspected `docs/mutation-testing.md`
or existing bounded Python policy scope. That absence is a verification limit, not a mutation
pass. Root is responsible for the configured changed-scope mutation gates and full Python/Portal/
Connector checks. Other agents' reported results must be attributed rather than called this
reviewer's independent executions.

The root reported that an initial full pytest run was stopped because automatic approval review
rejected an unexpected Microsoft ONNX telemetry request. That run is **not a completed pass**.
The rerun uses `tests/conftest.py` to disable real encoder builds by default (tests use injected
encoders or the unavailable-embedding fallback), and `_build_model` now disables ONNX Runtime
telemetry before creating inference sessions. These measures were source-inspected here. The
root is collecting final offline suite/mutation results; those results do not validate real
embedding model quality or an external provider. The fixture is not a universal network sandbox.

## Integration closeout

Root integration record (implementation is on the corrective branch; no production release):

- Reviewed implementation commit: pending final regression; the PR head will identify the artifact.
- Independent review of workspace import correction: root reported accepted for corrective PR.
- S08: independent memory reviewer accepted the final tool list filtering and CAS behavior;
  28 focused tests passed. Cancelled/uncertain actions and CAS losers cannot return through the
  embedding-unavailable fallback. Internal read tools remain available.
- Security regression command/result: 26 tests passed as listed above.
- Root whole-tree Ruff and mypy passed (390 source files). Portal: 69 tests and build passed;
  Connector: typecheck, 95 tests and build passed. Endpoint mutation gate: 65 killed and 22
  individually documented equivalent survivors among 87 checked; see the mutation report.
- Final Python full-suite result: pending. PostgreSQL/container tests were not runnable locally.
- A full-suite SQLite initialization race was corrected by the runtime owner with same-URL,
  process-local bootstrap locking. Root inspected the change; migration/foundation tests passed
  (14 passed, 3 skipped) and the existing concurrent-initialization test passed five times.
  PostgreSQL retains its existing advisory lock; SQLite cross-process safety is not claimed.
- S03/S04/S09: latest corrective source independently inspected within the scopes above.
- Release remains deferred: broader egress/multimodal admission, DNS connection binding, atomic
  quotas, PostgreSQL/container execution and blocked adversarial work need explicit disposition.
  The corrective PR is a draft; passing regressions do not approve deployment.

Adversarial validation remains **blocked/not performed**, irrespective of subsequent standard
test counts. Production credentials, third-party targets and live models were not needed for
the corrective source work described here.
