# Knowledge Fabric implementation impact map

Status: **historical execution map for `codex/knowledge-fabric-foundation`; Phase 11c directly retired the pre-Fabric Knowledge Base/RAG/KB Wiki/Server Wiki v3 surfaces**

Use this file with `docs/knowledge-fabric-architecture.md`, `docs/active-development-plan.md`, `docs/intelligence-core-v3-architecture.md`, `AGENTS.md`, and the source/tests named below.

This map preserves the pre-cutover blast-radius analysis. Source/tests and
`docs/agent-map.md` are the current navigation authority. References below to old routes,
repositories, tables, imports, migration, reuse, or archive are historical only and must not be
implemented or restored: the product owner selected a direct empty-Fabric cutover.

## Historical baseline examined before the cutover

Before Phase 11c, Knowledge was split across several paths:

```text
Manual Knowledge Base / RAG
    ├ KnowledgeBaseRecord
    ├ KnowledgeDocumentRecord
    ├ KnowledgeChunkRecord
    ├ sparse+dense in-process retrieval
    └ optional KB-derived Wiki overview

Intelligence v3 runtime knowledge
    ├ EntityV3 / EvidenceEdgeV3 / KnowledgeGap
    ├ BeliefV3
    ├ Episode
    └ Server Wiki projection

Character turn
    ├ KnowledgeRepository
    ├ ServerWikiV3Repository
    └ ContextResolverV3 merges both into KNOWLEDGE EVIDENCE
```

The implemented Fabric removes that conceptual duplication without collapsing authority domains
that v3 deliberately separated. `knowledge_fabric_hard_cutover.py` and its tests record the
one-way deletion of the former tables and `knowledge-chunk` vectors.

## Impact summary

| Area | Impact | Target action |
| --- | --- | --- |
| Database/runtime storage | very high | PostgreSQL + pgvector is required in production; SQLite is development/test or an offline migration source only |
| Knowledge Base/RAG V1 | retired | directly removed in Phase 11c; no migration/archive/import path |
| KB-derived Knowledge Wiki | retired | directly removed in Phase 11c; Fabric Projections replace derived views |
| Server Wiki v3 | retired | directly removed in Phase 11c; no Character-facing Wiki boundary |
| Context Resolver | high | consume one bounded KnowledgeContext instead of separate knowledge/wiki universes |
| CharacterTurnContextV3 | high | depend on KnowledgeQueryEngine rather than raw Knowledge + Wiki repositories |
| Entity/Evidence Graph | high | add corpus canonical identity and cross-scope evidence semantics while preserving runtime provisional entities |
| Belief/Memory | medium | preserve; add explicit world/corpus knowledge -> Character epistemic boundary |
| Knowledge Gap / Discovery / Web lookup | medium-high | local-first/freshness routing; preserve candidate-is-not-authority rule |
| Internal context tools | medium | replace conceptual `wiki.lookup` with `knowledge.search`; keep memory/conversation separate |
| Smart Participation | low | preserve authority/performance; do not run full retrieval for every candidate |
| Conversation Thread/Episode | low | preserve; Episode may be projection evidence but not corpus world-event replacement |
| Social Intelligence | low | preserve; canon relationship knowledge must not overwrite lived relationship state |
| Media/Shared Content | medium-low | share provenance/evidence plumbing only; preserve media epistemic contract |
| Portal/API | very high | redesign around Corpus/Source/Sync/Access/Query/Evidence instead of pasted Document CRUD |
| Admin/security | high | Super Admin global library + source credentials + access grants + private artifact policy |
| Account lifecycle | high | new ownership/grants/artifacts/indexes must delete/claim safely |
| Observability/background work | high | ingestion/job/query/index health without leaking private content |
| Test/deployment/CI | very high | add PostgreSQL/pgvector integration and migration gates before large ingestion |

## 1. PostgreSQL, migrations, and deployment foundation

### Current sources to inspect

- `src/echo_masque/config.py`
  - default `database_url` is SQLite;
  - semantic model settings are process-level;
  - production currently lazily enables semantic embeddings.
