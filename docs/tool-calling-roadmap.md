# Tool Calling Roadmap

Character Relay Tool Calling is a general **Character Capability Module**, not a Discord-only feature. Tools let a character actively obtain external/current information or perform an action, while Character Card, RAG, Participant Runtime, and Runtime Authority keep their existing responsibilities.

## Goal

```text
Character Card
= who the character is

Knowledge / RAG
= what the character already knows

Participant Runtime
= how the character participates in the conversation

Tool Calling
= what the character can actively do outside normal chat participation

Runtime Authority
= whether a proposed action is actually legal and executable
```

A Tool Result is turn-local context by default. It is **not** automatically written into Knowledge/RAG or long-term Memory.

## Runtime / Tool boundary

Tool Calling must not duplicate normal participant behavior.

Participant Runtime remains responsible for conversational actions such as:

- deciding whether a Character speaks or stays silent
- reaction selection
- reply / quote targeting
- turn order and continuation
- Character mentions and participation routing

Tool Calling is reserved for capabilities that require external/current information or change shared state outside the normal message response path.

For social Tools, the intended product behavior is:

```text
Shared conversation state
        ↓
Character persona decides whether / how to act
        ↓
Tool proposal
        ↓
Runtime authority + policy validation
        ↓
Shared external state changes
        ↓
Group members can observe the result
```

The Tool capability itself is neutral. Character Card/persona should influence whether a Character uses it, how it frames the action, what it chooses, and whether it refuses a conversational request.

## Deployment-scoped assignment

Available tools are assigned **manually per Character Deployment** in Deployment Center.

The same Character Card may therefore have different capabilities in different deployments:

```text
Character A @ Deployment 1
- web.search
- utility.calculator

Character A @ Deployment 2
- scheduler.remind
- utility.current_time
```

Tool availability is not stored in the Character Card persona and does not change the Character Semantic Profile.

Character Relay currently does **not** use embedding-based Tool Retrieval. Runtime resolves the deployment allowlist from Tool Registry and passes all assigned, currently available native tool schemas to the Character LLM for that turn.

Embedding-based semantic Tool Retrieval is deferred until the registry is large enough that passing assigned schemas directly becomes inefficient.

## Runtime flow

```text
Character Turn
      ↓
Deployment Tool Profile
      ↓
Tool Registry
      ↓
Assigned + available native Tool schemas
      ↓
Character LLM
      ├─ final Smart Output
      └─ Tool Proposal
             ↓
        Tool Runtime
        ├─ deployment capability check
        ├─ provider / runtime availability
        ├─ input schema validation
        ├─ platform / destination scope
        ├─ network safety
        ├─ risk / side-effect policy
        └─ execution
             ↓
        Tool Result
             ↓
        Character LLM
             ↓
        Smart Output
             ↓
        Runtime Validation
```

The LLM proposes. Runtime remains authority.

The Tool loop remains bounded with `max_tool_rounds = 2`. After the configured rounds, Runtime makes a final model call without tools so a turn cannot become an unbounded agent loop. At most one side-effect Tool is allowed to complete in a single character turn.

Tool-capable turns also receive an explicit **Tool execution integrity** rule: tools are real Runtime capabilities, not roleplay. A character should not claim a reminder, poll, role assignment, music action, or other external/write/future action succeeded unless the corresponding Tool returned a successful result in that turn. The persisted Runtime record / Tool trace remains the authoritative proof of execution.

RAG remains an upstream Context Layer capability. A character should normally use supplied knowledge first; tools are for external/current information, deterministic utilities, random outcomes, file inspection, or explicit actions.

## Browser Capability

`web.search`, `image.search`, `places.search`, and rendered `web.fetch_page` use an internal Playwright + headless Chromium Browser Capability. Character-facing Tool IDs do not expose the browser implementation.

There is no Brave/Tavily/Serper Search API dependency and no Search API key.

### Lifecycle

Chromium is **not** started with the API process. Browser Manager starts only its lightweight cleanup loop.

```text
No Browser Tool use
→ Chromium OFF

First browser-backed Tool call
→ lazy launch Chromium
→ create isolated BrowserContext
→ execute Tool

Repeated calls shortly afterwards
→ reuse warm Chromium
→ reuse the owner/deployment BrowserContext
→ reuse a short-lived Page when appropriate

Idle
→ close Page after ~3 min
→ close BrowserContext after ~5 min
→ close Chromium after ~10 min with no contexts

Hard recycle
→ ~60 min browser lifetime
or
→ ~100 browser operations
```

Initial defaults are configurable through:

