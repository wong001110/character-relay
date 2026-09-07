# Active development plan — AI-native reliability review

Status: **corrective batch complete; MCP/slow-turn implementation and local verification complete; Draft PR #204 open; not merged**
Branch: `codex/ai-native-reliability-review`
PR: https://github.com/wong001110/character-relay/pull/204
Implementation commit: `3b334a8e78bf1ce64cc25d8253afc2efe2ac4d1b`
Base: `main @ d23e7f22229788068dbb76abf9e403fd0a4bcc7d`

User authorized implementation, sub-agents/model choice, a PR, and a final whole-project Red Team assessment. Root owns integration. No production deployment, external attack targets or production data deletion is authorized.

## Authority and practice

The [architecture review](history/architecture-review-2026-09-07.md) is the finding baseline, not a confirmed production incident postmortem. The [previous branch record](history/knowledge-fabric-foundation-execution.md) is archived.

Use AI-Native Development Practice: native harness first, adaptive coherent stages, selective delegation, risk-based validation, explicit Security and Red Team. Agent Lore is not a new dependency. Trace ingress, formal wiring, persistence, execution, delivery, observation and recovery before declaring a feature complete. Root reviews delegated changes and commits; agents do not deploy or commit independently.

Invariants: Runtime owns authorization/side effects; owner/server/Character perception cannot widen; uncertain effects are not blindly replayed; Demo stays read-only; secrets stay out of prompts/logs/exports; raw evidence remains provenance; no Topic authority; preserve existing source data and Portal design.

## Stages

| Stage | Findings | Acceptance | State |
| --- | --- | --- | --- |
| A: evidence/environment | R09 | Archive stale plan, isolated dependencies, reproducible PG/API/worker recipe and actual validation evidence | Implemented; local evidence below, PG execution unavailable |
| B: recovery/acquisition | R01–R03 | New service cannot reset active work; supervised/restartable tasks; explicit offline recovery; bounded capture and process resources; failed discovery preserves current source | Implemented; focused regressions and independent review passed |
| C: continuation/recall | R04–R07 | Formal runtime continuation scoped to actor/deployment/server and assigned tool; no unknown effect replay; query-first older recall with perception; allowed Fabric candidates and provenance-safe packing | Implemented; focused regressions and independent review passed |
| D: integrated security gate | R09 + new findings | Source-wide defensive review, boundary/failure regressions, Python/Web/Connector gates, final scope-wide assessment with executed/blocked/unverified distinctions | Defensive assessment and local regressions complete; adversarial exercise blocked |
| E: PR | all | Reviewed diff, evidence, remaining work and handoff; open PR without merging/deploying | Draft PR #204 open |
| Follow-up: interaction quality | R08 + remaining R04–R06 | Durable acknowledgement/progress/result protocol; real dialogue replay, same-model quality/latency/cost comparison | Protocol implemented; live dialogue-quality comparison remains pending |
| Follow-up: dense retrieval | remaining R06–R07 | Actual index→query→prompt and update/delete semantics with measured relevance benefit | Planned; do not claim disconnected paths available |
| Follow-up: MCP | R05 | One controlled provider; pagination, discovery, schema changes, reauthorization/failures after capability contracts | Controlled integration implemented; live configured-provider smoke remains pending |

All nine findings are tracked. This corrective release fixes proven defects and establishes foundations; planned expansion is not implementation. Local gaming/WebRTC, framework replacement, broad graph enrichment and Portal redesign remain deferred.

## Delegation

- Root: environment/docs, target credential safety, integration, final gates and PR.
- GPT-5.6 Terra / high: runtime recovery; tools; memory; Fabric retrieval; acquisition, each with non-overlapping file ownership.
- GPT-6 Astra / high: independent security source review and integrated acceptance review.
- Cross-module constructor edits go through the file owner. Security participates before acceptance.

## Final Security / Red Team scope

Auth/session/invitations; vault/target/provider config; owner/server/Character isolation; Demo/exports; Discord ingress/delivery/tools; memory/external-content trust; SSRF/browser resources; recovery/cancellation; Portal rendering; deployment/CI.

An automatic cybersecurity check stopped the independent agent's attack-reproduction task. Do not resume rejected attack scripts. Continue materially narrower defensive source review, corrective patches and rejection-before-execution regression tests with synthetic fixtures. Record blocked adversarial validation explicitly. No blanket secure certification or full Red Team pass.

## Evidence and limitations

- Base targeted sandbox suite: 16 passed in 10.78 s; does not prove formal pending wiring.
- Python 3.12 isolated dependencies and Portal/Connector npm ci succeeded.
- Remote main rechecked at start: d23e7f2.
- Sandbox lacks Docker/PostgreSQL. apt setup failed because user/group switching is unsupported; do not claim local PostgreSQL coverage.
- Production incident logs/resources/topology and actual model/Discord quality remain unverified.
- Final commands/outcomes and exact handoff are recorded below.
- No production changes. Document rollout/offline recovery and rollback before deployment.

