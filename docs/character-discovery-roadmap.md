# Character Discovery / Social Discovery Roadmap

> Status: **Planned / documentation only**
>
> This roadmap records a future Character Relay direction. It does **not** authorize implementation work yet. No OAuth flow, platform login, social-account mutation, automated posting, liking, following, commenting, or external account action should be implemented as part of this roadmap entry.

## Goal

Extend Character Relay so a character can discover interesting content from external social/content platforms in a way that resembles ordinary social behavior:

```text
Discover something
  -> decide whether it is interesting to this character
  -> understand the content when needed
  -> form a reaction / opinion
  -> associate it with a person, topic, or previous conversation
  -> remember it when useful
  -> optionally bring it back into Discord naturally
```

The product goal is **character presence and initiative**, not a generic feed aggregator or social-media automation bot.

A successful first version should make behavior such as this possible:

> A character notices a video related to something discussed in Discord yesterday, remembers the connection, and later shares it into the relevant conversation with an in-character reaction.

## Product principles

### 1. Discovery comes before external account automation

The first implementation should prove that Character Relay can generate believable discovery behavior without requiring every character to own a real account on every platform.

A platform account is an optional actuator / identity, not the source of the character's interests or social cognition.

```text
Character Social Cognition
  -> Social Intent
  -> optional Platform Capability
```

Characters should still be able to conceptually like, dislike, remember, recommend, or want to follow something even when no external account is connected.

### 2. One Character Discovery Engine, many source adapters

Do not build a separate recommendation system for every platform.

```text
YouTube --------┐
Bilibili -------┤
X --------------┤
Reddit ---------┤ -> Source Adapters
Instagram ------┘
                     |
                     v
              Normalized Content
                     |
                     v
              Candidate Pool
                     |
                     v
             Character Discovery
```

Platform-specific code should stop at the adapter boundary. Character interest, ranking, memory, reasoning, and sharing behavior remain platform-independent.

### 3. Share behavior is not the same as interest

A character liking content does not automatically mean it should be posted into Discord.

The runtime should distinguish at least:

```text
Recommended
  -> Interested?
  -> Inspect / understand?
  -> React?
  -> Remember?
  -> Relevant to somebody / some conversation?
  -> Share?
```

This is required to avoid spammy behavior and preserve believable initiative.

### 4. Discovery should include exploration, not only exact interests

The virtual feed must not become a rigid keyword filter. Candidate selection should eventually mix:

- persistent character interests;
- temporary/recent interests;
- current Discord topics;
- relationship relevance ("this person may like it");
- novelty;
- exploration outside the normal interest profile;
- selected trending/popular content.

Exact weights are deliberately unspecified until an implementation phase is approved.

## Platform priority

### P0 — first Discovery sources

#### YouTube

Preferred first stable source.

Target use cases:

- long-form video discovery;
- Shorts where accessible through supported data paths;
- technology / AI;
- gaming;
- anime / ACG-adjacent content;
- music;
- creator content.

The implementation should prefer supported official APIs wherever possible.

#### Bilibili

High-value Discovery source for Chinese-language, ACG, AI, technology, gaming, meme, music, and creator content.

Status: **Experimental adapter**.

Bilibili discovery capabilities may require less stable platform-facing mechanisms than YouTube. The adapter must therefore be isolated so upstream changes cannot break the Character Discovery Engine.

### P1 — later sources

#### X

Primary value:

- real-time topics;
- developer discussion;
- memes;
- short-form public conversation;
- emerging events and project demos.

#### Reddit

Primary value:

- interest communities;
- niche topics;
- longer discussion;
- question/answer and opinion-rich content.

### P2 — later visual source

#### Instagram

Primary value:

- image-heavy discovery;
- creator posts;
- visual trends;
- Reels where supported by the available integration path.

### Deferred

#### TikTok

High product value for short-form discovery, but defer until a reliable and acceptable integration path is available.

### Explicitly not planned

#### Bluesky

Bluesky is not required for the current Character Discovery roadmap.

## Proposed high-level pipeline