```text
CHARACTER_RELAY_BROWSER_PAGE_IDLE_SECONDS=180
CHARACTER_RELAY_BROWSER_CONTEXT_IDLE_SECONDS=300
CHARACTER_RELAY_BROWSER_IDLE_SECONDS=600
CHARACTER_RELAY_BROWSER_MAX_LIFETIME_SECONDS=3600
CHARACTER_RELAY_BROWSER_MAX_OPERATIONS=100
CHARACTER_RELAY_BROWSER_MAX_CONCURRENT_CONTEXTS=3
```

BrowserContext reuse is isolated by owner + deployment. Runtime does not expose arbitrary browser primitives such as JavaScript evaluation, login automation, arbitrary form submission, payment, or unrestricted clicking to the Character LLM.

All browser and HTTP destinations pass a public-URL guard that rejects localhost, private/reserved/non-routable addresses, credentials in URLs, and non-standard ports. Browser subrequests are guarded too.

`web.fetch_page` uses an HTTP fast path first. If the page looks like a JavaScript shell or has too little useful server-rendered text, it falls back to rendered Chromium reading.

## Tool Calling V1 — Core Tool Runtime ✅

- `web.search` ✅ — Playwright + Chromium public web search
- `web.fetch_page` ✅ — bounded HTTP fast path + rendered Chromium fallback
- `utility.calculator` ✅
- `utility.current_time` ✅
- `discord.search_messages` ✅ — current Discord channel/thread only
- `discord.create_poll` ✅ — current Discord channel/thread only

Discord Tools use the same managed Bot credential name as the Discord Connector:

```text
DISCORD_BOT_TOKEN
```

In multi-service deployments such as Railway, expose the same shared/project variable to both the Character Relay API service and the Discord Connector service.

Discord Tool scope comes from Runtime, not model-provided guild/channel IDs. Poll creation rejects bot-triggered autonomous creation and requires an explicit human poll/vote request.

## Tool Calling V1.1 — Contextual Utilities ✅

- `weather.get` ✅ — Open-Meteo current weather + short forecast; explicit location required
- `random.roll` ✅ — cryptographically strong `NdM+K` dice roll
- `random.choose` ✅ — cryptographically strong random selection from supplied options
- `image.search` ✅ — Playwright + Chromium image search with strict SafeSearch

`weather.get` does not require an API key. Location must come from the user/current context; Runtime does not guess a user's location.

`image.search` returns references to existing public images and source pages. It does not generate images.

## Tool Calling V1.2 — Persistent Actions ✅

- `scheduler.remind` ✅
- `scheduler.list` ✅
- `scheduler.cancel` ✅
- `places.search` ✅
- `file.inspect` ✅

### Scheduler

Reminders are persisted in SQLite and survive the current character turn / API restart. A background delivery service claims due reminders and delivers them later using the Character Deployment's Discord identity.

`scheduler.remind` supports either:

- relative `delay_seconds`; or
- timezone-aware ISO-8601 `scheduled_at`.

Reminder delivery is currently Discord-first. Webhook-mode deployments reuse the stored encrypted Character webhook binding. Bot-mode deployments use the shared `DISCORD_BOT_TOKEN`. Failed delivery is retried with a bounded attempt count.

Portal observability is available from **Portal Toolbox → Schedules / 提醒计划**. It shows the Character, destination, reminder text, scheduled/created/delivered time, status, attempt count, last error, and supports cancelling pending/processing reminders. A character merely saying “I will remind you” is not proof; a persisted reminder row in this viewer is the authority that `scheduler.remind` actually completed.

### Places

`places.search` uses Browser Capability for real-world place discovery. It requires an explicit location string and does not infer private user location.

### File inspection

`file.inspect` supports bounded temporary inspection of:

- text / Markdown / logs / YAML / XML
- JSON
- CSV preview
- PDF text extraction
- image metadata (format, dimensions, mode, frame count)

The maximum downloaded file size is 8 MiB. File contents are untrusted data and never become instructions. File inspection does **not** automatically persist a file into Knowledge/RAG.

Permanent ingestion remains a separate Knowledge workflow.

## Observability

Provider Trace exposes a privacy-safe category for faster debugging:

- `Tool Calling` — native Tool proposal/result rounds; exact Tool function names are shown when recorded.
- `Character Turn` — normal Discord character-generation turns.
- `Model Call` — other model calls that are not classified as the two categories above.

The Portal Provider Trace viewer can filter by category and status. New native Tool Calling traces record available Tool names, actual proposed Tool names, prior Tool calls, and Tool-result count without persisting Tool arguments, Tool Result bodies, API keys, or authorization headers as classification metadata.

## Tool Calling V2 — Event-driven & Social Tools ✅

