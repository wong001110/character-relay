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
- discord.create_poll
- utility.current_time
```

Tool availability is not stored in the Character Card persona and does not change the Character Semantic Profile.

For the current roadmap, Character Relay does **not** use embedding-based Tool Retrieval. The Runtime resolves the deployment allowlist from the Tool Registry and passes all assigned, currently available native tool schemas to the Character LLM for that turn.

Embedding-based semantic Tool Retrieval may be considered only if the registry grows large enough that passing all assigned schemas becomes inefficient.

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
        ├─ assignment / capability check
        ├─ provider availability check
        ├─ input schema validation
        ├─ platform / live scope check
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

V1 uses a bounded tool loop with `max_tool_rounds = 2`. After the configured rounds, the Runtime makes a final model call without tools so the turn cannot become an unbounded agent loop. At most one side-effect Tool is allowed to complete in a single character turn.

RAG remains an upstream Context Layer capability. A character should normally use existing supplied knowledge first; tools are for external/current information, deterministic utilities, or explicit actions.

## Tool Calling V1 — Core Tool Runtime ✅

V1 is implemented with:

- `web.search` ✅ — Brave Web Search
- `web.fetch_page` ✅ — bounded public-page fetch with SSRF/redirect/content guards
- `utility.calculator` ✅
- `utility.current_time` ✅
- `discord.search_messages` ✅ — current Discord channel/thread only
- `discord.create_poll` ✅ — current Discord channel/thread only

V1 establishes Tool Registry, Deployment assignment, native provider Tool Calling, bounded execution, validation, turn-local Tool Result context, provider availability, side-effect limits, and privacy-safe observability.

### V1 provider configuration

`web.search` uses Brave Search and requires:

```text
ECHO_MASQUE_BRAVE_SEARCH_API_KEY
```

`discord.search_messages` and `discord.create_poll` execute through Discord's HTTP API and require the API service to receive the same managed Bot credential used by the Discord Connector:

```text
ECHO_MASQUE_DISCORD_TOOL_BOT_TOKEN
```

The credential is server-side only and is never included in Tool schemas, Tool Results, Character prompts, or Portal responses.

`web.fetch_page` does not require a provider key. It accepts only public HTTP(S) destinations on standard web ports, validates redirects, rejects non-public address ranges, limits the response body to 1 MiB, and extracts bounded readable text. Web/search Tool Results are explicitly marked as untrusted external data.

`discord.search_messages` cannot choose an arbitrary Discord scope: Runtime injects the current guild/channel/thread from the admitted turn. `discord.create_poll` uses the same current scope, rejects bot-triggered autonomous creation, requires an explicit human poll/vote request in the triggering message, and counts as a side-effect Tool.

## Tool Calling V1.1 — Contextual Utilities

- `weather.get`
- `random.roll`
- `random.choose`
- `image.search` ✅ **confirmed and implemented early** — Brave Image Search with Runtime-enforced strict SafeSearch

`image.search` shares `ECHO_MASQUE_BRAVE_SEARCH_API_KEY` with `web.search`. It returns references to existing public images and their source pages; it does not generate images.

## Tool Calling V1.2 — Persistent Actions

- `scheduler.remind`
- `scheduler.list`
- `scheduler.cancel`
- `places.search`
- `file.inspect`

Scheduler introduces a lifecycle that can continue beyond the current conversation turn. `file.inspect` is temporary inspection; permanent knowledge ingestion remains a separate Knowledge workflow.

## Tool Calling V2 — Event-driven & Social Tools

- `watch.condition`
- `character.invite`

`watch.condition` introduces future condition-driven Character events. `character.invite` lets an admitted character propose that another character join the turn, subject to Runtime coordination, relationship/capability rules, participant limits, and redundancy checks.

## Explicit non-goals

The current roadmap does not include:

- `gif.search`
- `code.execute`
- `image.generate`
- embedding-based Tool Retrieval
- automatic Tool Result → RAG persistence
- LangGraph for the V1/V1.1/V1.2 execution loop
- unlimited autonomous tool loops

## Provider compatibility

The implementation uses OpenAI-compatible native function tools (`tools`, assistant `tool_calls`, and `role=tool` results). Character Relay validates generated JSON arguments before execution; provider-generated arguments are never trusted directly.

If a configured Character LLM provider does not expose native Tool Calling through the Character Relay provider adapter, the character continues without tools rather than bypassing Runtime validation.