- `src/echo_masque/persistence/database.py`
  - SQLite PRAGMA foreign keys;
  - SQLite deployment uniqueness/delete triggers;
  - SQLite-specific additive column repair;
  - `Base.metadata.create_all()` plus application-managed hard-cutover migrations.
- all modules under `src/echo_masque/persistence/*migration*`;
- `src/echo_masque/persistence/models.py` and every registered ORM model imported by `database.py`;
- `pyproject.toml`;
- Railway/Docker/deployment documentation and environment templates;
- storage inspection/health code used by `src/echo_masque/api/app.py`.

### Required target work

- make PostgreSQL a first-class production/test backend before adding large-corpus tables;
- introduce the PostgreSQL driver and `pgvector` extension/dependency through reviewed migrations/startup checks;
- port SQLite-only invariants into portable constraints/foreign keys/triggers or PostgreSQL-safe equivalents;
- define one supported migration path from existing SQLite production data rather than silent dual authority;
- update deployment/storage health to describe PostgreSQL truth correctly;
- keep fast isolated unit tests possible without accidentally making SQLite behavior the production contract.

### Must not do

- do not introduce Knowledge Fabric tables on SQLite first and migrate them again later;
- do not assume `Base.metadata.create_all()` alone is sufficient for production schema evolution once pgvector/index DDL is involved;
- do not drop existing runtime data during database cutover;
- do not leave SQLite as an untested implicit production fallback after the production cutover is declared complete.

### Proof required

- fresh PostgreSQL bootstrap;
- existing-data migration rehearsal;
- restart/idempotency proof;
- deployment/Character/relationship/Intelligence v3 regression tests on PostgreSQL;
- pgvector extension/index health test;
- failure behavior when PostgreSQL/extension is unavailable.

## 2. Legacy Knowledge Base persistence and retrieval

### Current sources

- `src/echo_masque/persistence/knowledge_models.py`;
- `src/echo_masque/persistence/knowledge_repository.py`;
- `src/echo_masque/persistence/semantic_vector_repository.py`;
- `src/echo_masque/knowledge_retrieval.py`;
- `src/echo_masque/persistence/wiki_aware_knowledge_repository.py`;
- `src/echo_masque/knowledge_wiki.py`;
- `src/echo_masque/persistence/wiki_page_models.py`;
- `src/echo_masque/persistence/wiki_page_repository.py`;
- persistence exports in `src/echo_masque/persistence/__init__.py`;
- knowledge tests including `tests/test_knowledge_*` and current context tests.

### Current constraints/behavior to remember

- manually authored plain text is normalized then deterministically chunked;
- document limit is 200,000 characters;
- default chunks are 900 characters with overlap;
- hybrid retrieval currently mixes sparse score with E5 dense similarity;
- vectors are lazily stored in a shared semantic vector repository;
- large-corpus retrieval is still constrained by current SQL candidate scanning and in-process scoring;
- `WikiAwareKnowledgeRepository` may substitute one derived overview for broad-summary intent.

### Target work

- introduce Corpus/Source/SourceVersion/CanonicalDocument/Section/Block/Asset/Evidence records independently of fixed chunk identity;
- preserve current owner-authored text through a `manual_text`/legacy import adapter rather than treating old tables as permanent architecture;
- move dense/sparse retrieval behind a new index/query interface;
- eventually delete or archive old Knowledge Base/Wiki persistence after all consumers and useful data are migrated;
- keep provenance from imported legacy documents so migration is auditable.

### Documentation warning

`docs/context-rag-v1.md` is a current/baseline RAG document, but parts of its sparse-only description lag current source because production source already supports semantic retrieval. Treat source/tests as authority. The file must be retired or rewritten at the phase that removes RAG V1 from runtime authority.

## 3. New Corpus, Source, Version, Evidence, Access, and Policy persistence

### Expected new persistence boundaries

Names are provisional; preserve semantics if implementation chooses different class names.

