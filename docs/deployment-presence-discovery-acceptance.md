# Deployment Presence + Discovery — Acceptance Checklist

Branch: `agent/deployment-presence-discovery`
Base: `main` at `fb71f21ef38227fdb6e9fa842079660b8ee3f1e1`

Status: **implementation in progress**

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
- Condition Watch persisted scheduler pattern (pattern only; Discovery must use a separate scheduler)
- Utility Gateway gray-zone-only policy

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
- [ ] Source/test changes linked in this checklist as phases land.

### Phase 1 — One Character Card per Discord Server

- [ ] Repository duplicate check uses Server identity rather than channel identity.
- [ ] Server-profile deployments reject duplicate Character Card in same guild.
- [ ] Legacy exact-channel deployments reject duplicate Character Card in same workspace/guild.
- [ ] Update/move path cannot create a duplicate server incarnation.
- [ ] Existing duplicate data is reported/left for explicit repair, not silently deleted.
- [ ] Regression tests pass.

### Phase 2 — Deployment Presence + Sleep Policy V1

- [ ] Presence persistence exists and is owner/deployment scoped.
- [ ] Manual Presence read/update API exists.
- [ ] Connector deployment contract carries current Presence.
- [ ] `SLEEPING` deployments are excluded before Smart Participation/Character invocation.
- [ ] Explicit mention/reply is intercepted while sleeping.
- [ ] Real Bot sends bounded sleep notice.
- [ ] Ambient messages are silent.
- [ ] Repeated explicit addresses respect notice cooldown.
- [ ] No Character model/Tool call occurs for sleeping explicit addresses.
- [ ] No wake behavior exists.
- [ ] Cross-server Deployments of the same Character Card remain independent.

### Phase 3 — Presence scheduler / rhythm

- [ ] Dedicated scheduler/service exists outside Condition Watch.
- [ ] Rhythm is opt-in.
- [ ] Daily schedule is persisted/recoverable and does not reroll on restart.
- [ ] Sleep transitions are deterministic-with-bounded-variation.
- [ ] Scheduler performs no Character LLM calls.

### Phase 4 — Discovery domain / Shadow mode

- [ ] Shared DiscoveryItem contract/persistence exists.
- [ ] Deployment-scoped exposure and decision persistence exists.
- [ ] Candidate collection alone does not grant perception.
- [ ] Shadow mode cannot send Discord/social actions.
- [ ] Account-capability domain boundary is reserved without credentials/actions.

### Phase 5 — YouTube collector / cheap ranking

- [ ] YouTube adapter collects supported public candidates.
- [ ] Candidate data normalizes into shared DiscoveryItem.
- [ ] Seed builder uses server/deployment context instead of a second interest database.
- [ ] E5/cheap ranking precedes expensive understanding.
- [ ] Exploration/freshness/novelty budgets are bounded.
- [ ] No per-candidate Character LLM loop.

### Phase 6 — Browsing Activity Session

- [ ] Persisted DeploymentActivitySession exists.
- [ ] `IDLE -> BROWSING -> IDLE` lifecycle is authoritative/recoverable.
- [ ] Browsing cannot start while sleeping/busy.
- [ ] Candidate/open/watch/share budgets exist.
- [ ] Attention levels are recorded.

### Phase 7 — Selective Media Understanding / exposure

- [ ] Existing Media Runtime is reused rather than duplicated.
- [ ] Objective analysis is reused across Deployments where cache rules allow.
- [ ] Subjective exposure remains Deployment-scoped.
- [ ] Learned State receives bounded evidence only after real exposure.

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
8. Run YouTube Shadow browsing; inspect candidate ranking and exposures.
9. Verify collected-but-unseen items do not enter Character lived history.
10. Verify only a small shortlist reaches Media Understanding.
11. Verify a past Discord topic can create a traceable content association.
12. In REVIEW mode, approve/reject proposed shares and inspect evidence.
13. Only after review quality is acceptable, optionally test AUTO under strict budgets.
14. Enable/disable Bilibili Experimental and verify isolation.

## OpenWiki after merge

After this feature is accepted and merged to `main`:

```bash
openwiki --update
```

Review the generated wiki diff against the merged source/tests and this canonical roadmap. Do not merge generated claims that present unimplemented future account phases as current behavior.
