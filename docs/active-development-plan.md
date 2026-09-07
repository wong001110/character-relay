# Active development plan — AI-native reliability review

Status: **corrective implementation complete; final verification and draft PR in progress; not merged**
Branch: `codex/ai-native-reliability-review`
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
| D: integrated security gate | R09 + new findings | Source-wide defensive review, boundary/failure regressions, Python/Web/Connector gates, final scope-wide assessment with executed/blocked/unverified distinctions | Defensive assessment complete; final regression running; adversarial exercise blocked |
| E: PR | all | Reviewed diff, evidence, remaining work and handoff; open PR without merging/deploying | Pending |
| Follow-up: interaction quality | R08 + remaining R04–R06 | Durable acknowledgement/progress/result protocol; real dialogue replay, same-model quality/latency/cost comparison | Planned |
| Follow-up: dense retrieval | remaining R06–R07 | Actual index→query→prompt and update/delete semantics with measured relevance benefit | Planned; do not claim disconnected paths available |
| Follow-up: MCP | R05 | One controlled provider; pagination, discovery, schema changes, reauthorization/failures after capability contracts | Planned |

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
- Final commands/outcomes and exact handoff will be appended after integration.
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
- Final `python -m pytest -n 2 --tb=short` outcome: pending integration closeout.
- Initial whole-suite run was stopped when automatic approval review rejected unexpected ONNX
  telemetry. No completion/pass is claimed for that run. Default tests now inject a fake encoder
  or exercise the unavailable fallback. This is not a general outbound-network sandbox.
- Earlier completed offline run found outdated recovery expectations, fixed-date expiration tests,
  an unnecessary live DNS dependency behind fake media transports, and a stale HTTPX test assertion.
  Those focused failures were corrected; the final integration run remains the acceptance evidence.

No release is approved. Remaining egress/DNS binding, multimodal-client admission and atomic quota
work are tracked in [the scope-wide security assessment](security-red-team-2026-09-07.md).
Next: finish the final regression, open the draft PR and inspect CI. Then resolve PostgreSQL/container
and blocked adversarial validation in an authorized suitable environment before release; prioritize
remaining security findings before MCP/dense/dialogue expansion. Production rollout and merge are
not part of this task.