- `watch.condition` ✅ — persisted bounded condition watches with deployment/account scope, minimum five-minute per-watch cadence, read-only background Tool evaluation, explicit expiry/attempt budgets, and Scheduler-backed notification delivery.
- `character.invite` ✅ — prompt-local Character coordination proposal using safe participant aliases, same-owner/current-destination validation, Smart Participation eligibility checks, one-proposal-per-turn bounds, and existing Discord participant continuation as final authority.

### Condition Watch authority

`watch.condition` can be created only from a human-initiated Character turn. Runtime persists the original concrete Discord channel/thread, checks the condition later with the Character's configured model plus only its assigned read-only Tools, and records the lifecycle as `active`, `triggered`, `expired`, `cancelled`, or `failed`.

A positive evaluation queues a real persisted reminder through the existing Scheduler delivery path. A Character saying that a watched condition has triggered is not authoritative until Runtime has recorded the transition.

### Character Invite authority

`character.invite` does not directly inject or force another Character to speak. The model can reference only prompt-local participant aliases such as `p1`; Runtime validates the candidate against the same owner, active Discord destination scope, exclusions, and Smart Participation mode. A successful Tool result is only `pending_runtime_validation`.

The proposal is bound to one Smart Output turn token and cannot leak into a later turn. Runtime may materialize at most that validated candidate through the existing Character mention primitive. The Discord Connector then applies the existing bounded continuation rules, participant/deployment checks, unique-turn protection, depth limit, and shared response budget. Bot-authored continuation turns cannot create further Character invites, preventing recursive invite trees.

## Tool Calling V3 — Shared Social Actions & Voice 🧭 Planned

V3 focuses on **group-visible actions** rather than personal-assistant utilities. `discord.create_poll` and `discord.search_messages` are already shipped in V1, so V3 does not duplicate poll or message-history features.

A V3 capability should normally satisfy all of the following:

- the effect is visible or directly experienced by other people in the shared Discord space
- Character persona can meaningfully affect whether the Tool is used and how it is used
- Runtime can bound the side effect and enforce Discord permissions independently of the model
- the feature does not duplicate Participant Runtime behavior

### V3.1 — Temporary Social Roles

Primary planned Tool:

- `discord.assign_temporary_role` 🧭 — create/reuse a zero-permission cosmetic role, assign it to a current-guild participant for a bounded duration, then remove/clean it automatically.

Optional companion Tool after the assignment lifecycle is stable:

- `discord.remove_temporary_role` 🧭 — remove a Character Relay-managed temporary social role before expiry.

Example social behavior:

```text
A group member says or does something notable
        ↓
Character persona decides a temporary title is appropriate
        ↓
discord.assign_temporary_role
        ↓
"今日最佳工程師" appears as a real Discord role
        ↓
Everyone in the server can observe the shared-state change
```

Runtime authority requirements:

- feature is opt-in per Discord connection / deployment and requires the Bot to hold `MANAGE_ROLES`
- target must resolve from the current guild/context through a Runtime-controlled participant/member alias; the model does not supply arbitrary guild IDs or raw target IDs
- only current-guild human members are eligible; no cross-guild targeting
- the Bot's Discord role hierarchy must allow the assignment
- created roles are **cosmetic only**: `permissions=0`, `hoist=false`, `mentionable=false`
- the model never controls permission bits, role position, administrator/moderator capabilities, or an existing privileged role
- title is normalized and bounded; reserved/admin-like names may be rejected by policy
- duration is bounded and configurable; the initial target is a short-lived social role with a conservative maximum such as 24 hours
- one Character turn still obeys the existing one-side-effect limit
- bot-authored recursive continuation/background turns cannot autonomously create role chains
- assignments are persisted so expiry/cleanup survives API or Connector restart
- a deterministic owner/admin removal path must exist even if the Character would refuse a conversational request to remove the role

Persistence should record at minimum:

```text
temporary_role_assignment
- owner_id
- deployment_id / character_id
- guild_id
- role_id
- target_user_id
- display_title
- source_message_id
- created_at
- expires_at
- status
```

The persisted record, not roleplay text, is authority that the assignment exists and when it should expire.

A later enhancement may emit a bounded `social_tool_completed` event back into Participant Runtime so other Characters can react naturally to a successful shared action. Such continuation must not be allowed to cascade into additional side-effect Tools.

### V3.2 — Full Music Playback

Goal: let a Character use its existing persona to search for, choose, queue, and play music that everyone in a Discord voice channel can hear.

Planned Character-facing Tools:

- `music.search` 🧭 — provider-neutral track search returning stable Runtime track references and metadata
- `music.play` 🧭 — start playback / establish the shared guild player when allowed
- `music.queue_add` 🧭 — add a resolved track to the shared queue
- `music.skip` 🧭 — skip the current track under Runtime policy
- `music.stop` 🧭 — stop playback and clear/leave according to Runtime policy
- `music.now_playing` 🧭 — read the current track and queue state