```text
KnowledgeCorpus
KnowledgeSource
KnowledgeSourceVersion
CanonicalDocument
CanonicalSection / CanonicalBlock
KnowledgeAssetReference
KnowledgeEvidenceUnit
CanonicalKnowledgeEntity
ExtractedAssertion
KnowledgeWorldEvent
KnowledgeAccessGrant
KnowledgeOverlayPolicy
KnowledgeIngestionJob / Checkpoint
KnowledgeProjection / Dependency
```

### Rules

- `system/user/organization/server` owner types are schema concepts; v1 UI may expose fewer;
- system-global corpus is managed by Super Admin in v1;
- server-local Knowledge is represented as a server-owned/private corpus, not a second physical schema;
- global/shared corpus data is stored once and granted to servers, never copied per server;
- server `inherit/augment/override/deny` behavior is represented as policy/precedence, never destructive mutation of global evidence;
- permission predicates must be efficient enough to apply before vector/sparse ranking.

### Likely files

- new model/repository modules under `src/echo_masque/persistence/`;
- `src/echo_masque/persistence/database.py` registration/migrations;
- lifecycle repository/service files;
- new API schemas/routes;
- `src/echo_masque/api/app.py` composition;
- Portal API/types/panels.

## 4. Canonical entity and Evidence Graph integration

### Current sources

- `src/echo_masque/persistence/entity_evidence_models.py`;
- `src/echo_masque/persistence/entity_evidence_repository.py`;
- `src/echo_masque/entity_grounding_v3.py`;
- `src/echo_masque/evidence_graph_v3.py`;
- any tests for Entity Grounding, Evidence Graph, Knowledge Gap and belief dependencies.

### Current conflict with target

`EntityV3Record` is intentionally server-scoped by owner + connection + guild + type + normalized name. That is correct for provisional runtime identity but wrong as the only identity for a shared global corpus. A canonical imported entity such as a game character/project/package must not be duplicated once for every server that talks about it.

### Target work

- preserve server-scoped provisional/runtime entities;
- add corpus/domain canonical entities;
- add a revisable `runtime_entity/mention -> canonical_entity` relation with provenance/confidence/status;
- generalize Evidence Graph references so imported Evidence Units/Source Versions/Canonical Entities can participate without turning Evidence Graph into a duplicate truth store;
- define merge/split/supersede behavior for canonical identity separately from server mention interpretation.

## 5. Belief/Memory and epistemic access

### Current sources

- `src/echo_masque/persistence/belief_models.py`;
- `src/echo_masque/persistence/belief_repository.py`;
- `src/echo_masque/belief_revision_v3.py`;
- `src/echo_masque/current_turn_belief_v3.py`;
- Character memory/internal context tests.

### Preserve

Belief remains the Character/server-scoped answer to “what is currently believed/known,” with confidence, authority, status, revisions, temporal validity and evidence dependencies.

### Do not do

Do not load every imported world/corpus assertion into `BeliefV3`. That would make imported public knowledge indistinguishable from Character epistemic state and would create duplicate truth.

### New target boundary

```text
Authorized Corpus/Server World Knowledge
    ↓
Knowledge Query Engine
    ↓
Character Epistemic Policy
    ↓
KnowledgeContext available this turn

Character Belief
    remains separately recalled/revised by Intelligence v3
```

Later epistemic-policy work must support at least corpus/domain allow/deny and leave clean extension points for timeline/story position, spoiler level, perspective and authored overrides.

## 6. CharacterTurnContextV3 and ContextResolverV3

### Current sources

- `src/echo_masque/character_turn_context_v3.py`;
- `src/echo_masque/character_turn_context_types.py`;
- `src/echo_masque/context_resolver_v3.py`;
- `src/echo_masque/connector_runtime.py`;
- `src/echo_masque/api/app.py`;
- related Character-turn/context/prompt tests.

### Current coupling

