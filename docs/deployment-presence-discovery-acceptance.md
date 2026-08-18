# Deployment Presence + Discovery — Acceptance Checklist

Branch: `agent/deployment-presence-discovery`
Base: `main` at `fb71f21ef38227fdb6e9fa842079660b8ee3f1e1`

Status: **implementation in progress — Phase 0–6 runtime landed; full CI revalidation pending**

This checklist is the branch-local acceptance/evidence record required by `docs/ai-agent-development-workflow.md`. Generated OpenWiki baseline remains merged-main documentation and is intentionally not regenerated on this feature branch.

## Evidence map

### Canonical docs read

- `docs/character-discovery-roadmap.md`
- `docs/ai-agent-development-workflow.md`
- `openwiki/INSTRUCTIONS.md`
- `docs/conversation-intelligence-control-plane-roadmap.md`
- `docs/ai-utility-gateway-roadmap.md`

### Source contracts inspected before implementation

Deployment/runtime:

- `src/echo_masque/persistence/deployment_models.py`
- `src/echo_masque/persistence/deployment_repository.py`
- `src/echo_masque/api/deployment_schemas.py`
- `src/echo_masque/api/routes/deployments.py`
- `src/echo_masque/persistence/database.py`

Conversation Intelligence:

- `src/echo_masque/character_learned_state.py`
- `src/echo_masque/smart_participation_outcome.py`
- `src/echo_masque/persistence/conversation_topic_models.py`
- `src/echo_masque/persistence/conversation_episode_models.py`
- `src/echo_masque/episodic_sql_rag.py`
- `src/echo_masque/layered_conversation_consolidation.py`

Discord Connector:

- `connectors/discord/src/types.ts`
- `connectors/discord/src/relayClient.ts`
- `connectors/discord/src/index.ts`

Existing reusable infrastructure:

- shared E5/query-vector reuse
- public video canonicalization and `yt-dlp` transcript/metadata resolution
- shared Media Analysis cache/single-flight
- Condition Watch persisted scheduler pattern (pattern only; Discovery uses a separate scheduler)
- Utility Gateway gray-zone-only policy

Phase 7 reuse boundary additionally inspected:

- `src/echo_masque/content_resolver.py`
- `src/echo_masque/live_media.py`
- `src/echo_masque/live_media_scoped.py`
- existing `MediaUnderstandingService` / `MediaAnalysisRepository` path

## Fixed invariants

- [x] Character Card stays a reusable definition; no hidden global cross-server consciousness is added.
- [x] Presence/Activity/Discovery lived state is Deployment-scoped.
- [x] One Character Card may have at most one Deployment in one Discord Server.
- [x] Channel/thread scope cannot be used to create a duplicate incarnation in the same Server.
- [x] Shared public content/media analysis may be global, but subjective exposure/decision is Deployment-scoped.
- [x] Collected external content does not automatically become a conversation Episode or Character memory.
- [x] Sleeping is Runtime authority, not a prompt instruction.
- [x] Sleep Policy V1 has no wake-on-mention behavior.
- [x] Explicit address to a sleeping Character is answered by the real Character Relay Discord Bot, not the Character webhook.
- [x] Ambient chat does not emit sleep notices.
- [x] Discovery/account-action adapters remain separate; OAuth/social write actions are out of scope.

## Phase status

### Phase 0 — Contracts / OpenWiki evidence baseline

- [x] Canonical roadmap revised.
- [x] Branch evidence map created.
- [x] Fixed invariants recorded before runtime changes.
- [x] Source/test changes linked in this checklist as phases land.

### Phase 1 — One Character Card per Discord Server

- [x] Repository/database guard uses Server identity rather than channel identity.
- [x] Server-profile deployments reject duplicate Character Card in same guild.
- [x] Legacy exact-channel deployments cannot create another incarnation in the same workspace/guild.
- [x] Update/move path cannot create a duplicate server incarnation.
- [x] Existing duplicate data is reported/left for explicit repair, not silently deleted.
- [ ] Full regression suite passes on final Phase 6 head.

Evidence:

- SQLite INSERT/UPDATE guards use owner + Discord connection + workspace/guild + Character Card.
- `inspect_deployment_server_duplicates()` provides non-destructive legacy inspection.
- Existing pagination fixture was changed to multiple Character Cards rather than preserving the invalid duplicate model.

