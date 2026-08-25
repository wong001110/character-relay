# Knowledge Fabric Architecture Contract

Status: **approved target architecture for `codex/knowledge-fabric-foundation`; implementation is pending and must proceed phase-by-phase**

Baseline: `main` at `68169b8d878ef4d8475e1e52c812fffcb19249a4`.

This contract defines the intended long-term Knowledge architecture for Character Relay. It deliberately optimizes for the desired product rather than preserving the current RAG V1 implementation. Until an implementation phase cuts a consumer over, current source/tests remain the runtime authority for that consumer.

## Goal

Replace the document-centric `Knowledge Base -> Document -> Chunk -> retrieve` model with a source-driven Knowledge Fabric that can ingest, version, index, update, authorize, and query large heterogeneous corpora without making the Character runtime depend on a particular storage engine, website shape, vector database, or summary format.

The target flow is:

```text
Knowledge Source
    ↓
Acquisition Adapter
    ↓
Immutable Source Version / Canonical Content
    ↓
Deterministic Parsing + Structure Preservation
    ↓
Evidence Units
    ↓
Canonical Entity / Extracted Assertion / Event interpretation
    ↓
Evidence reconciliation + indexes
    ↓
Knowledge Query Engine
    ↓
Epistemic Access
    ↓
Knowledge Context
    ↓
Context Resolver
    ↓
Character Runtime
```

Derived views are separate:

```text
Evidence + entities + reconciled corpus state
    ↓
Projection Engine
    ↓
Entity overview / corpus overview / timeline / relationship view
```

Projections are disposable caches. They never become a second source of truth.

## Non-negotiable authority rules

1. Raw source artifacts and immutable source versions are provenance truth for imported knowledge.
2. An Evidence Unit is a bounded, source-addressable interpretation target. A retrieval chunk is an index artifact, not truth.
3. `ExtractedAssertion` is an interpretation artifact produced from evidence. It must not become a second authority store competing with Character Belief.
4. Corpus/world knowledge and Character Belief are different domains. World knowledge describes what the available sources support; Belief describes what a Character currently knows or believes.
5. Server access to a corpus does not imply every Character in that server knows every fact in that corpus.
6. Character epistemic access is applied after system/server data authorization and before knowledge reaches the Character prompt.
7. Wiki/overview/summary text is always derived. Exact quotes, exact source claims, and provenance requests must resolve back to raw source evidence.
8. External Web/Image/API results are current-turn evidence candidates. They do not become permanent Knowledge merely because a search returned them.
9. Discovery candidates remain non-authoritative. The existing rule requiring Content Understanding/evidence acceptance is preserved.
10. LLM output is never the only retained representation of imported content. Source artifacts, canonical structure, provenance, hashes, and versions must survive independent of any enrichment model.
11. Ingestion, parsing, embedding, re-indexing, sync, and projection rebuilds run as background work. A Character reply request must not perform bulk corpus maintenance.
12. `unresolved`, `disputed`, `stale`, and `insufficient` are valid knowledge states. The system must not force a low-confidence identity or fact.
13. Intelligence Core v3 authority remains intact: Conversation Thread, Episode, Belief, Social State, Media perception, and Runtime permissions do not collapse into the Knowledge subsystem.
14. Public Demo remains server-enforced read-only and must not expose global/private corpus administration, source credentials, imported private content, or raw object-storage artifacts.

## Core domain model

### KnowledgeCorpus

A Corpus is a logical knowledge domain, not a physical vector collection and not a Discord server table.

Target fields include:

```text
KnowledgeCorpus
├ id
├ name
├ description
├ owner_type       system | user | organization | server
├ owner_id
├ visibility       private | shared | global
├ default_authority_profile
├ status
├ created_at
└ updated_at
```

V1 product policy may allow only Super Admin to create/manage `system + global` corpora. The schema must not hard-code that policy so future private workspace or organization corpora do not require another persistence redesign.

