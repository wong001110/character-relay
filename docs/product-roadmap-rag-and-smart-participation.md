# Character Relay: RAG Evaluation and Smart Participation Roadmap

This document records the product decisions made before implementation so later work does not blur separate concerns.

## 1. Keep four concerns separate

Character Relay should treat these as composable but independent modules:

1. **Smart Participation** — decide whether any character should speak and which character should speak.
2. **Memory / RAG** — retrieve relevant history, knowledge, lore, or relationship context after a character has been selected.
3. **Expression Retrieval** — retrieve a small set of Discord Emoji or Sticker candidates for the response model.
4. **RAG Evaluation** — test a customer's external AI/RAG API against customer-authored expected results.

Smart Participation does not require a Vector Database. Vector storage belongs to a later persistent-memory or knowledge-retrieval layer.

## 2. External RAG Evaluation direction

The initial RAG Evaluation feature should be API-first. Character Relay does not need direct access to a customer's Vector Database.

The customer supplies:

- API endpoint and HTTP method;
- authentication configuration;
- request-body mapping;
- response mapping for the final answer;
- optional response mapping for retrieved contexts, source IDs, citations, and scores;
- manually authored test cases and accepted results.

A test case may contain:

- question/input;
- expected answer or accepted answer rules;
- accepted source IDs;
- required phrases;
- forbidden phrases;
- optional expected evidence text.

Character Relay calls the customer API, maps its response, compares it with the customer's accepted result, and produces a report.

Two evaluation levels should be supported later:

- **Black-box** — the API returns only a final answer.
- **White-box** — the API also returns retrieved contexts, sources, citations, or traces.

This design avoids requiring customers to expose Vector DB credentials, embedding models, chunking configuration, or internal storage.

## 3. Smart Participation MVP

The first Smart Participation MVP must not add:

- a Vector Database;
- embeddings;
- a second LLM Judge call;
- persistent long-term memory.

It should provide a conservative deterministic gate:

1. Explicit Mention and Reply continue to work without the Smart gate.
2. Ordinary messages are evaluated only for deployments using `participation_mode=smart`.
3. Each character may have a configurable Participation Profile.
4. Fixed scoring selects at most one proactive character.
5. A minimum score and minimum lead over the runner-up are required.
6. Channel and per-character cooldowns limit interruption frequency.
7. Low-information acknowledgements and configured avoid phrases stay silent.
8. Decisions are logged with scores and reason codes.
9. Any failure defaults ordinary Smart messages to silence.

### Participation Profile

The connector MVP accepts profiles through `DISCORD_SMART_PARTICIPATION_PROFILES_JSON`.

Keys are resolved in this order:

1. deployment ID;
2. character-card ID;
3. character display name;
4. Discord identity display name;
5. `default`.

Example:

```json
{
  "character-zhi": {
    "topics": ["AI product", "software development", "Discord deployment", "RAG"],
    "keywords": ["API", "bug", "deploy", "deployment", "Discord", "vector db"],
    "trigger_phrases": ["how do I", "why", "怎么", "为什么", "有人知道"],
    "avoid_phrases": ["不要回答", "不用回答", "just documenting"],
    "initiative": 0.5,
    "minimum_score": 5,
    "cooldown_seconds": 120
  }
}
```

The initial profile is connector configuration rather than a database schema. A later Portal phase can persist and edit the same contract.

## 4. Future Participation Judge runtime

After the deterministic MVP collects real false-positive and false-negative examples, Character Relay may add an optional Participation Judge.

Supported runtime modes should eventually include:

- local model;
- self-hosted cloud model;
- external LLM API;
- hybrid primary plus API fallback.

The Judge should evaluate all candidate characters in one request and return a strict JSON decision. It must not generate the final character response.

Fallback principles:

- infrastructure or schema failure may trigger the configured fallback;
- a valid `silent` decision must not trigger a second opinion by default;
- if all Judge routes fail, ordinary Smart messages remain silent;
- explicit Mention and Reply remain available;
- cloud fallback must be explicit because it may send Discord content to an external provider.

## 5. Future persistent memory and Vector DB

Vector search should be introduced only when Character Relay needs persistent semantic retrieval across large amounts of history, lore, or knowledge.

A likely path is:

```text
SQLite / current SQL database
→ PostgreSQL
→ PostgreSQL + pgvector
```

Runtime data must remain scoped by workspace/account, Discord connection, Server, Channel/Thread, Deployment, character version, and user visibility policy.

## 6. Delivery sequence

1. Deterministic Smart Participation engine and tests.
2. Connector integration, conservative defaults, cooldowns, and decision logs.
3. Portal-backed Participation Profiles and per-Server/channel settings.
4. Evaluation dataset from real Smart decisions.
5. Optional local/cloud/API Participation Judge with fallback and circuit breaker.
6. Persistent memory and pgvector when justified by retrieval requirements.
7. External RAG Evaluation workspace using customer APIs and customer-authored accepted results.