## Integration evidence and takeover

- Root integrated the runtime, tools, recall, Fabric and acquisition changes, and independently
  inspected the workspace import authorization patch. The independent memory reviewer accepted
  final continuation suppression: CAS losers, cancellation and uncertain actions are removed from
  the actual provider-visible tool list even when embeddings are unavailable; 28 focused tests passed.
- Independent runtime source review accepted Compose settings/entrypoint and the Python CI Portal
  build. Docker was not executed.
- `python -m ruff check .`: passed. `python -m mypy src`: passed, 390 source files.
- Portal: `npm test` (69 passed) and `npm run build` (TypeScript + Vite) passed; existing large-chunk
  advisory remains. Discord Connector: typecheck, 95 tests and build passed.
- Target endpoint mutation gate: 87 checked, 65 killed, 22 equivalent survivors, zero unchecked
  in this targeted scope. See [individual classifications](target-endpoint-mutation-2026-09-07.md).
- First integrated parallel run: 975 passed, 6 skipped, one SQLite concurrent-initialization
  ledger conflict. Runtime correction serializes complete initialization for the same SQLite URL
  within one process; existing PostgreSQL advisory locking remains. Root reviewed the correction.
  Migration/foundation regressions: 14 passed, 3 skipped; concurrency regression: five passes.
  This does not claim SQLite cross-process locking or canonicalization of alternate file URLs.
- Final `python -m pytest -n 2 --tb=short`: **976 passed, 6 skipped, 13 warnings in 267.29 s**
  on Python 3.12.13 after the SQLite correction. This is the repository-configured suite, including
  its pre-existing exclusion of `tests/test_utility_gateway_phase2.py`; no new exclusions were added.
  Warnings include existing pytest class-collection and Pydantic fixture-serialization warnings.
- GitHub CI for implementation commit `3b334a8` (run `34117172813`) completed the Web,
  Discord Connector, PostgreSQL foundation and Docker jobs successfully. PostgreSQL evidence
  covers the existing five bootstrap/cutover/API/retrieval contracts; Docker covers production
  storage rejection, non-root browser startup, API readiness and storage identity after replacement.
  This does not run the new full Compose topology, invitation concurrency or load tests.
  Python 3.12/3.13 CI jobs were still running at documentation closeout; check current PR status.
- Initial whole-suite run was stopped when automatic approval review rejected unexpected ONNX
  telemetry. No completion/pass is claimed for that run. Default tests now inject a fake encoder
  or exercise the unavailable fallback. This is not a general outbound-network sandbox.
- Earlier completed offline run found outdated recovery expectations, fixed-date expiration tests,
  an unnecessary live DNS dependency behind fake media transports, and a stale HTTPX test assertion.
  Those failures were corrected; the successful final integration run above is the local evidence.

No release is approved. Remaining egress/DNS binding, multimodal-client admission and atomic quota
work are tracked in [the scope-wide security assessment](security-red-team-2026-09-07.md).
Latest steering: the user has parked local-model/adversarial reproduction work and requested a
continued reviewer assessment of improvements, omissions and lower-priority features. Do not
restart the parked work. Full Compose validation and unresolved security evidence remain release
limitations, not requirements to resume adversarial work in the current review task.

## Reviewer follow-up — 2026-09-07

Status: source review complete; recommendations only, no new product changes or feature-removal
decision. The [product/runtime review](reviewer-product-runtime-2026-09-07.md) records R10–R17,
source evidence, acceptance proposals and feature tradeoffs at `895f817`.

- Root reconciled three read-only reviews: product surfaces, memory quality and runtime cost.
- Main CI run `34117484100` and Railway Smoke passed at `895f817`. Public Demo Status Check
  `34117484124` failed: two Demo cards, one credential ready. The workflow queries shared
  production without deployed-commit attestation; this is not proof of a PR regression.
- This review ran two existing provider-capability persistence tests (both passed), a pure local
  endpoint-key comparison, source/caller checks and read-only GitHub CI inspection. No full-suite,
  load, live-model or browser E2E evidence was added.
- Proposed next work: repair first-use/readiness gaps; establish actual-turn replay evidence;
  close queue/deadline/cancellation and scratch-expiry lifecycles; then assess automatic gap
  discovery and optional modules by quality/cost comparison. R10–R17 remain unimplemented.
- Existing security release limitations still apply. Production rollout and merge remain outside
  this task. The new report does not supersede product contracts or approve deleting features.

## MCP and asynchronous conversation implementation — active

User now explicitly requests implementation of MCP tool discovery/use and natural early replies
while slow tools run, followed by images/results in the original conversation. This supersedes
the preceding review-only scope for these capabilities; local models and adversarial reproduction
remain parked. Baseline: `15c19029d3d627e044350ad601920686057b68de`; same Draft PR #204.

