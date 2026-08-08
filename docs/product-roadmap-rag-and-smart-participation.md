# Character Relay Runtime Roadmap

This document records the current runtime boundaries for Discord Smart Participation, Smart Output, future RAG / Vector Memory, LangChain, and Tool Calling. The goal is to keep character behavior flexible without turning the whole Discord connector into an LLM-controlled agent.

## 1. Runtime boundaries

Character Relay keeps these concerns separate:

1. **Routing** — resolve explicit Discord addressing, Reply, Server/Channel scope, and active deployments.
2. **Smart Participation** — decide whether an unaddressed message should give any character a turn, and which character receives that turn.
3. **Context** — collect recent conversation, Expression candidates, active participants, and later RAG / Vector Memory / relationship context.
4. **Smart Output** — let the selected character choose one natural social action.
5. **Execution** — validate references, resources, permissions, self-Mention rules, chain limits, rate limits, and Discord delivery.
6. **RAG Evaluation** — evaluate an external customer's AI/RAG API against customer-authored expected results; this remains separate from deployed character runtime.

A recurring design rule is:

> LLM output is a proposal. Character Relay Runtime remains the authority that validates and executes it.

## 2. Production Smart Participation V2

Smart Participation is a **Smart Turn Selector**, not a response generator and not an LLM Judge.

The production path remains deterministic:

1. Explicit Mention and Reply bypass proactive Smart selection and target the addressed character directly.
2. Ordinary messages are considered only for deployments using `participation_mode=smart`.
3. Participation Profiles supply topics, keywords, trigger phrases, avoid phrases, style, initiative, thresholds, and cooldowns.
4. Fixed scoring selects at most one proactive character.
5. A minimum score and minimum lead over the runner-up are required.
6. Per-character and per-channel limits protect the conversation from interruptions and excessive provider calls.
7. Smart selection is reserved first and counted when the selected turn is admitted into Character Runtime rather than when the scorer merely evaluates it.
8. Decisions remain observable through score and reason logs.
9. Deterministic failure remains fail-closed for unaddressed Smart messages.

### 2.1 Lightweight social follow-up

Short acknowledgements such as `lol`, `haha`, `thanks`, `好的`, `哈哈`, `晚安`, and Emoji-only messages can receive one conservative lightweight follow-up when a recent Smart character turn provides an unambiguous social anchor.

The immediately previous Smart turn cannot itself be a lightweight follow-up, preventing acknowledgement loops.

### 2.2 Character-to-character continuation

Automatic untagged Primary → Secondary continuation is disabled by default.

The preferred path is explicit character intent through Smart Output. Runtime prevents self-Mention, retains depth/response budgets, and tracks characters already seen in the current human-triggered chain so a character cannot re-enter the same chain.

The old Primary/Secondary auto-follow path remains compatibility-only.

## 3. Production Smart Output V1

Smart Output V1 replaces the prompt-model runtime's old "visible reply plus `CR_EXPRESSION` marker" behavior with one structured character action:

```text
ignore
message
react
sticker
```

A `message` supports ordered content containing:

- normal text;
- Unicode Emoji directly in text;
- one retrieved custom Server Emoji reference in V1;
- structured human or active-character Mentions;
- optional `reply_to` message reference;
- direct channel speech when `reply_to` is omitted.

A Reaction selects one supplied message reference and one retrieved Emoji resource. A Sticker selects one retrieved Sticker and may optionally request a reply target.

The model receives prompt-local aliases instead of raw Discord user IDs, deployment IDs, or message IDs. Custom Emoji / Sticker choices must come from the bounded Expression Retrieval candidates.

See `docs/smart-output-v1.md` for the protocol and delivery rules.

### 3.1 Smart Output validation and failure policy

The normal prompt-model path uses one character-model call. Invalid Smart Output gets at most one regeneration attempt. If the second result is still invalid, the action becomes `ignore`.

Runtime validates the complete proposal before delivery. Invalid Mention, message reference, resource, or action causes the whole action to be skipped rather than partially applied.

For shared Bot identity, validated `reply_to` uses a real Discord Reply. Webhook character identity preserves its webhook identity and degrades a valid reply request to direct webhook delivery, recording the fallback explicitly.

### 3.2 Expression Retrieval remains the resource provider

Smart Output does not add another Emoji/Sticker database or LLM Judge.

```text
Server expression dictionary
→ available / enabled / allowed-action filtering
→ semantic ranking + recent-use penalty
→ bounded Top-K candidates
→ Smart Output
→ live Discord resource validation
```

The full Server Emoji/Sticker catalog is never sent to the model.

### 3.3 Token policy

The ordinary social path remains:

```text
Deterministic routing
→ deterministic Smart Participation
→ deterministic retrieval
→ one Character LLM call
→ deterministic validation / execution
```

