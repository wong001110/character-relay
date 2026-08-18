# Character Relay — Deployment Presence and Discovery Roadmap

Status: **ACTIVE IMPLEMENTATION**

Branch: `agent/deployment-presence-discovery`

This document is the canonical architecture/phase plan for the current Presence + Discovery work. It follows `docs/ai-agent-development-workflow.md` and `openwiki/INSTRUCTIONS.md`: current source/tests remain authoritative for implemented behavior, this document records accepted intent, and generated OpenWiki pages should be refreshed from merged `main` only after this work is accepted and merged.

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

The repository/API must reject attempts to deploy the same Character Card twice to the same Discord Server, even if the requested channels differ.

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

`ACTIVE_CHAT` should be represented as current engagement/activity evidence where possible rather than forcing every conversation into one exclusive global enum.

### 3.1 Availability gate

Presence must be evaluated before Smart Participation ranking and before invoking the Character model.

```text
Discord event
  -> resolve eligible Deployment(s)
  -> Deployment Presence Gate
  -> Deployment/channel/runtime authority
  -> Smart Participation / explicit addressing
  -> Character Runtime
```

`SLEEPING` is a hard exclusion:

- no Smart Participation candidacy;
- no Character model call;
- no Character Tool call;
- no Discovery browsing session;
- no autonomous Discovery share.

### 3.2 Sleep Policy V1

Sleep does not automatically end because somebody addresses the Character.

Ambient group message while sleeping:

```text
Deployment is excluded silently.
```

Explicit mention or reply to a sleeping Character:

```text
explicit address
  -> DeploymentPresence == SLEEPING
  -> Character Runtime is NOT invoked
  -> real Character Relay Discord Bot sends a system status notice
```

Example notice:

```text
Ann 当前正在睡觉中。
```

The Character webhook must never send this notice because that would imply the sleeping Character is speaking.

V1 does **not** implement wake-on-mention, wake probability, dream replies, or interrupted-sleep roleplay.

Sleep notices require a short `(deployment, channel, notice_type)` cooldown/dedupe so repeated mentions do not spam the channel.

### 3.3 Rhythm and persistence

Presence simulation must use bounded, persisted scheduling rather than rerolling every process restart.

A Deployment may opt into a daily rhythm. Generated sessions should be deterministic for a stored schedule/day and include bounded variation rather than fixed exact times.

First useful rhythm:

- sleep window/duration;
- idle periods;
- bounded leisure opportunities for Discovery browsing.

Do not add eating, showering, commuting, work shifts, or other fake-precision life simulation unless a future product requirement gives those states real runtime consequences.

## 4. Discovery Runtime

Discovery is an external perception source feeding existing Conversation Intelligence, not a second Character brain.

Reuse current systems for:

- Topic lifecycle/keywords;
- Learned State interest/salience/relationship evidence;
- E5 semantic ranking/query-vector cache;
- SQL-RAG episodic recall;
- layered Memory;
- Social Graph/relationship context;
- shared Media Understanding and media cache;
- Utility Gateway only for bounded ambiguity/decision cases.

Do **not** create parallel `DiscoveryInterest`, `DiscoveryMemory`, or `DiscoveryRelationshipGraph` systems.

### 4.1 Source adapters

One platform-neutral contract:

```text
DiscoverySourceAdapter
  -> fetch candidates
  -> normalize to DiscoveryItem
```

Platform priority:

- **P0a YouTube** — first stable implementation source.
- **P0b Bilibili** — high-value but Experimental adapter, isolated behind a feature flag/kill switch.
- **P1 X + Reddit** — later text/realtime/niche sources.
- **P2 Instagram** — later visual source.
- **Deferred TikTok** — until a reliable acceptable integration path is available.
- **Not planned Bluesky** — intentionally excluded from this roadmap.

### 4.2 Candidate versus exposure

Never insert every collected external candidate into `ConversationEpisodeRecord`.