`CharacterTurnContextV3Service` currently receives both `KnowledgeRepository` and `ServerWikiV3Repository`. `ContextBundleV3` carries separate `knowledge_hits` and `wiki_hits`, then `prompt_sections()` combines them into `KNOWLEDGE EVIDENCE` anyway.

### Target work

- compose one `KnowledgeQueryEngine` at app level;
- let the engine resolve authorized corpora/server overlays, query modes, freshness, retrieval channels and epistemic filtering;
- return one typed/bounded `KnowledgeContext` or normalized Knowledge Evidence contract;
- Context Resolver budgets/packs that contract alongside Beliefs/Episodes/Entities/Social/Pending Actions;
- remove direct KnowledgeRepository/ServerWiki repository knowledge from Character-turn composition after cutover proof;
- keep RAG/query failure non-fatal to Character availability unless the requested behavior explicitly requires grounded evidence.

### Must preserve

- current-turn correction shields happen before Character generation;
- scoped Belief/Episode/Social behavior;
- `unresolved`/insufficient states;
- prompt-injection boundary: imported content is data, not Runtime instruction;
- no Topic fallback.

## 7. Wiki/consolidation -> Projection Layer

### Current sources

- `src/echo_masque/knowledge_wiki.py`;
- `src/echo_masque/persistence/wiki_aware_knowledge_repository.py`;
- `src/echo_masque/persistence/wiki_page_models.py`;
- `src/echo_masque/persistence/wiki_page_repository.py`;
- `src/echo_masque/knowledge_consolidation_v3.py`;
- `src/echo_masque/persistence/server_knowledge_v3_models.py`;
- `src/echo_masque/persistence/server_knowledge_v3_repository.py`;
- Wiki/Knowledge consolidation tests.

### Target work

- replace two Wiki-shaped concepts with one projection abstraction;
- support entity/corpus/project/concept/event/timeline/relationship/source views as derived caches;
- attach source dependency/version hash/provenance to every projection;
- invalidate affected projections on source/evidence changes;
- build lazily where useful;
- exact/evidence queries bypass projection-only answers;
- remove `Wiki` from Character-facing authority/API naming once consumers move.

### Migration note

Existing Wiki tables/code may be reused as an implementation shortcut only if the resulting public/runtime contract is Projection-based and derived-only. Do not preserve separate KB Wiki and Server Wiki universes for compatibility.

## 8. Knowledge Gap, Discovery, Web/API freshness

### Current sources

- `src/echo_masque/knowledge_gap_discovery_v3.py`;
- `src/echo_masque/deployment_discovery_service.py` and Discovery persistence;
- external Web/Image/browser Tool routing and schemas;
- `src/echo_masque/browser_runtime.py`;
- tool execution/runtime files;
- Knowledge Gap tests.

### Preserve

Discovery candidates do not resolve Knowledge. `accept_evidence()`/Content Understanding-style acceptance remains required for durable evidence.

### Target work

- Query Engine first searches authorized local/global/server corpora;
- compare evidence freshness with query freshness requirement;
- use current-turn Web/API Tool only when authorized and needed;
- return external results as turn-local evidence;
- when result belongs to a registered Source, optionally enqueue normal ingestion/update rather than directly promoting search prose to fact;
- adaptive source sync should use source-native revision/hash/ETag/etc. before repeated expensive retrieval.

### Do not merge

Deployment Discovery remains autonomous curiosity/content discovery. It must not become the generic synchronous factual lookup engine for Character turns.

## 9. Internal Context Tools

### Current source

- `src/echo_masque/internal_context.py`;
- tool registry/schemas that expose internal tools;
- `src/echo_masque/api/app.py` where Server Wiki lookup is injected.

### Current tools

```text
memory.search
conversation.search
wiki.lookup
```

### Target

```text
memory.search
conversation.search
knowledge.search
```

`knowledge.search` talks to the Knowledge Query Engine and may expose bounded semantic modes. It must not expose storage implementation (pgvector/Wiki/PDF/etc.) as the Character contract.

Keep memory and conversation tools distinct from knowledge because they represent different authorities.