### KnowledgeSource

A Source records where knowledge comes from and how it is maintained.

```text
KnowledgeSource
├ id
├ corpus_id
├ source_type
├ locator
├ access_profile
├ parser_profile
├ sync_policy
├ freshness_policy
├ authority_profile
├ enabled
├ last_checked_at
├ last_changed_at
└ status
```

Supported source families are intentionally broader than Wiki:

- Git/GitHub repositories;
- local Git repositories or local folders through an upload/sync boundary;
- uploaded PDF, DOCX, PPTX, XLSX, Markdown, text, HTML, JSON, CSV and similar files;
- generic websites;
- specialized documentation sites such as Docusaurus/GitBook-style structures;
- Wiki engines such as MediaWiki;
- blogs/news sites;
- RSS/Atom;
- forums/threaded sources;
- APIs and structured datasets;
- databases through explicit schema/query adapters;
- media/transcript sources where allowed.

Use a generic adapter as fallback and specialized adapters when source-native structure is available. Do not flatten every source into generic scraped page text.

### SourceVersion and canonical content

Imported content is versioned rather than overwritten.

```text
SourceVersion
├ source_id
├ version_key
├ observed_at
├ published_at
├ source_hash
├ artifact_ref
└ metadata

CanonicalDocument
├ source_version_id
├ canonical_locator
├ title
├ language
├ mime/content type
└ metadata

Section / Block / Asset
├ parent relationship
├ structural path
├ content / object ref
├ page/line/symbol/table coordinates where available
└ source provenance
```

Original large artifacts belong in object storage. PostgreSQL stores the structured records, references, hashes, permissions, and queryable metadata rather than large opaque blobs.

### Evidence Unit

Evidence Units are stable source-addressable units derived from canonical content. They preserve source coordinates and are suitable for retrieval or interpretation.

Examples include:

- a DOCX paragraph under a heading;
- a PDF table with page coordinates;
- a source-code symbol/function body;
- a Wiki section;
- a forum post in a thread;
- a transcript segment with timestamps;
- a visual observation derived from an embedded diagram.

A retrieval chunk may reference one or more Evidence Units and can be regenerated when chunking/index strategy changes.

### Canonical Entity versus runtime entity

The current Intelligence v3 `EntityV3` is server-scoped and remains appropriate for provisional conversation identity. It must not become the sole identity model for global corpora.

Introduce a corpus/domain canonical entity layer:

```text
CanonicalEntity
├ id
├ domain/corpus identity
├ canonical name
├ type
├ aliases
└ provenance/status

Runtime Entity / Mention
    ↓ resolves_to (revisable evidence relation)
CanonicalEntity
```

A globally imported entity must not be duplicated once per Discord server merely because many servers discuss it.

### Extracted Assertion and corpus state

Natural-language evidence may be interpreted into a typed assertion:

```text
ExtractedAssertion
├ subject canonical entity/ref
├ predicate/type
├ object/value
├ qualifiers
├ temporal validity
├ evidence refs
├ confidence
├ producer/model metadata
└ status
```

This record is an interpretation artifact and retrieval/reconciliation aid. It is not a Character Belief. Conflicting assertions may coexist while corpus reconciliation marks support, dispute, supersession, version/time differences, or unresolved state.

### Event

Events represent what occurred in a corpus/world domain and remain evidence-backed. They may reference participants, location, story/project order, timestamps, effects/outcomes, and Evidence Units.

Do not reuse Conversation Episode as the universal world-event table. Conversation Episode remains the Intelligence v3 answer to “what happened in the Character Relay conversation/runtime.” Cross-links may exist through the Evidence Graph.

## Scope, access, and overlays

Knowledge storage scope and knowledge access are separate concepts.

### Canonical Server principal (Phase 2 decision)