```text
DiscoveryItem
= content exists in the shared candidate pool

DeploymentDiscoveryExposure
= this Deployment actually noticed/opened/watched/engaged with it
```

Only exposure can become lived evidence for later Memory/Learned State/recall.

### 4.3 Browsing sessions

Browsing is an Activity Session, not a fixed cron that blindly fetches content.

```text
DeploymentPresence = IDLE
  -> leisure opportunity
  -> Activity Planner
  -> maybe nothing / YouTube / Bilibili
  -> DeploymentPresence = BROWSING during bounded session
```

A session has budgets such as:

- candidate budget;
- open/inspection budget;
- deep-watch budget;
- share-intent budget;
- exploration probability.

Attention levels:

```text
SCROLL_PAST  title/thumbnail-level exposure at most
NOTICE       candidate caught attention
OPEN         inspect metadata/description
WATCH        use transcript / existing Media Runtime where justified
ENGAGE       strong subjective reaction / memory / social intent
```

### 4.4 Discovery seeds and ranking

Seed selection comes from the Deployment's existing server context:

```text
Learned interests
+ recent/active/cooling Topic summaries and keywords
+ relevant Memory/episodic context
+ exploration/trending candidates
```

Candidate ranking remains cheap-first:

```text
many candidates
  -> deterministic/source filters
  -> E5 / sparse / freshness / novelty ranking
  -> small shortlist
  -> existing Media Runtime only when justified
  -> bounded Utility/Judge only for gray zones
```

Never call the expensive Character model once per collected candidate.

### 4.5 Social association and delayed sharing

After a Deployment actually inspects content, it may associate it with:

- current Topic;
- previous conversation via perception-safe SQL-RAG;
- known Discord actor/Character via Social Graph/relationship evidence;
- a durable or synthesized Memory.

Share motivations may include:

```text
RELATED_TO_CURRENT_TOPIC
RELATED_TO_PAST_CONVERSATION
REMIND_ME_OF_SOMEONE
FUNNY
INTERESTING
USEFUL
ASK_FOR_OPINION
EMOTIONAL_REACTION
```

Interest is not equivalent to sharing. Most interesting content should not create a Discord message.

## 5. Reserved future account integration

Real platform accounts remain out of the current implementation scope, but contracts must preserve a clean future path.

Reserved abstractions:

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

Discovery adapters and future account/action adapters stay separable:

```text
YouTubeDiscoveryAdapter
YouTubeAccountAdapter       # future

BilibiliDiscoveryAdapter
BilibiliAccountAdapter      # future
```

Future account credentials stay in encrypted credential infrastructure. Character models never receive raw platform credentials or arbitrary write access.

Current implementation must not add OAuth, login sessions, Like/Follow/Comment/Post/DM automation, account farming, or fake-engagement training of platform recommendation systems.

## 6. Implementation phases

Phase transition is driven by exit criteria and automated evidence. Routine phase advancement does not require owner confirmation; final acceptance remains owner-controlled.

### Phase 0 — Contracts, OpenWiki evidence map, and acceptance baseline

Implement:

- revise this canonical roadmap;
- add one branch acceptance/status checklist;
- record exact source contracts reused from Deployment, Discord Connector, Conversation Intelligence, Media Runtime, scheduler/condition-watch patterns;
- define Deployment-scoped Presence/Activity/Discovery domain contracts;
- preserve future Account adapter boundaries;
- add non-goals and invariants to tests/docs before runtime behavior changes.

Exit criteria:

- source paths are named and verified;
- one-Card-per-Server, Deployment-scoped lived state, Sleep Policy V1, and shared-content/per-Deployment-exposure boundaries are unambiguous.

### Phase 1 — Deployment uniqueness invariant

Implement:

- repository-level duplicate check by owner + platform + connection + workspace/guild + Character Card;
- API returns a clear conflict for any same-Card/same-Server duplicate regardless of channel;
- update path cannot move a Deployment into a conflicting server identity;
- migration/legacy inspection path identifies pre-existing duplicates without silently deleting data;
- tests for server-wide and legacy exact-channel deployments.