Evidence: `tool_runtime.py`, `media_tools.py`, `targets/prompt_model.py`, `connector_runtime.py`,
`api/routes/connectors.py`, durable runtime repositories, Discord `relayClient.ts`/`index.ts`,
tool-calling and media-generation contracts. Runtime retains assignment, owner/deployment scope,
side-effect admission and durable delivery authority. MCP catalog text is untrusted data.

Stages:
1. Controlled Streamable HTTP MCP gateway: operator-configured endpoints and exact owner/deployment
   grants; bounded paginated discovery; fingerprints and argument validation before invocation;
   no automatic server installation, OAuth grants or executable stdio configuration.
2. Durable bounded turn jobs and progress claims: short submission/poll requests, model-authored
   progress before slow tools, final existing delivery, timeout/shutdown outcomes with no blind
   re-execution of uncertain effects. Knowledge Fabric worker remains separate in responsibility.
3. Formal Discord connector integration, synthetic delayed-provider/MCP regressions, independent
   source review, relevant Python/Connector gates, documentation and PR update.

Delegation: MCP agent owns new config/client/gateway and focused tests/dependencies; job agent owns
new job models/repository/routes/progress lifecycle and app/database composition; connector agent
owns TypeScript job protocol and real delivery. Root owns registry/model/media integration, settings,
contracts, reconciliation and commit. Agents do not commit or access live providers/Discord.

Acceptance: acknowledgement can be delivered before blocked image/MCP work completes; authorized
discovery returns only a few relevant schemas; unassigned or changed remote tools fail before call;
final images use the existing scoped artifact/Discord identity path; failed/unknown effects never
cause a second automatic write; repeated polls/submission do not repeat progress or final delivery.


### MCP/slow-turn closeout — 2026-09-07

Implemented the three stages above. Canonical contract/configuration: `docs/mcp-conversation-jobs.md`.
New persistence tables are `discord_turn_jobs` and `discord_turn_job_progress`, initialized through
existing SQLAlchemy table registration; no existing source-data table is rewritten. The job queue
is lifespan-supervised inside each API process, distinct from the dedicated Fabric worker.

Validation:
- Full offline Python integration run: `python -m pytest -n 2 --tb=short` — **1005 passed,
  6 skipped, 13 warnings**, 288.92 seconds. This ran before the final recovery pagination changes.
- Post-recovery integration scope: `python -m pytest tests/test_turn_jobs.py tests/test_mcp_gateway.py
  tests/test_mcp_conversation_integration.py tests/test_slow_image_conversation.py
  tests/test_tool_continuation_review.py tests/test_prompt_model_tool_calling.py
  tests/test_tool_runtime.py tests/test_image_creation_runtime.py -q` — **51 passed**.
  Final query-limit change additionally rechecked all **8** job/API tests.
- `ruff check src tests` and `mypy src` pass; mypy checks **399 source files**.
  An optional repository-wide `ruff format --check` reports 251 unformatted files; this is not
  an existing CI gate, and unrelated formatting was not changed. It is not recorded as a pass.
- Discord Connector: `npm test -- --run` — **105 tests across 18 files passed**;
  typecheck, production build, and whitespace diff check pass.
- MCP grant mutation command: `mutmut run '*McpProviderConfig*granted_tool_names*'
  --max-children 2` — **4 selected mutants killed, 0 survivors**. The tool generated other
  configuration mutants, which were not executed or counted in this result.
- MCP transport tests use the actual official SDK with synthetic in-process ASGI JSON/SSE
  responses, including byte limits; no external MCP/provider/Discord calls were made.

Independent Security source review was performed by `mcp_jobs_security_review`, separate from
implementers. Findings drove streamed response bounds, restricted schema validation, fresh scope
checks, progress CAS, continuous retention, terminal claim-before-send, delivery-state SQL filtering,
message-only recovery pagination past revoked entries, and periodic bounded Connector recovery.
Final static recheck found no remaining blockers in that reviewed scope. This is not a new full
adversarial Red Team execution; the user parked local-model/adversarial reproduction.

Deliberate limits: only configured public HTTPS Streamable HTTP MCP providers and explicit grants;
no provider is enabled by default; restricted schemas and one bounded inline image; per-destination
turn serialization; in-process rather than distributed job execution; uncertain effects never
replayed; live dialogue quality, provider compatibility, Discord outages, PostgreSQL contention,
and DNS-to-connection binding remain unverified. See the canonical contract for operational limits.

Commit/handoff: this closeout and implementation are one coherent commit after `15c19029` on Draft
PR #204; identify the exact commit from Git history to avoid embedding a self-referential hash.
Next action after review: configure one authorized MCP provider in an isolated preview, exercise
real Discord acknowledgement/image/final delivery, and compare dialogue quality/latency against
baseline. No merge, production deployment, live test dispatch, or feature removal was performed.