### Phase 2 — Deployment Presence + Sleep Policy V1

- [x] Presence persistence exists and is owner/deployment scoped.
- [x] Manual Presence read/update API exists.
- [x] Server-side Smart Participation authority excludes sleeping Deployments before semantic/planner candidacy.
- [x] `SLEEPING` blocks Character Runtime before Character model/Tool execution.
- [x] Explicit mention/reply is intercepted while sleeping.
- [x] Real Bot sends bounded sleep notice.
- [x] Ambient messages are silent.
- [x] Repeated explicit addresses respect notice cooldown/dedupe.
- [x] No Character model/Tool call occurs for sleeping explicit addresses.
- [x] No wake behavior exists.
- [x] Cross-server Deployments of the same Character Card remain independent.
- [ ] Final Phase 6 head passes the complete Python regression suite.

Evidence:

- Presence state is not stored on Character Card.
- Sleep notice uses a persisted system-notice queue and Discord Bot token; Character webhook identity is never used for the notice.
- Current V1 keeps alias/name-only sleeping addressing silent unless it resolves through the explicit mention/reply authority path; no Character reply is generated.

### Phase 3 — Presence scheduler / rhythm

- [x] Dedicated Presence scheduler/service exists outside Condition Watch.
- [x] Rhythm is opt-in.
- [x] Daily sleep schedule is persisted/recoverable and does not reroll on restart.
- [x] Sleep transitions are deterministic-with-bounded-variation.
- [x] Existing Discord Server IANA timezone is reused.
- [x] Scheduler performs no Character LLM calls.
- [x] Wake only clears sleep state owned by the rhythm scheduler.
- [ ] Final Phase 6 head passes scheduler regression tests.

### Phase 4 — Discovery domain / Shadow mode

- [x] Shared DiscoveryItem contract/persistence exists.
- [x] Deployment-scoped exposure and decision persistence exists.
- [x] Candidate collection alone does not grant perception.
- [x] Shadow mode cannot record executed/proposed share side effects.
- [x] Account-capability domain boundary is reserved without credentials/actions.
- [x] Public-source query cache does not persist raw private interest query text.
- [ ] Final Phase 6 head passes Discovery persistence tests.

### Phase 5 — YouTube collector / cheap ranking

- [x] YouTube adapter collects supported public candidates through the official Data API.
- [x] Candidate data normalizes into shared DiscoveryItem.
- [x] Search calls are session-capped and query results persist across Deployment sessions/restarts.
- [x] Seed builder uses Deployment Server Topic + server-scoped Learned-State event evidence.
- [x] Character-global Learned-State aggregate is not used as Discovery lived-interest authority.
- [x] Existing shared E5 runtime and SemanticVectorRepository are reused.
- [x] E5/cheap ranking precedes expensive understanding.
- [x] Exploration/freshness/novelty budgets are bounded.
- [x] No per-candidate Character LLM loop.
- [x] Manual Shadow Preview collects/ranks without exposure, Discord send, or Character LLM.
- [ ] Final Phase 6 head passes YouTube/seed/ranking regression tests.

### Phase 6 — Browsing Activity Session

- [x] Persisted DeploymentActivitySession and per-item session evidence exist.
- [x] Daily browsing opportunity/start/duration are generated from stable Deployment/date hashing.
- [x] Same day/restart does not reroll the planned browsing opportunity.
- [x] Browsing scheduler is independent from Presence sleep scheduler and Condition Watch.
- [x] `IDLE -> BROWSING -> IDLE` lifecycle is persisted and restart-recoverable.
- [x] Browsing cannot start while sleeping/busy.
- [x] Sleep/busy interruption cancels browsing without waking or clearing the stronger Presence state.
- [x] Candidate/open/watch/share budgets exist; Shadow share budget is fixed to zero.
- [x] Phase 6 records only `SCROLL_PAST`, `NOTICE`, and `OPEN`; `WATCH/ENGAGE` remain reserved for Phase 7 selective Media Understanding.
- [x] Session/list/detail owner APIs expose current/past browsing evidence for acceptance.
- [x] Same Character Card in another Server keeps an independent Presence/Activity state.
- [ ] Ruff passes on final Phase 6 head.
- [ ] MyPy passes on final Phase 6 head.
- [ ] Full Pytest passes on final Phase 6 head.