Exit criteria:

- no new duplicate Character Deployment can be created in one Discord Server;
- existing data is not destructively repaired automatically.

### Phase 2 — Deployment Presence foundation and Sleep Policy V1

Implement:

- persisted `DeploymentPresence` state/metadata;
- owner-scoped read/update API;
- Presence included in connector deployment contract;
- connector filters `SLEEPING` before Smart Participation;
- explicit mention/reply to sleeping Deployment is intercepted before Character Runtime;
- real Discord Bot sends system sleep notice;
- ambient messages remain silent;
- sleep-notice cooldown/dedupe;
- no wake behavior;
- Portal observation/control sufficient for manual testing.

Exit criteria:

- sleeping Deployment cannot call Character model/Tools or enter Smart Participation;
- explicit address yields only one bounded system notice;
- another Deployment of the same Card in another Server remains independent.

### Phase 3 — Presence scheduler and lightweight daily rhythm

Implement:

- dedicated Presence scheduler/service; do not overload `watch.condition`;
- persisted next transition/session state;
- opt-in Deployment rhythm configuration with safe defaults;
- deterministic bounded sleep variation and restart recovery;
- `SLEEPING -> IDLE` / `IDLE -> SLEEPING` transitions;
- observability for why/when a transition was scheduled/executed.

Exit criteria:

- restart does not reroll today's schedule unpredictably;
- disabled rhythm never changes Presence automatically;
- scheduler performs no Character LLM calls.

### Phase 4 — Discovery domain, shared pool, and Shadow mode

Implement:

- `DiscoveryItem` shared normalized content record;
- `DeploymentDiscoveryExposure` and `DeploymentDiscoveryDecision` records;
- source/canonical IDs, freshness, dedupe and TTL/cleanup boundaries;
- `SHADOW` mode as the first Discovery execution mode;
- decision trace/observability without Discord posting;
- reserve `PlatformIdentity`/`AccountBinding`/capability contracts without implementing credentials/actions.

Exit criteria:

- collecting content does not imply a Deployment perceived it;
- subjective records always include Deployment scope;
- Shadow mode cannot send external/social actions.

### Phase 5 — YouTube candidate collector and cheap ranking

Implement:

- official/supported YouTube candidate collector;
- interest/search and selected popular/trending sources;
- normalize into shared DiscoveryItem pool;
- build Discovery seeds from current server-scoped Topic/Learned State context;
- E5-first ranking, sparse/freshness/novelty signals, exploration allocation;
- strict candidate/shortlist budgets;
- no per-candidate Character LLM calls.

Exit criteria:

- one YouTube fetch can serve multiple Deployments through shared content records;
- each Deployment receives a different ranking from its own server context;
- ranking trace explains the major signals.

### Phase 6 — Browsing Activity Sessions

Implement:

- persisted `DeploymentActivitySession`;
- session lifecycle integrated with Presence (`IDLE <-> BROWSING`);
- random/bounded leisure opportunity scheduling;
- YouTube session candidate/open/watch budgets;
- attention levels `SCROLL_PAST/NOTICE/OPEN/WATCH/ENGAGE`;
- no browsing while sleeping/busy;
- session restart/recovery and activity observability.

Exit criteria:

- Portal/runtime can truthfully say a Deployment is currently browsing because a persisted session exists;
- session ending restores the appropriate Presence state;
- most candidates do not reach deep Media Understanding.

### Phase 7 — Selective Media Understanding and lived exposure

Implement:

- reuse existing canonical public-video resolver, yt-dlp transcript/metadata and Media Analysis cache;
- promote only justified `OPEN/WATCH/ENGAGE` items into deeper inspection;
- store objective Media understanding once where cache rules permit;
- store subjective Deployment exposure separately;
- feed bounded interest/media evidence into existing Learned State rather than a parallel interest DB.

