# Smart Participation V3 — Semantic Multi-Character Participation

Smart Participation V3 upgrades Character Relay from manual topic/keyword routing to semantic Character Card relevance while keeping runtime admission deterministic and fail-open.

## Scope

V3 includes:

- Optional Character Card Semantic Profiles backed by multilingual embeddings.
- A Character Shelf inspector that shows whether a card has an embedding and lets the user create or refresh it without a Deployment.
- Multilingual semantic relevance for incoming Discord messages.
- SQLite BLOB storage for cached embedding vectors; no Vector DB is required.
- Candidate-set admission instead of winner-takes-all routing.
- A default maximum of two Smart participants per normal user turn, configurable from one to three.
- Ordered multi-character turns so the second character sees the first character's delivered response in recent context.
- Minimal linked secondary → primary coordination using the existing Smart Participation group-role fields.
- Existing cooldown, channel rate limits, avoid phrases, and conservative lightweight follow-up behavior.
- Fail-open behavior when semantic embedding is disabled or unavailable.

V3 does **not** add long-term Memory, a Vector DB, LangGraph, or a general Character Relationship Graph.

## Optional Semantic Profile lifecycle

Creating a Character Card does not require an embedding. A card can exist, be edited, tested, or organized with no Semantic Profile at all.

Users can open **Semantic Profile** directly from the Character Shelf to inspect one card. The inspector reports:

- status: `not_created`, `ready`, `stale`, `invalid`, or `disabled`;
- embedding model;
- vector dimension;
- persisted vector byte size;
- source hash;
- created / updated timestamps;
- the Character Card identity text used as semantic source.

No raw vector values are exposed to the browser.

A user can explicitly choose **Create Semantic Profile** from that panel. Deployment is not required. After a card has opted in, later edits refresh the persisted profile when its semantic source changes.

Smart semantic runtime also remains self-healing: if a Character Card is later used by a Smart Discord deployment and no Semantic Profile exists yet, the scoring path may lazily create it when semantic relevance is actually needed. This keeps card-only creation lightweight while preserving Smart Participation behavior.

## Semantic Character Card profile

The Character Card is the semantic source of truth for participation relevance. A deterministic adapter builds participation-focused text from:

- display name
- subtitle / role
- subject type
- persona summary
- traits
- tags
- expected tone

Memory summary and forbidden-behavior text are deliberately excluded from the participation embedding.

When a Semantic Profile is explicitly created or first required by Smart semantic scoring:

```text
Character Card
  → deterministic participation semantic text
  → multilingual embedding
  → float32 vector
  → SQLite character_semantic_profiles
```

Each cached record stores the source hash, model name, dimension, semantic text, and vector BLOB. If the semantic source text and model are unchanged, the existing vector is reused.

Production uses `intfloat/multilingual-e5-small` through FastEmbed/ONNX. Query messages are embedded with the E5 `query:` prefix and Character Card profiles with `passage:`.

## Runtime semantic scoring

For a normal Discord user message, the Connector makes at most one semantic-scoring request for the active Smart deployments in that destination:

```text
User message
  → one query embedding
  → compare with cached Character Card vectors
  → semantic relevance per deployment
  → deterministic Smart Participation scorer
```

Raw vectors never leave the API. The Connector receives only relevance scores and profile readiness.

Semantic relevance is one signal, not runtime authority. V3 combines it with existing deterministic signals such as explicit routing, triggers, legacy topics/keywords, initiative, cooldown, avoid phrases, and rate limits.

If semantic scoring is unavailable, the Connector logs the failure and continues with the deterministic non-semantic signals.

## Legacy Participation Profile

`topics` and `keywords` remain supported for compatibility and fallback, but they are no longer intended to be the long-term semantic source of truth.

The long-term Participation Profile should primarily control behavior:

- enabled / disabled
- participation style / initiative
- threshold
- cooldown
- rate limits
- avoid phrases / hard boundaries
- explicit trigger phrases
- group coordination hints

## Multi-character candidate admission

V2 effectively selected one proactive winner. V3 first builds an eligible candidate set.

The top candidate must satisfy its own admission threshold. Additional candidates may join only when:

- they satisfy their own threshold;
- they have a character-specific reason (semantic relevance, topic, keyword, or explicit trigger), rather than only a generic question/help signal;
- their score is within the configured margin of the strongest candidate; and
- the configured participant cap has not been reached.

Default maximum participants: **2**.

This prevents generic dog-piling while allowing two characters with materially relevant perspectives to participate in the same user turn.

## Ordered execution

Selected deployments remain ordered. The Connector processes them sequentially:

```text
User
  → Character A
  → deliver A
  → append A to recent context
  → Character B
  → deliver B or Smart Output ignore
```

This allows the later character to complement, correct, challenge, support, or decline to add anything rather than generating duplicate answers in parallel.

## Linked secondary interjection

V3 reuses the existing minimal group fields for a first relationship-aware coordination behavior:

- primary character: `group_role = primary`
- attendant/supporting character: `group_role = secondary`
- secondary points to the primary with `preferred_follow_up_character_card_id`

When a user explicitly addresses one primary character by Character Relay name/alias, one eligible linked secondary may be inserted before the primary:

```text
User → Serena

Mira (secondary / interject)
  → first response

Serena (primary)
  → second response with Mira's output already in recent context
```

If multiple linked secondaries compete, V3 auto-selects one only when semantic relevance produces a sufficiently clear winner; otherwise it avoids the automatic interjection.

Native Discord replies remain exclusive to the replied-to character in V3.

## Observability

Connector events include semantic scoring diagnostics without logging raw vectors:

- `smart_participation_semantic_scored`
- `smart_participation_semantic_failed`

The deterministic Smart Participation decision log also includes:

- selected deployment IDs
- ordered turn roles
- per-candidate semantic relevance
- semantic score contribution
- existing literal/trigger/cooldown signals

For card-only workflows, the Character Shelf **Semantic Profile** inspector is the preferred way to verify persisted embedding state without needing Discord or a Deployment.

## Configuration

Python/API:

- `ECHO_MASQUE_SEMANTIC_PARTICIPATION_ENABLED`
- `ECHO_MASQUE_SEMANTIC_EMBEDDING_MODEL`
- `ECHO_MASQUE_SEMANTIC_EMBEDDING_MODEL_FILE`
- `ECHO_MASQUE_SEMANTIC_EMBEDDING_DIMENSION`
- `ECHO_MASQUE_SEMANTIC_EMBEDDING_CACHE_DIR`

Discord Connector:

- `DISCORD_SMART_PARTICIPATION_MAX_PARTICIPANTS` (default `2`, allowed `1..3`)

The production Docker image enables semantic participation and places the embedding-model cache under `/data/embedding-models` so it can reuse the Railway persistent volume.