The Knowledge Fabric Server principal is a durable `KnowledgeServerScope` identified by the exact
tuple `(platform, connection_id, workspace_id)`. It is deliberately distinct from connector
inventory, owner-scoped Discord Server Profiles, join-code access, and observed Discord roles.
Those records may support other product features but never authorize Knowledge Fabric access.

`KnowledgeServerAdministrator` is the only V1 server-local administrator membership. An
authenticated Super Admin bootstraps scopes and exclusively adds or removes these memberships.
There is no role-sync/profile fallback. Removing an administrator (including account deletion)
revokes only that membership; it never deletes the server scope, server-local corpus, or another
administrator. Connector deprovision must be an explicit audited lifecycle operation rather than
a side effect of transient catalog synchronization.

Public Demo has neither server membership nor global-library access. Its read API responses must
remain non-enumerating even though the shared read-only middleware permits ordinary GET requests.

Target hierarchy:

```text
System Global
    ↓ grant
Owner / Workspace shared or private
    ↓ grant
Server
    ↓ epistemic policy
Character
```

### KnowledgeAccessGrant

Global corpus data is stored once. Servers receive grants instead of copied corpus rows.

```text
KnowledgeAccessGrant
├ corpus_id
├ grantee_type      user | organization | server
├ grantee_id
├ enabled
├ access_mode
└ policy metadata
```

For first product delivery:

- Super Admin maintains system-global corpora;
- an explicit Knowledge Server Administrator may enable or disable an available global corpus for
  that server;
- server-local corpora remain private to that server unless another explicit sharing policy is later introduced.

### Knowledge policy / overlay behavior

Server-local knowledge may intentionally differ from global canon, especially for RP/AU or internal project variants. Do not mutate the global corpus to represent the server variant.

Policy semantics must be able to express:

- `inherit`: use global/shared corpus normally;
- `augment`: add server-local knowledge without overriding global facts;
- `override`: server-local supported knowledge shadows conflicting inherited knowledge for this server context;
- `deny`: inherited knowledge/domain is unavailable in this server context.

The Query Engine must surface provenance and precedence rather than destructively overwriting global records.

## Epistemic boundary

Data authorization answers “may this server/runtime access this corpus?” Character epistemic policy answers “should this Character know this information in-world?” They are different gates.

Target policy inputs may include:

```text
CharacterEpistemicPolicy
├ allowed corpora/domains
├ denied corpora/domains
├ timeline/story position
├ spoiler level
├ perspective/role
├ known entities
├ authored overrides
└ explicit server policy
```

The target query flow is:

```text
Request scope
→ authorized corpora and server overlays
→ retrieve candidate evidence/state
→ Character epistemic filter
→ bounded KnowledgeContext
```

This prevents an imported full-world corpus from turning every roleplay Character into an omniscient narrator.

## Ingestion/compiler pipeline

Knowledge ingestion is deterministic-first and LLM-last.

### Tier 0 — deterministic structure

Use parsers and source-native metadata for:

- source discovery and versioning;
- hash/diff/change detection;
- HTML/DOM/heading extraction;
- DOCX XML structure;
- PDF text/layout extraction where available;
- table/list/link preservation;
- source-code AST/symbol/import/dependency extraction;
- Git commit/tree/diff processing;
- MIME/language/basic metadata;
- deduplication;
- provenance coordinates.

Scanned PDFs use OCR/document vision only when a reliable text layer is unavailable. OCR is a fallback, not the default for every PDF.

### Tier 1 — local semantic processing

Use embeddings/small deterministic semantic models where appropriate for:

- semantic indexes;
- NER/entity candidate detection;
- similarity and near-duplicate detection;
- clustering;
- routing/classification where confidence is sufficient;
- representative-unit selection.

### Tier 2 — bounded inexpensive LLM enrichment

Use only when useful for:

- ambiguous entity resolution;
- extracted assertion/event interpretation;
- metadata repair;
- local section summaries when justified.

### Tier 3 — strong synthesis

Use selectively and preferably lazily for:

- cross-document synthesis;
- conflict interpretation;
- complex relationship/event understanding;
- high-quality materialized overviews.

No phase may introduce “send every chunk to an LLM and store the summary” as the ingestion architecture.

## Source-specific expectations

### Git/code repositories

Git-native version/diff semantics should drive incremental sync. Code files should preserve AST/symbol/reference/dependency structure so code questions can use symbol/graph retrieval rather than fixed text chunking alone.

### PDF/DOCX and other documents

Preserve section hierarchy, paragraphs, tables, lists, images, captions, page/section provenance, and structured table representations. For an embedded diagram, a visual observation may become evidence while the original asset remains referenced.

### Websites

Generic websites use canonical URL detection, main-content extraction, sitemap/link discovery, deduplication, and conditional requests where available. Specialized adapters should preserve revision/category/navigation/thread semantics instead of scraping rendered text only.

### Private/local content

Cloud Character Relay cannot directly read an arbitrary local path. Support either explicit upload/import or a future Local Sync Agent that watches allowed paths and transmits only approved changed content. Local sync must support `.gitignore`-style exclusion and deny common secret paths/material such as `.env`, private keys, credential files, dependency/build/cache directories by default.

## Storage target

The new architecture uses PostgreSQL as the formal primary relational store before large-scale ingestion is introduced.

PostgreSQL owns:

- corpus/source/version metadata;
- canonical content structure metadata;
- Evidence Units and provenance;
- canonical entities and interpretation records;
- access grants/policies;
- freshness/temporal state;
- ingestion job state/checkpoints;
- projection dependency metadata;
- relational filters and sparse/full-text search metadata.

Use `pgvector` as the initial dense retrieval index because the expected query path contains strong relational permission/scope/temporal filters. pgvector is an index implementation, not the definition of Knowledge.

Do not introduce Qdrant/Milvus/etc. in the first cutover unless measured scale requires it. Keep the vector index behind an interface so a specialized store can replace pgvector later without changing Context Resolver or Character Runtime.

Object storage (S3/R2-compatible) owns original and large artifacts such as PDF/DOCX snapshots, source archives, images, and other binary assets. The database stores object references and hashes rather than large source blobs.

### Phase 3 object-storage decision

Cloudflare R2 is the production object-storage provider. Knowledge Fabric uses R2 through its
S3-compatible protocol with private-by-default objects, allowing a future explicitly configured
AWS S3 deployment without changing the persistence or caller contract. The R2 endpoint, bucket,
access-key ID, and secret access key are deployment-only server settings; they are never stored in
Source fields, returned by an API, or copied into audit/log/trace metadata. Source-specific
third-party credentials remain separately scoped Credential Vault records when the corresponding
adapters are introduced.

## PostgreSQL cutover contract

PostgreSQL migration occurs before large Knowledge Fabric ingestion so the new schema is not designed twice around SQLite limitations.

The cutover must account for current SQLite-specific behavior in `Database`, including SQLite triggers, PRAGMA setup, local migration logic, and current Railway/storage assumptions. The phase must preserve all non-Knowledge runtime behavior and prove account/server/deployment/runtime isolation before Knowledge Fabric schema work continues.

The target is not indefinite dual-database authority. A bounded migration/export/import path may be needed for existing installations, but once production authority moves to PostgreSQL, SQLite-only runtime behavior must not remain as an implicit production fallback.

## Index and retrieval architecture

Use multiple retrieval channels:

```text
Query
  ↓
Query Planner
  ↓
Accessible Knowledge Space
  ├ PostgreSQL FTS / sparse retrieval
  ├ pgvector ANN dense retrieval
  ├ canonical entity lookup
  ├ graph/relation expansion
  └ temporal/freshness filtering
  ↓
Fusion (for example RRF-style)
  ↓
Rerank / diversify
  ↓
Evidence packing
  ↓
Epistemic filter / final KnowledgeContext
```

The Query Planner should model at least:

```text
intent
entities
candidate corpora
freshness requirement
source/authority requirement
temporal constraints
retrieval channels
answer/evidence mode
```

Examples of modes:

- overview: prefer a current materialized entity/corpus view plus high-value evidence;
- exact/quote: bypass summary authority and retrieve raw source-aligned evidence;
- relational: prefer canonical entity/relation/event evidence plus narrative support;
- current factual: apply freshness requirement and escalate to external lookup when local evidence is stale;
- code/project: use symbol/dependency + text/semantic evidence as appropriate.

## Freshness and sync

Freshness is a property of sources/content/query requirements, not one global cron interval.

Sources may expose policies such as:

- manual;
- daily;
- hourly;
- adaptive;
- webhook/change-feed when supported.

Use source-native change signals where possible: Git commit, API revision, Wiki revision, ETag, Last-Modified, sitemap diff, content hash, dataset version.

A source update performs incremental dependency invalidation:

```text
changed SourceVersion / Section
→ affected Evidence Units
→ affected sparse/vector indexes
→ affected assertions/events/entities
→ affected projections marked stale
```

Do not rebuild an entire corpus when only a small source region changed.

### Current-turn live fallback

When a query requires fresh information and local evidence is missing/stale:

```text
local retrieval
→ freshness/sufficiency check
→ Web/API Tool when authorized
→ turn-local evidence
→ answer
→ optional ingestion candidate for a registered Source
```

The last step is not automatic truth promotion. Accepted imported evidence follows normal authority/provenance rules.

## Projection Layer

Conceptually retire separate “KB Wiki” and “Server Wiki” authority-shaped abstractions. Replace them with one Projection Layer that can materialize:

- corpus overview;
- canonical entity overview;
- project/concept view;
- event/timeline view;
- relationship view;
- source/document summary.

Projection requirements:

- derived from explicit source/evidence dependencies;
- stores source hash/version and provenance;
- stale when a dependency changes;
- lazily rebuilt where reasonable;
- safely deletable and regenerable;
- never used as the sole evidence for exact-detail/quote/provenance queries.

Existing Wiki persistence can be migrated/reused only if it conforms to this contract. Do not preserve the word “Wiki” as a runtime boundary merely for compatibility.

## Character runtime integration

`CharacterTurnContextV3Service` must eventually depend on one `KnowledgeQueryEngine`, not separately on raw RAG and Server Wiki repositories.

Target integration:

```text
Character turn
→ Conversation/Belief/Social/Media v3 context
→ KnowledgeQueryEngine.query(scope, character, query)
→ KnowledgeContext
→ ContextResolverV3
→ bounded prompt sections
```

`KnowledgeContext` should expose semantic categories rather than storage implementation details, for example:

```text
facts/assertions
world events
narrative/raw evidence
materialized views
provenance
confidence/uncertainty
freshness
```

Context Resolver decides what fits in the prompt budget. It must not know whether an item came from a PDF parser, Git adapter, website, FTS, pgvector, or Projection cache.

Smart Participation must not execute the full Knowledge Query Engine for every candidate Character. Admission/routing may use cheap entity/relevance signals, but expensive corpus retrieval occurs only after a Character/turn is selected unless a separately bounded planner requirement proves otherwise.

## Internal Character tools

The implementation target replaces `wiki.lookup` as the conceptual runtime tool with a provider-neutral `knowledge.search` capability. It may support bounded modes such as `auto`, `overview`, `exact`, `relationship`, or `timeline`, but the Character model must not need to know which projection/index backend served the result.

`memory.search` and `conversation.search` remain separate because Character Belief and Conversation/Episode recall are different authorities from external/curated world knowledge.

## Security and privacy

