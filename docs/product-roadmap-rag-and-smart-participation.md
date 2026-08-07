# Character Relay Runtime Roadmap

This document records the current runtime boundaries for Discord Smart Participation, Smart Output, future RAG / Vector Memory, and Tool Calling. The goal is to keep social behavior flexible without turning the whole Discord connector into an LLM-controlled agent.

## 1. Runtime boundaries

Character Relay should keep these concerns separate:

1. **Routing** — resolve explicit Discord addressing such as Mention, Reply, Server/Channel scope, and active deployments.
2. **Smart Participation** — decide whether an unaddressed message should give any character a turn, and which character receives that turn.
3. **Context** — collect recent conversation, future RAG / Vector Memory, relationship context, expression candidates, and other bounded context for the selected character.
4. **Smart Output** — let the selected character choose a natural social action such as silence, reaction, sticker, direct message, reply-to-message, inline Emoji, or character Mention.
5. **Execution** — validate permissions, resource availability, self-Mention rules, chain limits, rate limits, and Discord API delivery.
6. **RAG Evaluation** — test an external customer's AI/RAG API against customer-authored expected results. This remains separate from the deployed character runtime.

A recurring design rule is:

> LLM output is a proposal. Character Relay Runtime remains the authority that validates and executes it.

## 2. Production Smart Participation V2

Smart Participation is a **Smart Turn Selector**, not a response generator and not an LLM Judge.

The production path remains deterministic:

1. Explicit Mention and Reply bypass proactive Smart selection and continue to target the addressed character directly.
2. Ordinary messages are considered only for deployments using `participation_mode=smart`.
3. Participation Profiles supply topics, keywords, trigger phrases, avoid phrases, style, initiative, thresholds, and cooldowns.
4. Fixed scoring selects at most one proactive character.
5. A minimum score and minimum lead over the runner-up are required.
6. Per-character and per-channel limits protect the conversation from interruptions and excessive model calls.
7. Smart selection is first reserved, then counted when the selected turn is admitted into Character Runtime rather than when the scorer merely evaluates it.
8. Decisions remain observable through score and reason logs.
9. Any deterministic failure remains fail-closed for unaddressed Smart messages.

### 2.1 Lightweight social follow-up

Short acknowledgements such as `lol`, `haha`, `thanks`, `好的`, `哈哈`, `晚安`, and similar messages are no longer treated as universally meaningless.

They may receive one conservative lightweight follow-up when:

- a Smart character had the most recent admitted turn in the same Discord destination;
- that turn is still inside the lightweight follow-up window;
- the character is still active and enabled;
- no avoid rule blocks the message; and
- the immediately previous Smart turn was not itself a lightweight follow-up.

This gives Smart Output an opportunity to choose a lightweight reaction, Emoji, Sticker, short reply, or silence without opening repeated acknowledgement loops.

If there is no recent character turn to anchor the acknowledgement, the message stays silent as before.

### 2.2 Automatic Primary → Secondary follow-up

Automatic untagged Primary-to-Secondary continuation is now **disabled by default**.

The preferred direction is explicit character intent:

- a character explicitly Mentions another active character when it wants that character to answer;
- self-Mention is rejected by Runtime;
- bot-to-bot chains are bounded by unique-participant and response budgets.

The existing Primary/Secondary follow-up implementation is retained only as a compatibility path and may be explicitly enabled for legacy behavior.

## 3. Smart Output target protocol

Smart Output should eventually replace the current "visible reply plus expression control marker" with one structured character action.

Target actions:

```text
ignore
react
sticker
message
```

A `message` may support:

- normal text;
- normal Unicode Emoji directly in text;
- structured custom Emoji references selected from Expression Retrieval;
- structured character/user Mentions;
- optional `reply_to` message reference;
- direct channel speech when `reply_to` is omitted.

Discord IDs, raw custom Emoji IDs, raw Sticker IDs, permission decisions, and execution authority stay outside the LLM.

### 3.1 Resource retrieval

The existing Expression Retrieval design remains the resource provider for custom Emoji and Stickers:

```text
Server expression dictionary
→ available / enabled / allowed-action filtering
→ semantic ranking + recent-use penalty
→ small Top-K candidate set
→ selected character model
```

Do not send the entire Server Emoji or Sticker dictionary to the model.

### 3.2 Token policy

The normal Smart path should keep one main character-model call:

```text
Deterministic routing
→ deterministic Smart Participation
→ deterministic retrieval
→ one Character LLM call
→ deterministic validation / execution
```

Extra LLM calls are justified only when a future Tool Call or another explicitly Mentioned character requires another turn.

## 4. Future Local Participation Judge — reserved architecture