A second character-model call occurs only for invalid structured-output regeneration, an explicitly triggered character turn, or later Tool Calling that genuinely requires another model round.

## 4. Next: Context Layer, RAG, and Vector Memory

With Smart Participation and Smart Output boundaries established, the next runtime milestone is a formal Context Layer.

A future `CharacterTurnContext` / Context Orchestrator should combine bounded providers such as:

- recent Discord conversation;
- character card and runtime profile;
- Expression Retrieval;
- active participants;
- RAG knowledge retrieval;
- Vector Memory;
- user/character relationship memory;
- Server/channel knowledge;
- future Tool results.

Smart Output should not need to know whether context came from SQL, a vector store, LangChain retriever, or another provider.

### 4.1 Initial RAG shape

Start with predictable two-step RAG:

```text
turn/query context
→ retrieve and rank Top-K
→ budget context
→ one Character LLM / Smart Output call
```

Do not start with an autonomous Agentic RAG loop.

### 4.2 Vector storage and isolation

Persistent retrieval must be scoped by metadata such as:

- owner/workspace;
- Discord connection;
- Guild/Server;
- Channel/Thread;
- Deployment;
- Character / character version;
- User or relationship scope;
- memory/knowledge type.

The same Character Card deployed to Server A and Server B must not silently merge private Server memories.

A likely storage evolution is:

```text
current SQL storage
→ PostgreSQL
→ PostgreSQL + pgvector or another justified Vector DB
```

The exact Vector DB should be selected after retrieval requirements and deployment constraints are measured rather than chosen only for architecture fashion.

### 4.3 LangChain

LangChain is future implementation infrastructure, not a required runtime authority.

It may be introduced for retrievers, context composition, evaluation utilities, and later Tool Calling orchestration when it reduces implementation complexity. Routing, Smart Participation, Discord execution, permissions, and resource validation stay owned by Character Relay.

## 5. Future Local Participation Judge — reserved architecture

A Local LLM Judge is not implemented now. Smart Participation remains compatible with a replaceable Judge without depending on one.

Recommended future hybrid path:

```text
Hard deterministic gates
→ deterministic scorer
→ clear winner? return it
→ ambiguous case? optional Local Judge
→ validate Judge proposal
→ selected character or silence
```

If the local model server is down, times out, returns malformed output, or selects an invalid character:

```text
Local Judge failure
→ deterministic Smart Participation fallback
→ continue normal runtime
```

The bot should degrade in selection quality rather than stop functioning. No cloud Judge fallback should be enabled implicitly.

## 6. Future Tool Calling

Tool Calling remains in future scope after Context/RAG foundations.

Examples include:

- search project issues or pull requests;
- read deployment status;
- query internal services;
- retrieve project/task information;
- create explicitly authorized tasks or records;
- call application-specific APIs.

Tool availability must be filtered by character, workspace, server, user authorization, and current task. Execution remains Runtime-controlled and audited.

**MCP is not currently in the Character Relay roadmap.** Current planning assumes direct Tool Calling integrations.

## 7. External RAG Evaluation direction

External RAG Evaluation stays API-first and separate from Character Relay's own memory runtime. Customers can provide an endpoint, authentication mapping, request/response mapping, expected answers, accepted sources, required/forbidden phrases, and optional retrieved evidence.

Both black-box answer evaluation and later white-box retrieval/source evaluation remain valid product directions.

## 8. Delivery sequence

### Production / current milestone

1. Deterministic Smart Participation and Portal Participation Profiles. ✅
2. Server/channel routing, explicit Mention/Reply, cooldowns, and rate limits. ✅
3. Expression Retrieval with available/enabled/action filtering and bounded Top-K candidates. ✅
4. Smart Participation V2 lightweight follow-up and admission-based accounting. ✅
5. Automatic untagged Primary → Secondary follow-up disabled by default. ✅
6. Smart Output V1 structured action schema. **Current implementation milestone.**
7. Structured Mention/custom-Emoji references, optional reply targets, atomic runtime validation, and unique-participant bot-chain guard. **Current implementation milestone.**

### Next

8. Formal `CharacterTurnContext` / Context Provider abstraction.
9. Two-step RAG MVP using bounded Top-K retrieval.
10. Persistent Vector Memory with strict Server/account/character/user scoping.
11. Retrieval evaluation, context budgeting, and observability.
12. Introduce LangChain components only where they simplify the above contracts.

### Later

13. Evaluation dataset from real Smart Participation decisions.
14. Optional hybrid Local Participation Judge with deterministic fallback.
15. Tool Calling with explicit permissions and auditability.
16. External RAG Evaluation workspace using customer APIs and customer-authored expected results.
