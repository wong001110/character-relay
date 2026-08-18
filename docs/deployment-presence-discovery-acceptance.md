# Deployment Presence + Discovery — Acceptance Checklist

Branch: `agent/deployment-presence-discovery`  
Base: `main` at `fb71f21ef38227fdb6e9fa842079660b8ee3f1e1`

Status: **implementation batch complete through Phase 11; final batch CI pending**

This is the branch-local acceptance/evidence record required by
`docs/ai-agent-development-workflow.md`. Generated OpenWiki pages remain a merged-`main`
baseline and are intentionally not regenerated on this feature branch.

## OpenWiki / repository-grounded evidence

Canonical sources read before implementation:

- `docs/character-discovery-roadmap.md`
- `docs/ai-agent-development-workflow.md`
- `openwiki/INSTRUCTIONS.md`
- `docs/conversation-intelligence-control-plane-roadmap.md`
- `docs/ai-utility-gateway-roadmap.md`

Existing runtime reused rather than duplicated:

- Deployment/Discord authority and server-profile scope
- Conversation Topics and server-scoped Learned-State event evidence
- perception-safe `CharacterEpisodeAccess` + episodic SQL-RAG
- shared multilingual E5 + `SemanticVectorRepository`
- `YtDlpMediaResolver`, Enhanced Live Media, Key Group credential routing and MediaAnalysis cache
- Character provider target/runtime for final roleplay phrasing only
- Discord Bot/webhook identity and message-route boundaries

## Fixed product invariants

- [x] Character Card remains a reusable definition; no hidden global cross-server consciousness.
- [x] Presence, Activity, Discovery exposure/decision/share state is Deployment-scoped.
- [x] One Character Card may have at most one Deployment in one Discord Server.
- [x] Channel/thread scope cannot create a second incarnation in that Server.
- [x] Shared public content/objective analysis may be reused; subjective perception stays Deployment-scoped.
- [x] Collected content is not automatically a conversation Episode or Character memory.
- [x] Sleeping is Runtime authority, not prompt text.
- [x] Sleep Policy V1 never wakes on mention.
- [x] Explicit mention/reply while sleeping is answered by the real Character Relay Bot.
- [x] Ambient chat silently excludes sleeping Deployments.
- [x] Public Discovery remains separate from future external-account actions/OAuth.

## Phase 0 — Contracts / evidence baseline

- [x] Canonical roadmap and branch acceptance contract exist.
- [x] Deployment/Character/Card/Server ownership boundaries are explicit.

## Phase 1 — One Character Card per Discord Server

- [x] New INSERT/UPDATE duplicates are blocked by Server identity, not channel identity.
- [x] Existing duplicate data is inspected, not silently deleted.
- [x] Cross-Server Deployments of the same Card remain independent.

## Phase 2 — Deployment Presence + Sleep Policy V1

- [x] Presence persistence/API is Deployment-scoped.
- [x] `SLEEPING` hard-excludes Smart Participation/Character Runtime/Tools.
- [x] Ambient messages are silent.
- [x] Explicit mention/reply queues a deduped Bot-only sleeping notice.
- [x] No wake behavior exists.

## Phase 3 — Presence rhythm

- [x] LLM-free scheduler uses existing Server IANA timezone.
- [x] Stable hash + persisted daily sleep/wake schedule survives restarts.
- [x] Wake only clears sleep owned by the rhythm scheduler.

## Phase 4 — Discovery domain / Shadow safety

- [x] Shared `DiscoveryItem` and hashed source-query cache exist.
- [x] Exposure/decision/profile are Deployment-scoped.
- [x] Shadow mode structurally cannot `PROPOSE_SHARE` or `SHARE`.
- [x] Future account-capability contracts contain no credential/action implementation.

## Phase 5 — YouTube collector / cheap ranking

- [x] Official YouTube Data API collector is application-key scoped.
- [x] Search calls are capped and cached across sessions/restarts.
- [x] Seeds use current Server Topics + server-scoped Learned-State events.
- [x] Character-global Learned-State aggregate is not Discovery authority.
- [x] Shared E5/vector cache ranks before expensive understanding.
- [x] Manual Shadow Preview has no exposure/model/send side effects.

## Phase 6 — Browsing Activity Session

- [x] Daily leisure opportunity/start/duration are stable per Deployment/date.
- [x] Persisted `IDLE -> BROWSING -> IDLE` lifecycle is restart-recoverable.
- [x] Sleep/busy blocks or interrupts browsing without waking the Character.
- [x] Candidate/open/watch/share budgets are bounded.
- [x] Owner APIs expose session/item evidence.

## Phase 7 — Selective Media Understanding

