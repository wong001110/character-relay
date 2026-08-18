# Character Relay — Deployment Presence and Discovery Roadmap

Status: **IMPLEMENTED THROUGH PHASE 11 — OWNER ACCEPTANCE PENDING**

Branch: `agent/deployment-presence-discovery`

This document is the canonical architecture/phase plan for the current Presence + Discovery work. It follows `docs/ai-agent-development-workflow.md` and `openwiki/INSTRUCTIONS.md`: current source/tests remain authoritative for implemented behavior, this document records accepted intent, and generated OpenWiki pages should be refreshed from merged `main` only after this work is accepted and merged.

## Implementation status

The feature branch now implements the planned Deployment-scoped Presence + public Character Discovery V1 through Phase 11:

- Phase 0 — contracts / OpenWiki evidence baseline;
- Phase 1 — one Character Card per Discord Server invariant;
- Phase 2 — Deployment Presence + Sleep Policy V1;
- Phase 3 — deterministic, persisted Presence rhythm;
- Phase 4 — shared Discovery domain + Deployment-scoped exposure/decision;
- Phase 5 — YouTube public candidate collector + server-scoped E5 ranking;
- Phase 6 — persisted Browsing Activity Sessions;
- Phase 7 — selective reuse of existing Media Understanding;
- Phase 8 — perception-safe episodic SQL-RAG / Topic / relationship association;
- Phase 9 — Review-mode Discord share proposal/approval/outbox;
- Phase 10 — bounded AUTO initiative with global + Deployment opt-in, budget, cooldown and retry/idempotency;
- Phase 11 — Bilibili Experimental read-only adapter behind a global kill switch.

The source validation gate is green on `14fc10f715ad75a22b81f4f177f2fe595bbe4dc8`: Ruff, MyPy, full Pytest on Python 3.12/3.13, Web, Discord Connector, Docker and Railway Smoke. Public Demo Status Check remains an external deployment-readiness failure and did not reach demo verification.

Detailed acceptance evidence and manual owner acceptance steps live in `docs/deployment-presence-discovery-acceptance.md`.

## 1. Product goal

Make a deployed Character feel persistently present outside direct Discord turns without turning Character Relay into a full life simulator.

The target loop is:

```text
Deployment has a current Presence state
  -> sometimes sleeps / idles / browses
  -> browsing sessions discover external content
  -> cheap ranking decides what deserves attention
  -> existing Media Runtime understands only shortlisted content
  -> the Deployment forms subjective exposure / interest / associations
  -> most items are ignored or merely remembered
  -> strong items may create a Social Intent
  -> bounded policy may later share into Discord
```

The feature exists to create **time-continuous experience that can affect later conversation**, not to manufacture decorative activity logs.

## 2. Fixed product boundaries

### 2.1 Character Card remains a reusable definition

Character Card keeps its current responsibility: persona/identity definition and authoring/runtime configuration source.

Do **not** add cross-server lived state to Character Card. In particular, Character Card does not own:

- current sleeping/idle/browsing state;
- current YouTube/Bilibili session;
- server-specific learned interests;
- server-specific relationships;
- server-specific memories/topics;
- Discovery exposure/history;
- a hidden global cross-server consciousness.

### 2.2 Deployment owns lived runtime state

A Deployment is the concrete runtime incarnation of a Character Card in one Discord Server.

```text
Character Card: Zhi
  |
  +-- Deployment / Server A
  |     +-- Presence
  |     +-- Activity sessions
  |     +-- Discovery exposure
  |     +-- Topics / Memory / Learned State / Social context
  |
  +-- Deployment / Server B
        +-- independent Presence
        +-- independent Activity sessions
        +-- independent Discovery experience
```

The same Character Card may therefore be sleeping in Server A while browsing YouTube in Server B. That is intentional: the product does not claim these Deployments share one cross-server consciousness.

### 2.3 One Character Card per Discord Server

Hard product invariant:

> For one owner/account, one Character Card may have at most one Deployment in the same Discord Server.

The uniqueness identity is conceptually:

```text
owner_id
+ platform
+ connection_id
+ workspace_id / Discord guild_id
+ character_card_id
```

Channel/thread is **not** part of the identity. Channels are activity scope inside the one server Deployment.

### 2.4 Shared content is global; subjective experience is Deployment-scoped

Objective public content may be shared/deduplicated globally:

```text
ExternalContent / DiscoveryItem
MediaAnalysis
canonical source resolution
```

Subjective state must be Deployment-scoped:

```text
DeploymentPresence
DeploymentActivitySession
DeploymentDiscoveryExposure
DeploymentDiscoveryDecision
DeploymentDiscoverySharePolicy / Share outbox
```

Fetching a YouTube/Bilibili item does not mean every Deployment has seen it.

## 3. Presence Runtime

Presence is Runtime authority, not a roleplay prompt suggestion.

Initial states:

```text
SLEEPING
IDLE
BROWSING
BUSY
```

### 3.1 Availability gate

Presence must be evaluated before Smart Participation ranking and before invoking the Character model.

`SLEEPING` is a hard exclusion:

- no Smart Participation candidacy;
- no Character model call;
- no Character Tool call;
- no Discovery browsing session;
- no autonomous Discovery share.

### 3.2 Sleep Policy V1

Ambient group message while sleeping: the Deployment is excluded silently.