A Local LLM Judge is **not part of the current implementation**. The architecture should remain compatible with it without making Smart Participation depend on it.

The future abstraction should behave like a replaceable Participation Decision Provider:

```text
Hard deterministic gates
→ deterministic scorer
→ clear winner? return it
→ ambiguous case? optional Local Judge
→ validate Judge proposal
→ selected character or silence
```

The recommended future mode is **hybrid**, not Judge-every-message:

- clear deterministic cases never call the Judge;
- ambiguous margins, weak social cues, or difficult multi-character choices may call the Local Judge;
- the Judge evaluates all eligible candidates in one request;
- the Judge returns strict structured selection only and never writes the character response;
- cooldowns, permissions, deployment state, rate limits, and execution rules remain deterministic Runtime authority.

### 4.1 Local Judge failure fallback

If the local model server is down, times out, returns malformed output, selects an unknown character, or otherwise fails validation:

```text
Local Judge failure
→ deterministic Smart Participation fallback
→ continue normal runtime
```

The Discord bot should degrade in selection quality rather than stop functioning.

No external/cloud Judge fallback should be enabled implicitly because it would change privacy, cost, and latency characteristics.

## 5. Future Context Layer: RAG, Vector DB, LangChain

RAG and Vector Memory belong after character selection and before Smart Output.

They should not replace Smart Participation.

A future Context Orchestrator may combine:

- recent Discord conversation;
- character card and runtime profile;
- RAG knowledge retrieval;
- Vector Memory;
- user/character relationship memory;
- Server/channel knowledge;
- Expression Retrieval;
- active participants;
- future Tool results.

The selected context should be ranked and budgeted before entering the character model.

### 5.1 Data isolation

Persistent retrieval must remain scoped by metadata such as:

- owner/workspace;
- Discord connection;
- Guild/Server;
- Channel/Thread;
- Deployment;
- Character / character version;
- User or relationship scope;
- memory/knowledge type.

Server A data must not silently leak into Server B merely because the same Character Card is deployed to both.

### 5.2 Initial RAG shape

Prefer a predictable two-step runtime first:

```text
query/context signal
→ retrieve Top-K
→ one Character LLM call
```

LangChain may later provide retrievers, context composition, structured output, and tool orchestration. A full autonomous agent loop is not required for the initial RAG implementation.

A likely storage evolution remains:

```text
current SQL storage
→ PostgreSQL
→ PostgreSQL + pgvector or another justified Vector DB
```

## 6. Future Tool Calling

Tool Calling is in future scope.

Examples for Discord characters may include:

- search project issues or pull requests;
- read deployment status;
- query internal services;
- retrieve project/task information;
- create explicitly authorized tasks or records;
- call application-specific APIs.

Tool availability must be filtered by character, workspace, server, user authorization, and current task. Tool execution remains Runtime-controlled and audited.

**MCP is not currently in the Character Relay roadmap.** If interoperability requirements change later it can be reconsidered, but current planning should assume direct Tool Calling integrations.

## 7. External RAG Evaluation direction

The RAG Evaluation feature remains API-first. Character Relay does not need direct access to a customer's Vector Database.

The customer supplies:

- API endpoint and HTTP method;
- authentication configuration;
- request-body mapping;
- response mapping for the final answer;
- optional response mapping for retrieved contexts, source IDs, citations, and scores;
- manually authored test cases and accepted results.

Two evaluation levels may be supported:

- **Black-box** — only the final answer is available.
- **White-box** — retrieved contexts, sources, citations, or traces are also available.

This keeps external RAG testing separate from Character Relay's own future memory stack.

## 8. Delivery sequence

### Production now

1. Deterministic Smart Participation and Participation Profiles.
2. Server/channel deployment routing, explicit Mention/Reply, cooldowns, and rate limits.
3. Expression Retrieval with available/enabled/action filtering and bounded Top-K candidates.
4. Smart Participation V2 lightweight follow-up and admission-based proactive accounting.
5. Automatic untagged Primary → Secondary follow-up disabled by default.

### Next

6. Unified Smart Output action schema: `ignore | react | sticker | message`.
7. Structured Mention/custom-Emoji references and optional `reply_to`.
8. Bot-chain guard based on bounded responses and unique participant tracking.
9. Execution-confirmed participation accounting once Smart Output has a stable delivery callback.

### Later

10. Evaluation dataset from real Smart Participation decisions.
11. Optional hybrid Local Participation Judge with deterministic fallback when the local server is unavailable.
12. Persistent memory / RAG / Vector DB with strict Server and account isolation.
13. LangChain-based retrieval/context orchestration where it reduces implementation complexity.
14. Tool Calling with explicit permissions and auditability.
15. External RAG Evaluation workspace using customer APIs and customer-authored expected results.