```text
External Sources
    |
    v
Source Adapters
    |
    v
Normalized Content
    |
    v
Global Candidate Pool
    |
    +--> cache / freshness / source metadata
    +--> cross-source deduplication
    |
    v
Cheap Retrieval / Embedding Rank
    |
    v
Per-Character Interest Rank
    |
    v
Top Candidate Shortlist
    |
    v
Media / Content Understanding when needed
    |
    v
Bounded Judge / Decision Layer
    |
    +--> ignore
    +--> remember
    +--> react
    +--> associate with person/topic/memory
    +--> share to Discord
```

The expensive Character model should not be used as the first-pass filter for every collected item.

## Character interest model

The future system should support more than a flat list of tags.

Conceptually:

```text
Character Interest Profile
├── explicit interests
│   └── Character Card / creator configuration
├── learned interests
│   └── repeated positive interaction with discovered content
├── temporary interests
│   └── recently active curiosity that decays over time
├── social/context interests
│   └── current Discord topics and people the character knows
└── negative interests
    └── topics normally filtered or strongly deprioritized
```

The exact persistence and learning mechanism is intentionally deferred.

## Social association and Discord initiative

Discovery becomes valuable to Character Relay when external content can connect back to the character's existing social context.

Examples:

- `RELATED_TO_CURRENT_TOPIC`
- `RELATED_TO_PAST_CONVERSATION`
- `REMIND_ME_OF_SOMEONE`
- `FUNNY`
- `INTERESTING`
- `USEFUL`
- `ASK_FOR_OPINION`
- `EMOTIONAL_REACTION`

A possible future decision record may include:

```text
content interest
novelty
current-topic relevance
past-memory relevance
relationship relevance
share motivation
share confidence
cooldown / attention budget
```

The system should allow a character to see and remember content without sharing it immediately. A later Discord topic may retrieve that memory and create a natural delayed share.

## Shared cache and cost boundary

The same external content must not be fetched and fully understood separately for every character.

Preferred shape:

```text
Platform source
   -> fetch once
   -> normalize once
   -> shared cache
   -> shared base content understanding where safe
   -> per-character relevance / reaction
```

Per-character work should focus on subjective relevance and behavior, while objective content extraction/understanding should be reusable when the input and analysis contract are equivalent.

This should align with Character Relay's existing media-understanding cache direction rather than introducing a second unrelated cache system.

## Attention and anti-spam behavior

Discovery must have an attention budget. The character should not share every item that passes an interest threshold.

Future controls may include:

- bounded browse/discovery sessions;
- per-character daily or rolling attention budget;
- share-attempt budget;
- same-topic cooldown;
- same-source cooldown;
- duplicate-content suppression;
- channel/activity awareness;
- recent-share penalty;
- exploration probability.

Exact values are an implementation-phase concern.

# Reserved future account integration

Real platform accounts are **not part of the first implementation**, but the architecture must not make them difficult to add later.

The Character Discovery Engine and Character Social Brain must therefore stay independent from platform credentials and write APIs.

## Required future-facing abstractions

The following boundaries should be reserved in the domain architecture when this roadmap is eventually implemented.

### PlatformIdentity

Represents a character's identity on an external platform without embedding credentials into the Character Card or Social Brain.

Conceptual fields:

```text
character_id
platform
external_account_id
handle / display identity
status
capability_profile
credential_reference
```

### AccountBinding

Represents the user's explicit connection between a Character Relay character/deployment and an external social account.

It should remain separate from interest data and discovered-content history.

### CredentialReference / OAuth Adapter

Credentials must stay in Character Relay's encrypted credential infrastructure. Social components receive opaque references/capabilities rather than raw tokens.

No OAuth implementation is requested at this stage.

### PlatformCapability

Each adapter should declare what the connected account can actually do.

Examples:

```text
READ_PUBLIC_CONTENT
READ_HOME_FEED
READ_MENTIONS
PUBLISH
REPLY
LIKE
REPOST
FOLLOW
SAVE
COMMENT
DIRECT_MESSAGE
```

Capabilities must be platform-specific and permission-aware rather than assuming every social network supports the same operations.

### SocialIntent

The Character Social Brain should express intent independently from execution.

Example:

```json
{
  "content_ref": "external-content-id",
  "reaction": "LIKE",
  "want_to_share": true,
  "share_target": "discord",
  "want_to_follow_creator": false
}
```

A SocialIntent may exist even if no platform account is attached.

### CapabilityRouter

Resolves whether a SocialIntent has a valid actuator.

```text
SocialIntent
   -> account connected?
   -> capability granted?
   -> policy allows action?
   -> execute or retain as conceptual intent only
```

### PolicyGate

All future external mutations must cross a policy layer after the character decision.

The PolicyGate should be able to apply:

- owner configuration;
- platform rules/capability limits;
- action risk level;
- rate/cooldown limits;
- approval requirements;
- anti-spam rules;
- destination/audience restrictions.

### ActionExecutor

Platform-specific write operations belong below the PolicyGate.

The Character model should never directly call arbitrary social APIs with credentials.

```text
Character Social Brain
       |
       v
   SocialIntent
       |
       v
CapabilityRouter
       |
       v
   PolicyGate
       |
       v
Platform Action Executor
       |
       v
External Platform
```

## Read / write separation

Discovery adapters and account-action adapters should be logically separable.

For example:

```text
BilibiliDiscoveryAdapter
BilibiliAccountAdapter   (future)

YouTubeDiscoveryAdapter
YouTubeAccountAdapter    (future)
```

They may share transport/client primitives later, but the domain contract must not require account write access just to discover content.

## Future account phases

The following is only a directional sequence, not an approved implementation schedule.

### Account Phase A — identity and binding

- platform identity domain;
- account binding lifecycle;
- encrypted credential references;
- capability discovery;
- no autonomous mutation required yet.

### Account Phase B — low-risk explicit actions

Potential examples:

- publish only after explicit approval;
- react to already-approved content;
- narrowly scoped account operations.

Exact supported actions depend on each platform's official capabilities and policies at implementation time.

### Account Phase C — bounded autonomous social presence

Only after Discovery and Social Intent quality are validated:

- mentions/replies;
- limited posting;
- follow/repost/like where appropriate;
- persistent external interaction history;
- external relationships entering Character Memory under explicit privacy rules.

This phase requires a separate safety, platform-policy, consent, observability, and failure-recovery design review before implementation.

## Non-goals for the current roadmap entry

Do not implement yet:

- OAuth/login flows;
- browser automation for social accounts;
- automatic liking;
- automatic following;
- automatic commenting;
- automatic posting;
- automatic reposting;
- direct messages;
- per-character platform account farming;
- platform recommendation training through fake engagement;
- a second media-understanding stack dedicated only to social discovery.

## Suggested future implementation sequence

When this roadmap is explicitly activated, the intended order is:

```text
Phase 1 — External Perception
YouTube + Bilibili candidate collection and normalized content contract

Phase 2 — Character Discovery Feed
Interest ranking, exploration, deduplication, attention budget

Phase 3 — Content Understanding
Reuse Character Relay media understanding and shared cache boundaries

Phase 4 — Social Association
Current topic, past conversation, relationship, and memory relevance

Phase 5 — Discord Initiative
Natural bounded sharing / topic initiation with observability

Phase 6 — Persistent Discovery Memory
Remember seen, ignored, interesting, and shared content

---------------- validation gate ----------------

Phase 7 — Platform Identity / Account Binding
Reserved interfaces become real integrations

Phase 8 — External Account Actions
Policy-gated, capability-aware Like / Reply / Follow / Post where supported

Phase 9 — External Relationships
Persistent platform interaction history and relationship memory
```

Phase transitions should be approved based on observed behavior quality rather than platform count.

## Validation target for the first implementation

Before adding real social accounts, Character Relay should be able to demonstrate this loop reliably:

```text
YouTube / Bilibili
    -> discover candidate
    -> rank for a specific character
    -> inspect only when justified
    -> form an in-character reaction
    -> connect to relevant Discord context or memory
    -> decide not to share most items
    -> occasionally share a strong match naturally
    -> preserve enough trace evidence to explain why
```

If this behavior is not convincing, adding external account actions should not be treated as the solution.