Character behavior remains persona-driven. For example, two Characters receiving “放點歌” may search different moods/genres, select different tracks, or refuse the conversational request. The music service itself does not contain persona logic.

#### Shared Guild Audio Service

Music playback must not create one Discord voice player per Character. Character Relay should maintain one shared audio runtime per guild:

```text
Character Runtime
       ↓
Music Tools
       ↓
GuildAudioService
├─ Voice Connection
├─ Audio Player
├─ Queue
└─ current Character / track attribution
       ↓
Discord Voice Channel
```

The Discord Connector owns the voice connection and audio output. The current connector uses `discord.js`; V3.2 will add the voice stack (for example `@discordjs/voice` plus the required Opus/FFmpeg path for the selected source formats) rather than attempting to stream audio through the Python HTTP Tool executor.

Scope / authority requirements:

- voice channel destination comes from Connector/Runtime context, never a model-provided channel ID
- initial join target should be the human initiator's current voice channel or an already-established Character Relay guild voice connection
- the Bot must pass Discord `CONNECT` / `SPEAK` and channel visibility checks
- one shared guild connection/player/queue prevents Characters from creating competing voice sessions
- queue entries retain which Character proposed them so later group interaction can attribute choices correctly
- arbitrary model-provided audio URLs are rejected; Characters operate on Runtime-issued `track_id` values
- conversational requests may be accepted/refused according to persona, but deterministic owner/admin controls such as an explicit stop/cleanup command bypass persona so a Character cannot hold a voice channel hostage
- reconnect, idle disconnect, queue bounds, track-duration bounds, and failed-stream recovery are Runtime responsibilities

#### Music source abstraction

Music source access should be provider-neutral:

```text
MusicSourceAdapter
├─ search(query / genre / mood)
├─ resolve(track_id)
└─ open_stream(track_id)
```

**Audius is the initial MVP provider candidate** because it offers music discovery/streaming APIs suitable for evaluating a zero-API-fee prototype. Production enablement still requires a fresh terms/licensing review and Runtime must respect provider streamability/access metadata.

The adapter boundary keeps Character Relay free to add or replace sources later, including a self-hosted royalty-free / CC-licensed library.

The initial implementation should not depend on YouTube audio extraction or Spotify rebroadcast. Provider/API availability does not by itself grant redistribution rights; source terms and track licensing remain part of production readiness.

“Free music API” also does not mean zero operating cost: Discord voice bandwidth, CPU/transcoding, storage/cache, and hosting remain Character Relay infrastructure costs.

#### Suggested V3 delivery order

1. Temporary Social Role Tool contract + Runtime policy / alias resolution.
2. Temporary role persistence, expiry cleanup, Discord permission/hierarchy validation, tests, and Portal observability.
3. Ship `discord.assign_temporary_role`; add early removal only after lifecycle/cleanup is stable.
4. Introduce provider-neutral `MusicSourceAdapter` and `GuildAudioService` contracts.
5. Add `music.search` with the first approved free/low-cost provider candidate.
6. Add Connector voice dependencies, one-guild player/queue lifecycle, and `music.play` / `music.queue_add`.
7. Add bounded `music.skip`, `music.stop`, `music.now_playing`, deterministic owner/admin override, and reconnect/idle cleanup.
8. Run Discord permission, multi-Character queue, deployment isolation, restart, and deployed smoke validation before marking V3 complete.

## Deferred / Cost-gated capabilities

### `image.generate`

Image generation remains a good group-visible Character capability, but it is **deferred rather than an explicit non-goal** until the operating-cost model is evaluated.

Before implementation, define:

- provider abstraction and current per-image pricing
- per-guild / per-deployment daily budgets
- concurrency and cooldown limits for proactive Character generations
- abuse/moderation policy
- image storage / attachment lifetime and bandwidth cost
- behavior when a Character wants to generate an image but Runtime budget denies the Tool

The initial Character-facing contract should describe a creative brief rather than expose raw provider/model controls, so persona decides what to create while Runtime remains free to change image providers.

## Explicit non-goals

The current roadmap does not include:

- `gif.search`
- `code.execute`
- paid Search API dependency
- embedding-based Tool Retrieval
- automatic Tool Result → RAG persistence
- LangGraph for the current Tool execution loop
- unlimited autonomous tool loops
- arbitrary browser scripting exposed to the LLM

## Provider compatibility

Character Tool Calling uses OpenAI-compatible native function tools (`tools`, assistant `tool_calls`, and `role=tool` results). Character Relay validates generated JSON arguments before execution; provider-generated arguments are never trusted directly.

If a configured Character LLM provider does not expose native Tool Calling through the Character Relay provider adapter, the character continues without tools rather than bypassing Runtime validation.