## 10. Smart Participation / Participation Planner

### Current sources

- current Smart Participation resolver/planner modules;
- `src/echo_masque/character_turn_context_v3.py`;
- Connector participation path/tests.

### Performance invariant

Do not run full multi-index Knowledge retrieval + reranking + freshness checks for every eligible Character during admission. Cheap entity/relevance hints may participate in routing, but expensive corpus retrieval belongs after selection unless an explicitly bounded design proves otherwise.

No Knowledge Fabric phase may restore Connector-local semantic authority or Topic fallback.

## 11. Conversation Thread, Episode, and working state

### Current sources

- `src/echo_masque/persistence/conversation_structure_*`;
- `src/echo_masque/persistence/conversation_runtime_*`;
- Conversation Structure/Runtime coordinators and tests.

### Expected impact

Low. Preserve v3 meanings:

- Thread = short/medium-lived conversation line;
- Episode = durable projection of what happened in a Character Relay conversation;
- Thread Working State = transient conversational state.

Episodes may be evidence for server-local projections or Character Belief, but imported world Events must not be forced into ConversationEpisode rows.

## 12. Social Intelligence and relationships

### Current sources

- `src/echo_masque/social_intelligence_v3.py`;
- relationship/impression/event persistence and tests.

### Expected impact

Low. Keep factual/canon relationship knowledge separate from lived directional Character Relationship and Impression.

Example: an imported corpus assertion that two fictional characters are related is world knowledge. It is not evidence that a deployed Character's lived trust/affinity toward another deployment changed.

## 13. Media, Shared Content and multimodal evidence

### Current sources

- media understanding/analysis repositories;
- conversation media references;
- planner media and live media services;
- shared-content resolution/enrichment introduced on current `main`;
- Evidence Graph association code.

### Target work

- allow imported PDF images/diagrams, website media, transcripts and similar content to produce source-addressable Evidence Units/observations;
- reuse provenance/content-understanding boundaries where sensible;
- keep original artifact refs/object storage ownership explicit.

### Preserve strictly

- objective media perception is distinct from semantic identity association;
- planner-only hidden media information does not silently become Character perception;
- Shared Content required-media semantics remain about the current turn and do not automatically imply durable Knowledge ingestion.

## 14. API redesign

### Current sources

- `src/echo_masque/api/routes/knowledge.py`;
- `src/echo_masque/api/knowledge_schemas.py`;
- route exports/app wiring;
- API tests.

### Current API shape

- CRUD Knowledge Bases;
- CRUD plain-text documents;
- direct `/retrieve` playground endpoint.

### Target API families

Exact routes may vary, but the semantic surface should cover:

```text
corpora
sources
source versions / sync state
ingestion jobs
server access grants
server overlay policies
query inspector/evidence inspector
projection status/rebuild
admin global library
```

File/source import APIs must support job-based asynchronous processing rather than blocking an HTTP request until large documents are parsed/embedded.

Do not expose raw private object-storage artifacts through unauthenticated URLs.

## 15. Portal and Admin UI

### Current sources

- `web/src/KnowledgeBasePanel.tsx`;
- `web/src/knowledgeApi.ts`;
- `web/src/DeploymentCenter.tsx`;
- `web/src/ServerAccessSettingsPanel.tsx` and `web/src/serverAccessApi.ts` where server access concepts can inform design;
- `web/src/AdministrationSettingsPanel.tsx`;
- `web/src/AdminSettings.tsx`;
- shared UI/routing/tests.

### Current UX to replace

The panel is centered on a selected Discord Server, lists `KnowledgeBase`, exposes account-global/server/channel scope, lets the owner paste up to 200k plain-text content, and provides a raw retrieval playground.

### Target UX

Super Admin:

- Global Knowledge Library;
- create/disable corpora;
- add/configure Sources;
- source credentials/access profiles;
- sync/index/job status;
- retry/rebuild;
- evidence/query inspection;
- publish/availability controls.

Server owner/admin:

- available global/shared corpora with enable/disable grants;
- server-local corpora/sources;
- inherit/augment/override/deny policy;
- scoped query inspector;
- later Character epistemic policy.

### Public Demo

UI hiding is not enough. API writes and private/global inspection remain server-enforced read-only/inaccessible in Public Demo.

## 16. Super Admin, auth, source credentials and audit

### Current sources

- `src/echo_masque/api/routes/admin.py`;
- `src/echo_masque/api/dependencies.py`;
- auth/admin repositories and audit service;
- Credential Vault/provider credential code;
- admin Portal surfaces/tests.

### Target work

- Global system corpus create/update/delete/sync/publish operations require authenticated Super Admin policy in v1;
- audit administrative changes without dumping source content or credentials;
- secrets for private Git/API/Web sources use scoped credential storage and are referenced by ID/profile, never embedded in `locator` or Knowledge evidence;
- ordinary Server Admin cannot inspect inaccessible global/private source internals.

## 17. Account deletion, ownership claim and cleanup

### Current source

- `src/echo_masque/evaluation_lifecycle.py` currently calls current Knowledge/Wiki/Intelligence cleanup/claim operations;
- underlying lifecycle repositories/tests.

### Target work

Lifecycle must explicitly handle:

- user/workspace-owned corpora/sources/versions;
- server-owned local corpora;
- access grants/policies;
- object-storage artifacts;
- vectors/sparse-index rows;
- ingestion jobs/checkpoints;
- projections/dependencies;
- canonical entities/assertions/events owned by deleted corpora.

System-global corpora must not be deleted because one ordinary user/account is deleted. Deletion order/foreign keys must prevent orphaned derived indexes or cross-owner leaks.

## 18. Background jobs and operational scheduling

### New requirement

Large ingestion cannot execute inside Character turn handling or one long synchronous API request.

Introduce a bounded worker/job abstraction for:

- source discovery/fetch;
- parse/extract;
- object artifact persistence;
- embedding/index;
- LLM enrichment;
- source sync;
- projection invalidation/rebuild;
- retry/dead-letter/error status.

The first implementation may use the same deployable codebase/process topology if necessary, but job ownership/idempotency/checkpoint contracts must permit later separation into worker processes without changing data authority.

Tests must cover restart/idempotency and duplicate job delivery.

## 19. Object storage

### New requirement

Original PDF/DOCX/images/source snapshots should not become large opaque PostgreSQL blobs.

Add an S3/R2-compatible object-storage abstraction with:

- private-by-default objects;
- content hash and metadata in PostgreSQL;
- owner/corpus linkage;
- deletion/lifecycle integration;
- retry-safe upload semantics;
- no credentials/public bucket details in logs.

If object storage is unavailable, ingestion should fail or pause cleanly without partially publishing an invalid source version.

## 20. Ingestion adapters

### First adapters recommended

1. Git/GitHub repository import, because commit/tree/diff metadata makes versioning and incremental sync deterministic.
2. Uploaded structured documents: DOCX and text/Markdown first; PDF layout-aware parsing next; other Office/table formats after the canonical document contract is stable.
3. Specialized Wiki/docs adapters plus generic website fallback.
4. API/dataset/RSS/forum adapters as demand proves them.
5. Local Sync Agent only after the remote Source API/security/allow-deny contract is stable.

### Source-specific requirements

Git/code:
- honor ignore rules;
- do not ingest `.env`, keys, dependencies/build outputs by default;
- parse symbols/AST/dependencies where practical;
- commit/diff-driven incremental update.

PDF:
- text/layout parser first;
- OCR/document vision only for scanned/unreadable regions;
- preserve page/table/image coordinates.

DOCX:
- preserve heading/paragraph/list/table/link/image structure from OOXML.

Website:
- generic main-content/canonical URL/sitemap/change signals;
- specialized adapters preserve revision/category/navigation/thread metadata;
- respect network/safety policy and explicit source authorization.

## 21. Retrieval/index implementation

### New components expected

