# Tool Calling Roadmap

Character Relay Tool Calling is a general **Character Capability Module**, not a Discord-only feature. Tools let a character actively obtain external/current information or perform an action, while Character Card, RAG, and Runtime Authority keep their existing responsibilities.

## Goal

```text
Character Card
= who the character is

Knowledge / RAG
= what the character already knows

Tool Calling
= what the character can actively do

Runtime Authority
= whether a proposed action is actually legal and executable
```

A Tool Result is turn-local context by default. It is **not** automatically written into Knowledge/RAG or long-term Memory.

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

Tool-capable turns also receive an explicit **Tool execution integrity** rule: tools are real Runtime capabilities, not roleplay. A character should not claim a reminder, poll, or other external/write/future action succeeded unless the corresponding Tool returned a successful result in that turn. The persisted Runtime record / Tool trace remains the authoritative proof of execution.

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

## Explicit non-goals

The current roadmap does not include:

- `gif.search`
- `code.execute`
- `image.generate`
- paid Search API dependency
- embedding-based Tool Retrieval
- automatic Tool Result → RAG persistence
- LangGraph for the current Tool execution loop
- unlimited autonomous tool loops
- arbitrary browser scripting exposed to the LLM

## Provider compatibility

Character Tool Calling uses OpenAI-compatible native function tools (`tools`, assistant `tool_calls`, and `role=tool` results). Character Relay validates generated JSON arguments before execution; provider-generated arguments are never trusted directly.

If a configured Character LLM provider does not expose native Tool Calling through the Character Relay provider adapter, the character continues without tools rather than bypassing Runtime validation.