Exit criteria:

- identical content does not trigger duplicate objective analysis per Deployment;
- a Deployment cannot later claim knowledge of an item it never exposed/inspected under the recorded level.

### Phase 8 — Conversation/Social association and shadow Social Intent

Implement:

- match exposed content against current/recent Topics;
- use perception-safe episodic SQL-RAG for past-conversation association;
- use Social Graph/relationship state for `REMIND_ME_OF_SOMEONE` style relevance;
- produce bounded `SocialIntent` / `WOULD_SHARE` decisions in Shadow mode;
- preserve reasons/evidence in observability;
- no Discord post yet.

Exit criteria:

- a developer can explain why an item was associated with a person/topic/history;
- most items still resolve to ignore/remember rather than share.

### Phase 9 — Review-mode Discord sharing

Implement:

- `REVIEW` mode that surfaces proposed share target/content/reason before delivery;
- Character model is invoked only after Runtime has already decided a share is eligible, to phrase the in-character message;
- policy/attention/cooldown/duplicate gates;
- explicit target server/channel authority;
- acceptance/rejection recorded for calibration.

Exit criteria:

- no autonomous posting in REVIEW mode;
- rejected shares can be used to tune decision thresholds without mutating Character Card truth.

### Phase 10 — Limited auto initiative

Implement only after Shadow/Review quality is acceptable:

- `AUTO` mode opt-in per Deployment;
- strict rolling share budget and same-topic/source cooldown;
- channel activity awareness/recent-share penalty;
- safe failure/retry/idempotency;
- full Runtime/Provider/Discovery trace coverage;
- one-click disable.

Exit criteria:

- behavior remains low-frequency and non-spammy under sustained operation;
- disabling AUTO immediately prevents new autonomous shares.

### Phase 11 — Bilibili Experimental adapter

Implement:

- isolated Bilibili candidate source adapter;
- feature flag + kill switch;
- normalize into the same DiscoveryItem contract;
- reuse current Bilibili/yt-dlp Media pipeline for selected items;
- no Bilibili account/login/action automation;
- upstream failure degrades only the Bilibili source, never the Discovery Runtime.

Exit criteria:

- YouTube behavior remains unaffected when Bilibili adapter is disabled/broken;
- Bilibili content follows the same per-Deployment exposure/attention semantics.

### Validation gate — before real social accounts

Required demonstration:

```text
Deployment has believable Presence
  -> sleeps and becomes unavailable
  -> real Bot reports sleep only on explicit address
  -> later wakes/enters a bounded browsing session
  -> discovers YouTube/Bilibili content
  -> inspects only a small subset
  -> remembers/associates only perceived content
  -> decides not to share most items
  -> occasionally proposes or sends a strong contextual share according to mode
  -> every important decision is observable and evidence-backed
```

Only after this gate should Account Phase A begin.

## 7. Future account phases

### Account Phase A — identity and binding

- `PlatformIdentity` persistence;
- `AccountBinding` lifecycle;
- encrypted credential references/OAuth adapter;
- capability discovery;
- no autonomous mutation required.

### Account Phase B — explicit low-risk actions

- only owner-approved actions supported by the specific platform;
- PolicyGate and ActionExecutor enforce permission/rate/audience constraints.

### Account Phase C — bounded external social presence

Requires a separate product/policy/security review before implementation:

- mentions/replies;
- limited posting/repost/like/follow where appropriate;
- external interaction history;
- explicit privacy rules before external relationships may influence Memory.

## 8. OpenWiki operating rule for this branch

Per `docs/ai-agent-development-workflow.md` and `openwiki/INSTRUCTIONS.md`:

1. this feature branch updates source/tests and canonical docs;
2. the PR carries the active evidence map;
3. generated OpenWiki baseline is **not** regenerated here as if the feature were already merged;
4. after owner acceptance and merge, run a separate `openwiki --update` refresh from updated `main` and review generated claims against source/tests.