- [x] Existing Enhanced Media/yt-dlp/MediaAnalysis runtime is reused.
- [x] Only a bounded high-score `OPEN` shortlist may become `WATCH/ENGAGE`.
- [x] Objective analysis may be shared; exposure promotion remains Deployment-scoped.
- [x] `OPEN -> WATCH/ENGAGE` promotion does not double-count exposure.
- [x] Media failure degrades one item instead of failing the whole browsing session.
- [x] `discovery_media_inspection_enabled` is an independent kill switch.

## Phase 8 — Social association / SocialIntent evidence

- [x] Only `WATCH/ENGAGE` content is eligible.
- [x] Past-conversation association uses Character-accessible Episodes only.
- [x] E5 seed + bounded SQL event→entity→event expansion reuses episodic SQL-RAG.
- [x] Topic/destination comes from perceived Episode evidence.
- [x] Person association uses same-Server relationship evidence for Episode participants.
- [x] Decision evidence stores refs/scores rather than copying conversation text.
- [x] `WOULD_SHARE` itself has no Discord side effect.

## Phase 9 — Review-mode Discord sharing

- [x] `WOULD_SHARE` may create one durable `pending_review` proposal in REVIEW mode.
- [x] Eligibility/association happens before Character model phrasing.
- [x] Character model is used only to phrase the final proposed Discord message; no Tools are enabled.
- [x] Owner can list, approve, or reject proposals.
- [x] Approval rechecks budget/cooldown before queueing.
- [x] Delivery rechecks Deployment scope and Presence before Discord side effect.
- [x] Bot/webhook identity follows existing Deployment identity configuration.
- [x] Message route is registered after delivery for normal reply routing.

## Phase 10 — Limited AUTO initiative

- [x] AUTO requires `mode=auto`.
- [x] AUTO additionally requires per-Deployment `auto_share_enabled=true`.
- [x] AUTO additionally requires global `discovery_auto_share_global_enabled=true`.
- [x] Daily share budget and cooldown are enforced.
- [x] `(deployment_id, discovery_item_id)` uniqueness prevents duplicate proposals/shares.
- [x] Durable outbox recovers interrupted delivery and retries bounded failures.
- [x] Sleeping/busy Presence defers queued delivery.
- [x] Default configuration keeps AUTO globally disabled.

## Phase 11 — Bilibili Experimental

- [x] Bilibili source is isolated behind `bilibili_discovery_experimental_enabled`.
- [x] Adapter is read-only and uses low-rate yt-dlp `bilisearch` discovery.
- [x] No cookies/login/account mutation is introduced.
- [x] Raw interest queries are not persisted; shared cache stores hashes + canonical result keys.
- [x] Bilibili candidates normalize into the same shared `DiscoveryItem` contract.
- [x] Deep understanding reuses the existing Bilibili/yt-dlp media path.
- [x] One source failure is isolated when another enabled source can still return candidates.
- [x] When YouTube + Bilibili are enabled, daily browsing platform selection is stable/randomized per Deployment/date.

## Final batch validation gate

Run only after the complete module batch lands:

- [ ] Ruff — Python 3.12 / 3.13
- [ ] MyPy — Python 3.12 / 3.13
- [ ] Full Pytest — Python 3.12 / 3.13
- [ ] Web typecheck/test/build
- [ ] Discord Connector typecheck/test/build + image build
- [ ] Docker storage/runtime smoke
- [ ] Railway Smoke

The immediately preceding stable Phase 7 service-layer head passed all of the above core CI gates.

## Owner acceptance pass

1. Same Character Card cannot be deployed twice in one Discord Server.
2. Same Card in another Server has independent Presence/Discovery history.
3. Sleeping Deployment is absent from ambient participation and cannot browse/share.
4. Explicit mention/reply while sleeping receives the real Bot sleeping notice.
5. Daily sleep and browsing schedules survive restart without rerolling.
6. YouTube Shadow Preview shows seeds/ranking without perception side effects.
7. Browsing session visibly remains `BROWSING` for its planned duration.
8. Only selected content reaches `WATCH/ENGAGE` and existing Media Understanding.
9. Perceived past Episode/Topic/person association is visible in decision evidence.
10. REVIEW proposal can be approved/rejected and only approved items reach Discord.
11. AUTO remains inert until both Deployment and global switches are enabled.
12. AUTO obeys budget/cooldown and sleeping/busy deferral.
13. Bilibili cannot be enabled unless the Experimental global gate is enabled.
14. Bilibili failure does not break a working YouTube source.

## OpenWiki after merge

After owner acceptance and merge to `main`:

```bash
openwiki --update
```

Review the generated diff against merged source/tests and this canonical acceptance record.
Do not present future external-account OAuth/social mutation contracts as implemented behavior.