Current CI cleanup evidence:

- Earlier Python gate exposed 14 Ruff issues; those formatting/import issues were fixed.
- Diagnostic artifacts then exposed 11 MyPy issues in Presence/YouTube/seed-builder code; fixes are on the branch.
- Diagnostic Pytest artifacts exposed unsupported `pytest.mark.asyncio`; tests now use standard-library `asyncio.run()` instead of adding a new dev dependency.
- Railway Smoke has continued to pass during Phase 6 iterations.

### Phase 7 — Selective Media Understanding / exposure

- [ ] Existing Media Runtime is reused rather than duplicated.
- [ ] `OPEN` shortlist is selectively promoted to `WATCH/ENGAGE`; collection/ranking alone is insufficient.
- [ ] Objective analysis is reused across Deployments where cache rules allow.
- [ ] Subjective exposure remains Deployment-scoped.
- [ ] No Discovery-specific transcript/vision/cache stack is introduced.
- [ ] Learned interest evidence remains Server/Deployment-safe; no Character-global aggregate leak is introduced.

### Phase 8 — Social association / Shadow SocialIntent

- [ ] Topic association uses current/recent Topic data.
- [ ] Past-conversation association uses perception-safe episodic SQL-RAG.
- [ ] Person association uses existing Social Graph/relationship evidence.
- [ ] `WOULD_SHARE` remains shadow-only.
- [ ] Decision trace contains reason/evidence.

### Phase 9 — Review-mode Discord sharing

- [ ] Proposed share requires review/approval.
- [ ] Runtime chooses eligibility before Character model phrases the message.
- [ ] Policy/cooldown/dedupe/destination authority is enforced.
- [ ] Accept/reject evidence is retained for calibration.

### Phase 10 — Limited AUTO initiative

- [ ] Explicit opt-in per Deployment.
- [ ] Strict share budgets/cooldowns/idempotency.
- [ ] One-click disable prevents new autonomous sends.
- [ ] Sustained soak does not spam channels.

### Phase 11 — Bilibili Experimental

- [ ] Adapter is isolated/feature-flagged/kill-switchable.
- [ ] Same normalized DiscoveryItem/exposure semantics as YouTube.
- [ ] Existing Bilibili/yt-dlp content understanding is reused.
- [ ] No Bilibili account/login/action automation.
- [ ] Bilibili failure cannot break core Discovery/YouTube behavior.

## Manual owner acceptance targets

The final owner acceptance should explicitly exercise:

1. Same Character Card cannot be deployed twice to one Discord Server.
2. Same Character Card can still have independent Deployments in different Servers.
3. Set Deployment A to sleeping; ambient chat ignores it.
4. Explicitly mention/reply to Deployment A; real Bot reports sleeping without Character webhook/model output.
5. Verify repeated mentions do not spam the status notice.
6. Verify another Server's Deployment of the same Card can remain awake.
7. Enable rhythm and verify sleep schedule survives restart without rerolling.
8. Enable YouTube Shadow Discovery and inspect manual Shadow Preview ranking.
9. Start a Shadow browsing session and verify Presence remains `BROWSING` for the planned duration.
10. Verify another Server's Deployment of the same Card stays independent during that session.
11. Force/observe sleep while browsing and verify browsing cancels without waking the Character.
12. Verify collected-but-unseen items do not enter Character lived history.
13. Verify Phase 6 has no `WATCH/ENGAGE` until selective Media Understanding lands.
14. After Phase 7, verify only a small shortlist reaches existing Media Understanding.
15. Verify a past Discord topic can create a traceable content association.
16. In REVIEW mode, approve/reject proposed shares and inspect evidence.
17. Only after review quality is acceptable, optionally test AUTO under strict budgets.
18. Enable/disable Bilibili Experimental and verify isolation.

## OpenWiki after merge

After this feature is accepted and merged to `main`:

```bash
openwiki --update
```

Review the generated wiki diff against the merged source/tests and this canonical roadmap. Do not merge generated claims that present unimplemented future account phases as current behavior.
