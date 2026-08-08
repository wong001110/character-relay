# Context Layer + RAG V1

Context Layer + RAG V1 adds bounded, scoped knowledge retrieval to deployed Character Relay turns without changing Smart Participation, Smart Output, or Discord execution authority.

```text
Discord event
→ Routing / Smart Participation
→ CharacterTurnContext
   ├ recent Discord context
   ├ Smart Output message / participant / expression references
   └ scoped RAG knowledge
→ one Character LLM call
→ Smart Output V1
→ Runtime validation
→ Discord execution
```

RAG is context preparation, not a second LLM Judge. A normal turn still uses one character-model call.

## Context Layer boundary

`ContextOrchestrator` is the runtime boundary that prepares one `CharacterTurnContext` before the character model is called.

The current context contains:

- the existing `SmartOutputContext`, which owns prompt-local message, participant, Emoji, and Sticker references;
- bounded RAG knowledge chunks;
- a privacy-safe context trace for observability.

Smart Output does not know whether knowledge came from SQL sparse retrieval, a future vector store, or a future LangChain retriever. Discord execution remains unchanged.

## Knowledge model

RAG V1 stores three record types:

```text
Knowledge Base
→ Knowledge Document
→ Knowledge Chunk
```

A Knowledge Base defines retrieval scope and may optionally be limited to one Character Card.

A Knowledge Document is user-authored plain text. V1 stores the source text, SHA-256 digest, and chunk count.

Knowledge Chunks are deterministic retrieval units derived from the document.

### V1 ingestion limits

- plain-text documents only;
- maximum document length: 200,000 characters;
- default chunk size: 900 characters;
- default overlap: 120 characters;
- no PDF/file ingestion yet;
- no automatic chat-to-memory ingestion.

Documents are re-indexed in V1 by deleting and recreating them rather than editing chunks in place.

## Scope isolation

Every Knowledge Base is owner-scoped first. Location scope is explicit:

### `global`

Available to the owner's character turns across deployments. Creating a global Knowledge Base is an explicit sharing choice; it cannot include Discord connection, Server, Channel, or Thread filters.

### `server`

Requires a Discord `connection_id` and `guild_id`. It is available only in that connection + Server pair.

### `channel`

Requires `connection_id`, `guild_id`, and `channel_id`. An optional `thread_id` narrows it further.

### Optional Character filter

A Knowledge Base may specify `character_card_id`. If present, only turns for that Character Card can retrieve it.

The same Character Card deployed to Server A and Server B therefore does not automatically share Server-scoped knowledge.

## Retrieval

RAG V1 deliberately starts without embeddings or a Vector DB. It reuses Character Relay's deterministic sparse semantic approach:

- normalized alphanumeric tokens;
- Chinese character and bigram-aware tokens;
- cosine similarity;
- token overlap;
- exact normalized query match bonus.

The default retrieval path is:

```text
turn query
→ scope filter
→ bounded SQL chunk scan
→ sparse ranking
→ Top-K
→ context token budget
→ Character LLM
```

Defaults:

- Top-K: 4;
- maximum supported Top-K: 8;
- minimum sparse score: 0.05;
- maximum scanned eligible chunks per turn: 1,000;
- approximate knowledge context budget: 1,200 tokens.

The token estimate is provider-neutral (`~ characters / 4`) so RAG V1 does not introduce tokenizer dependencies.

The 1,000-chunk scan is an intentional V1 bound. Very large Knowledge Bases can become biased toward earlier persisted chunks and are a primary reason to introduce a Vector DB later.

## Retrieval query

For a substantive current message, RAG uses the current text directly.

For a short/low-information message, Context Layer may include up to two recent conversation messages to preserve the immediate topic.

If a turn contains only interpreted Discord Emoji/Sticker content, semantic descriptions may provide the retrieval query.

RAG V1 does not use an LLM query rewriter.

## Prompt safety

Retrieved knowledge is inserted as reference data, not executable instructions.

The character prompt explicitly says that retrieved excerpts must not override:

- the system prompt;
- character persona constraints;
- Character Relay runtime rules.

The model is also instructed not to reveal RAG internals, chunk IDs, or retrieval scores.

This reduces prompt-injection risk but does not make arbitrary retrieved content trusted. Runtime authority remains outside the model.

## Failure behavior

RAG is fail-open with respect to character availability:

```text
retrieval succeeds
→ add bounded knowledge context

no matching Knowledge Base / no relevant chunks
→ normal character turn without RAG knowledge

retrieval throws / storage unavailable
→ record warning trace
→ normal character turn without RAG knowledge
```

A RAG outage must not take the Discord character offline.

## Observability

The Discord Event Log can record:

- `context_built`;
- `rag_retrieval_completed`;
- `rag_retrieval_skipped`;
- `rag_retrieval_failed`.

The trace includes only metadata such as:

- RAG status/reason;
- query character count;
- eligible Knowledge Base count;
- candidate chunk count;
- selected chunk count;
- estimated selected knowledge tokens;
- configured budget;
- selected document IDs/titles, chunk indexes, and scores.

Retrieved chunk content is deliberately excluded from Discord Portal event logs.

The owner-authenticated RAG Retrieval Playground does display retrieved chunk content because its purpose is explicit retrieval inspection.

## Portal workflow

Deployment Center now contains a Knowledge Base panel for the selected Discord Server.

Users can:

- create Server, Channel, or explicit account-global Knowledge Bases;
- optionally restrict a Knowledge Base to one Character Card;
- enable/disable or delete a Knowledge Base;
- add/delete plain-text Knowledge Documents;
- see document chunk counts;
- use the Retrieval Playground to test Server/Channel/Character-scoped retrieval without making an LLM call.

This allows retrieval quality and isolation to be verified before testing the same knowledge through a live Discord character.

## API

Owner-authenticated endpoints:

```text
GET    /api/knowledge/bases
POST   /api/knowledge/bases
GET    /api/knowledge/bases/{base_id}
PUT    /api/knowledge/bases/{base_id}
DELETE /api/knowledge/bases/{base_id}

GET    /api/knowledge/bases/{base_id}/documents
POST   /api/knowledge/bases/{base_id}/documents
DELETE /api/knowledge/documents/{document_id}

POST   /api/knowledge/retrieve
```

The retrieval endpoint is intended for inspection/evaluation and returns retrieved content to the authenticated owner. Runtime Discord logs do not.

## Non-goals for V1

Context Layer + RAG V1 does not add:

- embeddings;
- pgvector, Qdrant, Chroma, or another Vector DB;
- long-term conversational memory;
- relationship memory;
- memory consolidation or forgetting;
- LangChain;
- Tool Calling;
- MCP;
- Local Participation Judge;
- Agentic RAG;
- autonomous multi-step retrieval loops.

## Next milestone

The next retrieval milestone is **Vector Memory / Vector DB** after RAG V1 behavior and retrieval requirements have been measured in real Discord usage.

The intended evolution remains:

```text
Context Layer contract
→ SQL-backed sparse RAG V1
→ retrieval quality / observability data
→ vector-backed retrieval where justified
→ long-term scoped Character Memory
```

The Context Layer and Smart Output contracts should remain stable while the retrieval backend evolves.
