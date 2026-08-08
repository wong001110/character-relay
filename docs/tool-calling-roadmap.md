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

For the current roadmap, Character Relay does **not** use embedding-based Tool Retrieval. The Runtime resolves the deployment allowlist from the Tool Registry and passes all assigned native tool schemas to the Character LLM for that turn.

Embedding-based semantic Tool Retrieval may be considered only if the registry grows large enough that passing all assigned schemas becomes inefficient.

## Runtime flow

```text
Character Turn
      ↓
Deployment Tool Profile
      ↓
Tool Registry
      ↓
Assigned native Tool schemas
      ↓
Character LLM
      ├─ final Smart Output
      └─ Tool Proposal
             ↓
        Tool Runtime
        ├─ assignment / capability check
        ├─ input schema validation
        ├─ platform permission check (when applicable)
        ├─ risk / confirmation policy (when applicable)
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

V1 uses a bounded tool loop with `max_tool_rounds = 2`. After the configured rounds, the Runtime makes a final model call without tools so the turn cannot become an unbounded agent loop.

RAG remains an upstream Context Layer capability. A character should normally use existing supplied knowledge first; tools are for external/current information, deterministic utilities, or explicit actions.

## Roadmap

### Tool Calling V1 — Core Tool Runtime

- `web.search`
- `web.fetch_page`
- `utility.calculator`
- `utility.current_time`
- `discord.search_messages`
- `discord.create_poll`

V1 establishes Tool Registry, deployment assignment, native provider Tool Calling, bounded execution, validation, Tool Result context, and observability.

**Initial V1 test slice:**

- `utility.calculator`
- `utility.current_time`

These two deterministic read-only utilities are implemented first so the provider/runtime loop can be validated before external providers or Discord write actions are added.

### Tool Calling V1.1 — Contextual Utilities

- `weather.get`
- `random.roll`
- `random.choose`
- `image.search` — undecided / optional

### Tool Calling V1.2 — Persistent Actions

- `scheduler.remind`
- `scheduler.list`
- `scheduler.cancel`
- `places.search`
- `file.inspect`

Scheduler introduces a lifecycle that can continue beyond the current conversation turn. `file.inspect` is temporary inspection; permanent knowledge ingestion remains a separate Knowledge workflow.

### Tool Calling V2 — Event-driven & Social Tools

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

## V1 provider compatibility

The first implementation uses OpenAI-compatible native function tools (`tools`, assistant `tool_calls`, and `role=tool` results). Character Relay validates generated JSON arguments before execution; provider-generated arguments are never trusted directly.

If a configured provider does not expose native Tool Calling through the Character Relay provider adapter, the character continues without tools rather than bypassing Runtime validation.