Explicit mention or reply to a sleeping Character:

```text
explicit address
  -> DeploymentPresence == SLEEPING
  -> Character Runtime is NOT invoked
  -> real Character Relay Discord Bot sends a system status notice
```

V1 does **not** implement wake-on-mention, wake probability, dream replies, or interrupted-sleep roleplay.

### 3.3 Rhythm and persistence

Presence simulation uses bounded, persisted scheduling rather than rerolling every process restart. The scheduler reuses the Discord Server IANA timezone and no Character LLM.

## 4. Discovery Runtime

Discovery is an external perception source feeding existing Conversation Intelligence, not a second Character brain.

Reuse current systems for:

- Topic lifecycle/keywords;
- server-scoped Learned State evidence;
- E5 semantic ranking/query-vector cache;
- perception-safe episodic SQL-RAG;
- Social Graph/relationship context;
- shared Media Understanding and MediaAnalysis cache;
- existing Character provider only for final share phrasing.

Do **not** create parallel `DiscoveryInterest`, `DiscoveryMemory`, or `DiscoveryRelationshipGraph` systems.

### 4.1 Source adapters

Platform priority:

- **YouTube** — stable public source through the official Data API;
- **Bilibili** — Experimental read-only source, globally kill-switchable;
- X + Reddit / Instagram remain future source adapters;
- TikTok remains deferred;
- Bluesky remains intentionally excluded.

### 4.2 Candidate versus exposure

```text
DiscoveryItem
= content exists in the shared candidate pool

DeploymentDiscoveryExposure
= this Deployment actually noticed/opened/watched/engaged with it
```

Only exposure can become lived evidence for later decisions.

### 4.3 Browsing sessions

Browsing is a persisted Activity Session, not a blind fixed cron.

```text
DeploymentPresence = IDLE
  -> bounded daily leisure opportunity
  -> stable/randomized YouTube or Bilibili session
  -> DeploymentPresence = BROWSING
  -> candidate/open/watch/share budgets
  -> planned end
  -> DeploymentPresence = IDLE
```

Attention levels:

```text
SCROLL_PAST
NOTICE
OPEN
WATCH
ENGAGE
```

### 4.4 Discovery seeds and ranking

Seeds come from the Deployment's existing Server context: active/cooling Topics, server-scoped Learned-State event evidence, weak Character definition priors and exploration/freshness/novelty.

Ranking remains cheap-first:

```text
many candidates
  -> deterministic/source filters
  -> shared E5 / sparse / freshness / novelty
  -> small shortlist
  -> existing Media Runtime only for a bounded OPEN subset
```

### 4.5 Selective Media Understanding

`WATCH/ENGAGE` reuses the existing canonical public-video resolver, yt-dlp transcript/metadata, Key Group credential routing and `MediaAnalysis` cache. Objective analysis may be shared; subjective exposure stays Deployment-scoped.

### 4.6 Social association

Only `WATCH/ENGAGE` content can enter social association. The runtime searches only Episodes the Character has `CharacterEpisodeAccess` to, then reuses E5 + bounded SQL event→entity→event expansion. Topic/destination and person association must be backed by perceived Episode / same-Server relationship evidence.

Possible motivations include:

```text
RELATED_TO_CURRENT_TOPIC
RELATED_TO_PAST_CONVERSATION
REMIND_ME_OF_SOMEONE
INTERESTING
```

## 5. Sharing modes

### SHADOW

`WOULD_SHARE` is evidence only. No proposal and no Discord side effect.

### REVIEW

```text
WOULD_SHARE
  -> system selects eligible item/destination
  -> Character provider phrases final message only
  -> durable pending_review proposal
  -> owner approve / reject
  -> policy recheck
  -> durable Discord outbox
```

### AUTO

AUTO is globally disabled by default and requires all gates:

```text
mode = AUTO
AND Deployment auto_share_enabled = true
AND global discovery_auto_share_global_enabled = true
AND daily budget available
AND cooldown passed
AND Deployment active
AND destination still in scope
AND Presence not sleeping/busy
```

A durable outbox provides bounded retry/recovery and `(deployment_id, discovery_item_id)` uniqueness prevents duplicate proposals/shares.

## 6. Bilibili Experimental

The Bilibili adapter is read-only, low-rate and globally kill-switchable. It uses yt-dlp `bilisearch` for candidate discovery, persists only hashed query cache identity/result keys, introduces no cookies/login/account mutation, and reuses the same Bilibili/yt-dlp Media Runtime for selected content.

A Bilibili source failure must not break a working YouTube source.

## 7. Reserved future account integration

Real platform accounts remain out of the current implementation scope. Reserved abstractions include:

```text
PlatformIdentity
AccountBinding
CredentialReference / OAuthAdapter
PlatformCapability
SocialIntent
CapabilityRouter
PolicyGate
ActionExecutor
```

Public Discovery adapters and future account/action adapters stay separate. Current implementation does not add OAuth, Like/Follow/Comment/Post/DM automation or external account mutation.

## 8. Validation and owner acceptance

Source validation is complete; owner product acceptance remains pending. Use:

- `docs/deployment-presence-discovery-acceptance.md`

After owner acceptance and merge to `main`:

```bash
openwiki --update
```

Review generated OpenWiki output against merged source/tests. Generated pages must not claim future OAuth/external-account actions are already implemented.