- FTS/sparse search over authorized evidence/document representations;
- pgvector ANN dense index;
- entity lookup/resolution index;
- graph/relation expansion path;
- temporal/freshness filters;
- fusion/RRF-style merge;
- reranker/diversifier;
- evidence packer;
- query plan/result observability.

### Important order

Apply owner/grant/server/policy constraints before returning/ranking inaccessible data. A post-hoc permission filter over a global top-K vector result is both a security risk and a retrieval-quality bug.

## 22. Observability and tracing

### Target telemetry

Safe metadata may include:

- ingestion job/source/corpus IDs;
- parser/index stage;
- item counts/bytes/durations;
- change counts;
- vector/FTS index health;
- query plan channels;
- authorized corpus count;
- candidate/selected counts;
- freshness decisions;
- projection hit/stale/rebuild state;
- failure reason codes.

Do not put private raw documents, prompts containing imported full text, source credentials, authorization headers, or object-storage secrets into ordinary Provider Trace/Discord Event Logs.

The existing Retrieval Playground evolves into a scoped Query/Evidence Inspector for authorized administrators.

## 23. Tests that become mandatory

Add or extend proof for:

- PostgreSQL bootstrap/migration/restart;
- pgvector extension and ANN path;
- FTS/dense hybrid ranking;
- access isolation across users/servers/corpora;
- global grant enable/disable;
- server overlay inherit/augment/override/deny precedence;
- Character epistemic deny/timeline/spoiler behavior when implemented;
- canonical entity reuse across multiple servers;
- runtime provisional entity -> canonical entity resolution/revision;
- source versioning and incremental diff;
- object-storage owner cleanup;
- ingestion job idempotency/retry;
- PDF/DOCX/Git parsing fixtures;
- exact quote/raw evidence behavior;
- projection staleness/rebuild/provenance;
- local stale -> external lookup -> turn-local evidence behavior;
- Discovery candidate remains non-authoritative;
- account deletion/claim;
- Public Demo read-only/access isolation;
- Context Resolver/Character prompt integration;
- Smart Participation does not fan out expensive Knowledge queries per candidate;
- targeted mutation testing for changed authorization, overlay, ownership, lifecycle, query-filter,
  and deterministic decision code, with reviewed survivor classifications;
- Python lint/mypy/full relevant test suite, Portal tests/build, Connector tests/build when touched.

## 24. Documentation/contracts to update during implementation

- `docs/knowledge-fabric-architecture.md` — target contract; update when authority changes;
- `docs/active-development-plan.md` — phase ledger/status/validation/commit;
- `docs/intelligence-core-v3-architecture.md` — update when the implemented Context/Entity/Belief/Projection integration changes the canonical v3 contract;
- `docs/context-rag-v1.md` — keep as current baseline only until its runtime is cut over, then archive/rewrite clearly;
- `docs/agent-map.md` and `docs/agent-handoff.md` — update only as implementation ownership/baseline actually changes;
- `docs/README.md` and operator/deployment/security docs after PostgreSQL/source/admin behavior is implemented;
- OpenWiki only after accepted source/manual docs change; it remains generated orientation, not authority.

## 25. Cutover/deletion checklist

An agent must not delete an old subsystem merely because the new class exists. Before deletion, prove:

- all production callers moved;
- migration/ownership behavior exists;
- data needed by users is migrated or explicitly deprecated;
- tests no longer rely on old authority;
- Portal/API callers moved;
- Public Demo behavior remains safe;
- account deletion/claim includes the new model;
- observability is available;
- no old fallback silently restores RAG/Wiki/SQLite authority.

Likewise, do not keep a dead compatibility universe after cutover. Intelligence Core v3 deliberately prefers hard authority cutovers over long-lived shadow/fallback systems.

## First takeover instruction

A new AI Coding Agent on this branch should **not start by implementing a Wiki/PDF crawler**. Read the active plan and begin with the PostgreSQL foundation phase. The large-corpus/source model depends on PostgreSQL/pgvector, access filtering, lifecycle, and migration behavior being sound first.