- Authorization filters must be enforced before retrieval ranking, not only after results return.
- A server must not infer the existence, title, entity inventory, source URI, vector hit, or projection of a corpus it cannot access.
- Source credentials/tokens belong in the existing credential/security boundary or a dedicated scoped extension; never persist secrets in Source locator metadata or evidence text.
- Private/local source ingestion must exclude common secrets and support explicit allow/deny patterns.
- Imported content is untrusted data for LLM enrichment. It cannot issue instructions to the Runtime or Utility model.
- Object-storage artifacts use scoped/private access; do not expose bucket/object URLs as public authority by default.
- Observability records may include IDs, status, counts, timing, hashes, retrieval channel, and bounded scores, but must not copy private raw documents into ordinary logs/traces.

## Account and ownership lifecycle

Current account deletion/local-workspace claim code explicitly owns current Knowledge/Wiki rows. New corpus/source/access/object ownership must participate in the same lifecycle.

Deletion/claim policy must distinguish:

- system-global corpora, which are not deleted with an ordinary user;
- user/workspace-owned private corpora;
- server-local corpora;
- grants from a user/server to a system corpus;
- object-storage artifacts;
- derived vectors/projections/job records.

Derived indexes/projections must never survive as cross-owner data leaks after source/ownership deletion.

## Portal/Admin target

The current document-CRUD panel is replaced by a Corpus/Source-first management experience.

Super Admin target surface:

```text
Global Knowledge Library
├ corpora
├ sources
├ sync/index health
├ ingestion jobs/errors
├ source authority/freshness
├ rebuild/retry controls
└ evidence/query inspection
```

Server target surface:

```text
Server Knowledge
├ enabled Global/Shared corpora
├ local corpora/sources
├ inherit/augment/override/deny policy
├ Character epistemic policy (later phase)
└ scoped Query Inspector
```

Public Demo must hide or hard-disable writes and private/global administration.

## Explicit compatibility/deprecation rules

The following are current implementation concepts, not long-term architecture contracts:

- `KnowledgeBaseRecord` as the primary corpus abstraction;
- manually pasted plain-text-only Knowledge Documents as the primary ingestion experience;
- fixed 900-character chunk identity as durable knowledge;
- bounded SQL scan then in-process dense scoring as large-corpus retrieval;
- `WikiAwareKnowledgeRepository` as a separate retrieval universe;
- `ServerWikiV3Repository` as a Character-facing knowledge subsystem;
- separate `knowledge_hits` and `wiki_hits` in final Context Resolver semantics;
- `wiki.lookup` as a permanent Character tool name;
- SQLite as the intended production database for the new large-corpus system.

Do not add new functionality to these concepts solely to make the transition easier. Either adapt them temporarily behind the new boundary or remove them when the consuming phase cuts over.

## Explicit non-goals

This architecture does not require:

- a dedicated graph database in the first implementation;
- Qdrant/Milvus/Pinecone in the first implementation;
- LLM summarization of every chunk;
- automatic ingestion of every Web search result;
- merging Social Relationship with world/canon relationship claims;
- merging Conversation Episodes with corpus/world Events;
- making every imported source globally visible;
- giving every Character all server-accessible knowledge;
- preserving RAG V1 APIs/UI forever.

## Implementation sequencing contract

The active development plan owns phase execution. The intended dependency order is:

1. PostgreSQL production foundation and migration proof;
2. Knowledge Corpus/Source/Access/Policy schema;
3. canonical content, source versioning, Evidence Units, object-storage contract;
4. PostgreSQL FTS + pgvector index layer;
5. Knowledge Query Engine, accessible-space resolution, fusion/rerank/freshness;
6. Character/Context integration and old RAG/Wiki consumer cutover;
7. unified Projection Layer;
8. ingestion adapters, beginning with Git and structured document import before broad generic Web crawling;
9. Character epistemic timeline/spoiler/perspective controls;
10. Portal/Admin operational UX, lifecycle hardening, observability and scale validation.

A phase may refine field names or split repositories, but it must not violate the authority, access, epistemic, provenance, and derived-projection rules in this contract without first updating this contract and the active plan.
