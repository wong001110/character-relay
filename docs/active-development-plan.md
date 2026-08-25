# Active development plan — Knowledge Fabric foundation

Status: **branch-local execution record — Phase 0 complete when this planning commit is at HEAD; next phase is PostgreSQL foundation**

| Field | Value |
| --- | --- |
| Active branch | `codex/knowledge-fabric-foundation` |
| Starting baseline | `main` at `68169b8d878ef4d8475e1e52c812fffcb19249a4` |
| Delivery mode | coherent phase batches; at most one implementation commit per phase |
| Current phase | Phase 1 — PostgreSQL production foundation |
| Integration owner | main/root coding agent for the active session |
| Target architecture | `docs/knowledge-fabric-architecture.md` |
| Blast-radius map | `docs/knowledge-fabric-impact-map.md` |

This file is the takeover ledger for the branch. It records approved target direction and execution order so a coding agent does not need chat history. Current source/tests remain authority for behavior that has not yet been cut over. The target contract becomes runtime truth only as each phase passes its gate.

## Approved outcome

The branch is approved to move Character Relay from the current manual/server-oriented RAG model toward a source-driven Knowledge Fabric with these properties:

1. PostgreSQL becomes the formal production relational database before large Knowledge Fabric ingestion is introduced; pgvector is the first dense index implementation.
2. Knowledge is organized as Corpus + Source + immutable Source Version + canonical structured content + Evidence, not as durable fixed-size chunks.
3. System-global/world corpora are stored once and can be granted to servers. V1 Global Library management is Super Admin-controlled.
4. Server-local knowledge remains available as a private server-owned corpus/overlay. Servers may inherit, augment, override, or deny inherited/global knowledge without mutating it.
5. Server authorization and Character epistemic access are separate. A server being allowed to use a corpus does not make every Character omniscient.
6. Canonical corpus entities are distinct from current server-scoped provisional/runtime Entities, with revisable resolution links between them.
7. Imported world/corpus knowledge does not get copied wholesale into `BeliefV3`; Character Belief remains a separate Intelligence v3 authority.
8. Retrieval becomes multi-index: PostgreSQL FTS/sparse + pgvector ANN + canonical entity/relation + temporal/freshness evidence, fused/reranked behind one Knowledge Query Engine.
9. Existing KB Wiki and Server Wiki concepts are reduced to one derived Projection Layer. Projection text never outranks raw evidence.
10. Ingestion is deterministic-first and LLM-last. LLM enrichment is selective/lazy and never becomes the only retained representation of a source.
11. Git/code, uploaded documents (PDF/DOCX/etc.), Wiki, ordinary websites, APIs/datasets, feeds/forums, and later local sync are Source Adapter families behind one canonical ingestion contract.
12. Stable knowledge is synchronized; volatile/current knowledge can escalate to live Web/API evidence when local evidence is stale or missing.
13. Bulk ingestion/index/sync/projection work runs as background jobs and never blocks the normal Character reply path.
14. Portal/Admin changes move from pasted Document CRUD toward Corpus/Source/Sync/Access/Policy/Evidence/Query operational surfaces.

## Explicitly out of scope for the foundation phases

- Keeping SQLite as a second long-term production authority merely for compatibility.
- Adding Qdrant/Milvus/Pinecone before pgvector scale limitations are measured.
- Introducing Neo4j or another graph database simply because the model has graph semantics.
- Sending every chunk/section through an LLM.
- Treating every Web search result as permanent Knowledge.
- Replacing Social Intelligence relationships with imported/canon relationship claims.
- Replacing Conversation Episodes with imported world Events.
- Letting Smart Participation execute full Knowledge retrieval for every candidate Character.
- Reintroducing Topic authority, Topic fallback, shadow authority, or deprecated compatibility UI.
- Making source credentials/object-storage artifacts public or exposing them through ordinary traces.
- Building the Local Sync Agent before the remote Source/import/permission security contract is stable.

## Required reading before edits

Read in this order:

1. `AGENTS.md`
2. `docs/ai-agent-development-workflow.md`
3. this file
4. `docs/knowledge-fabric-architecture.md`
5. `docs/knowledge-fabric-impact-map.md`
6. `docs/agent-map.md`
7. `docs/agent-handoff.md`
8. `docs/intelligence-core-v3-architecture.md`
9. source/tests for the active phase

`docs/context-rag-v1.md` is useful as a current/baseline product description but contains stale sparse-only statements relative to current hybrid source. Source/tests win.

## Current source evidence behind the plan

The branch plan was grounded against current `main`, including:

- `src/echo_masque/persistence/knowledge_repository.py`: plain-text document limit, deterministic chunking, current hybrid sparse+dense in-process retrieval and semantic vector persistence;
- `src/echo_masque/api/routes/knowledge.py`: current Knowledge Base/document CRUD and retrieval playground API;
- `web/src/KnowledgeBasePanel.tsx`: current Server/account-global/channel Knowledge Base UI and pasted plain-text document flow;
- `src/echo_masque/character_turn_context_v3.py`: Character turn currently receives `KnowledgeRepository` plus `ServerWikiV3Repository`;
- `src/echo_masque/context_resolver_v3.py`: separate `knowledge_hits`/`wiki_hits` are already merged into one `KNOWLEDGE EVIDENCE` prompt section;
- `src/echo_masque/internal_context.py`: current internal tools include `memory.search`, `conversation.search`, and `wiki.lookup`;
- `src/echo_masque/knowledge_consolidation_v3.py`: Entity/Belief/Episode/Evidence -> derived Server Wiki consolidation;
- `src/echo_masque/knowledge_gap_discovery_v3.py`: Discovery candidates remain non-authoritative until accepted as evidence;
- `src/echo_masque/persistence/entity_evidence_models.py`: current canonical/provisional runtime Entity storage is server-scoped;
- `src/echo_masque/persistence/belief_models.py`: current Belief is Character/server scoped with authority/revision/evidence/temporal semantics;
- `src/echo_masque/persistence/database.py`: SQLite-specific startup, triggers, PRAGMA and repair behavior;
- `src/echo_masque/config.py`: SQLite default database URL and current semantic model settings;
- `pyproject.toml`: no PostgreSQL driver/pgvector dependency yet;
- `src/echo_masque/evaluation_lifecycle.py`: account deletion/local claim explicitly owns current Knowledge/Wiki/Intelligence data;
- `src/echo_masque/api/routes/admin.py`: current authenticated Admin/runtime/credential boundaries to reuse rather than inventing a weaker global-corpus admin path.

## Cross-phase invariants

- Raw source artifacts, Evidence Units, raw messages, media refs, completed Tool results and external results remain provenance evidence; model prose is never silently promoted to source truth.
- `ExtractedAssertion` is not another Belief store. Corpus state and Character Belief remain different authority domains.
- Global/shared corpus records are never copied per Server simply to grant access.
- Corpus authorization is enforced before inaccessible candidates can affect ranking/results/metadata leakage.
- Server overlay precedence never destructively edits the inherited/global corpus.
- Character epistemic filtering is separate from Server access grants.
- Runtime provisional Entity and corpus Canonical Entity remain separate identities with evidence-backed resolution.
- Wiki/projection/summary material is derived, versioned/staleness-aware, and rebuildable.
- Exact quote/source/provenance queries route to raw/source-aligned evidence, not summary-only content.
- Imported content is untrusted data and cannot override Runtime/system/Character authority through prompt injection.
- Discovery candidate retrieval remains non-authoritative.
- Social Relationship/Impression remains in Social Intelligence.
- Conversation Thread/Episode meanings from Intelligence v3 remain unchanged.
- Media perception/identity epistemic boundaries remain unchanged.
- Smart Participation remains bounded and does not fan out expensive Knowledge Query Engine work per candidate.
- Bulk Knowledge work runs outside the synchronous Character reply critical path.
- Public Demo remains server-enforced read-only and isolated from private/global admin data.
- Credentials, private raw source content and object-store secrets do not enter ordinary logs/traces/docs/fixtures.
- No Topic fallback or dual old/new authority may be added to make a phase easier.

## Working and commit protocol

For every phase:

1. Re-open exact source/contracts/tests named for the phase and record any differences from this plan.
2. Map ownership and migration before changing shared persistence/contracts.
3. Let sub-agents research/test/edit non-overlapping scopes; the main agent owns cross-subsystem authority, combined diff and commit.
4. Integrate schema/source/tests/docs for one coherent phase before broad validation.
5. Run focused checks during development, then the complete phase gate once the batch is coherent.
6. Inspect combined diff for unrelated changes, secret/raw-content leakage, unsafe fallback and compatibility duplication.
7. Create at most one implementation commit for the phase after the gate passes.
8. Update this file with status, validation, deviations, commit/ref and the next concrete action.

Allowed phase states: `planned`, `in progress`, `blocked`, `complete`.

## Phase 0 — target architecture and blast-radius contract

Status: **complete when the branch HEAD contains this file plus the architecture/impact documents**

Scope:

- create `codex/knowledge-fabric-foundation` from current merged `main`;
- record the long-term architecture without optimizing around RAG V1 compatibility;
- identify every current subsystem that will be touched or must remain isolated;
- decide the high-level database/index/storage/access/epistemic direction before implementation starts.

Decisions locked by this phase:

- PostgreSQL before large-corpus schema;
- pgvector first dense index;
- object storage for large original artifacts;
- Corpus/Source/SourceVersion/Evidence as core imported-knowledge model;
- system-global corpus + grant, server-local corpus + overlay, Character epistemic policy;
- canonical corpus Entity separate from runtime/server Entity;
- corpus knowledge separate from Character Belief;
- Projection Layer replaces Wiki-shaped runtime concepts;
- KnowledgeQueryEngine becomes Character-turn integration boundary;
- deterministic-first/LLM-last ingestion;
- source-driven incremental sync and background jobs.

Validation gate:

- branch/base verification;
- manual read-through against current Intelligence v3 authority contract;
- current source evidence map review;
- no product tests required because this phase changes planning/docs only.

Phase 0 commit: **the branch HEAD containing this plan**.

Next action: Phase 1 PostgreSQL production foundation. Do not begin Source adapters first.

## Phase 1 — PostgreSQL production foundation

Status: **planned**

Goal: move the existing application runtime onto a sound PostgreSQL production foundation without yet changing Character Knowledge semantics.

Primary sources:

- `src/echo_masque/config.py`;
- `src/echo_masque/persistence/database.py`;
- persistence models and migration modules;
- `pyproject.toml`;
- deployment/storage health/config/docs;
- account/runtime/deployment tests that rely on SQLite-specific behavior.

Required work:

- add supported PostgreSQL driver/config;
- establish migration mechanism appropriate for PostgreSQL + future pgvector/index DDL;
- port current SQLite-only deployment invariants/foreign-key/cascade behavior;
- define/test migration of current SQLite production data to PostgreSQL;
- add `pgvector` extension availability/bootstrap without making Knowledge semantics depend on it yet;
- update production deployment/storage documentation/config;
- prove all current non-Knowledge Intelligence/Discord/Social/Media functionality still behaves correctly.

Hard questions to resolve before commit:

- exact migration tool/process for existing `create_all` + app-managed migration history;
- local developer/test database policy;
- how Railway production obtains PostgreSQL and runs migration safely;
- whether SQLite remains supported only for isolated tests/dev or is removed entirely after cutover.

Required gate:

- fresh PostgreSQL DB bootstrap;
- migration rehearsal from representative existing SQLite fixture/data;
- restart/idempotency checks;
- current full Python test suite or justified complete server/runtime gate on PostgreSQL;
- Ruff + strict mypy;
- deployment/storage health checks;
- no Knowledge behavior changes in this phase.

Commit gate: one database-foundation commit.

## Phase 2 — Corpus, Source, Access Grant and overlay policy schema

Status: **planned**

Goal: establish the scope/authorization model before importing large content.

Target contracts:

```text
KnowledgeCorpus
KnowledgeSource
KnowledgeAccessGrant
KnowledgeOverlayPolicy
```

Required behavior:

- owner types support future system/user/organization/server semantics;
- v1 system-global management is Super Admin-only;
- server-local corpus is server-owned/private;
- server grant enables/disables global/shared corpus without data copy;
- inherit/augment/override/deny policy is explicit and auditable;
- unauthorized server cannot infer corpus/source existence through query/admin APIs;
- lifecycle deletion/claim semantics are defined now, not postponed.

Likely sources:

- new persistence modules/migrations;
- `src/echo_masque/api/routes/admin.py` and admin dependencies;
- new Knowledge API schemas/routes;
- server access/ownership repositories;
- `src/echo_masque/evaluation_lifecycle.py`;
- Portal API/admin/server-access code.

Required gate:

- owner/server isolation tests;
- Super Admin authorization/audit tests;
- grant enable/disable tests;
- overlay precedence contract tests;
- account deletion/claim tests;
- Public Demo write/isolation tests;
- PostgreSQL migration/idempotency checks.

Commit gate: one scope/access schema commit.

## Phase 3 — canonical content, source versioning, Evidence Units and object storage

Status: **planned**

Goal: make source artifacts/versioned structure/evidence the durable imported-knowledge foundation.

Target contracts:

```text
KnowledgeSourceVersion
CanonicalDocument
Section / Block / Asset
KnowledgeEvidenceUnit
KnowledgeIngestionJob / Checkpoint
ObjectArtifactReference
```

Required behavior:

- immutable/source-versioned snapshots;
- canonical locator/hash/version metadata;
- structured document coordinates/provenance;
- large binary/original artifacts in private S3/R2-compatible object storage;
- restart-safe/idempotent background job state;
- dependency invalidation hooks for later indexes/projections;
- no mandatory LLM call to import a source.

Required gate:

- version/diff/idempotency tests;
- object storage failure/cleanup/access tests;
- duplicate job delivery/restart tests;
- secret/private locator redaction tests;
- lifecycle deletion tests.

Commit gate: one canonical-content/evidence foundation commit.

## Phase 4 — canonical corpus entities, assertions/events and Evidence Graph bridge

Status: **planned**

Goal: add world/corpus interpretation without abusing server-scoped Entity or Character Belief.

Primary current sources:

- `src/echo_masque/persistence/entity_evidence_models.py`;
- `src/echo_masque/persistence/entity_evidence_repository.py`;
- `src/echo_masque/entity_grounding_v3.py`;
- `src/echo_masque/evidence_graph_v3.py`;
- Belief models/repositories for authority-boundary tests.

Required behavior:

- Canonical Knowledge Entity is corpus/domain scoped;
- runtime/server Entity can resolve to canonical entity with revisable evidence;
- `ExtractedAssertion` and world Event reference Evidence Units and carry confidence/authority/temporal state;
- assertion/event interpretation does not become Character Belief automatically;
- imported evidence can participate in Evidence Graph relations without duplicating truth.

Required gate:

- same canonical entity reused across multiple server contexts;
- provisional runtime Entity can resolve/reject/reassign canonical relation;
- assertion conflicts remain representable without destructive overwrite;
- no automatic world assertion -> Belief promotion;
- evidence dependency/provenance tests.

Commit gate: one canonical-knowledge interpretation commit.

## Phase 5 — FTS + pgvector indexes and Knowledge Query Engine

Status: **planned**

Goal: replace current bounded SQL scan/in-process vector ranking for the new corpus path.

Target components:

```text
KnowledgeIndexProvider
Sparse/FTS retrieval
pgvector ANN retrieval
Entity/graph retrieval
Temporal/freshness filtering
QueryPlanner
Candidate fusion/RRF
Reranker/diversifier
EvidencePacker
KnowledgeQueryEngine
```

Required behavior:

- authorized corpus/server policy filtering is part of candidate retrieval;
- query modes support overview/exact/relational/current/code-like use cases without leaking backend details;
- exact quote/source query prefers raw/source-aligned evidence;
- current/fresh query can report stale/local insufficiency for later external lookup;
- current legacy RAG remains only for consumers not yet cut over, never mixed as a second authority inside the new engine.

Required gate:

- FTS/dense/entity/temporal channel tests;
- hybrid fusion/rerank quality fixtures;
- permission-filter-before-ranking tests;
- large-corpus synthetic performance/bounds test;
- pgvector index plan/health check;
- no cross-server/global metadata leakage.

Commit gate: one query/index engine commit.

## Phase 6 — Character Context cutover and freshness/external lookup integration

Status: **planned**

Goal: make the real Character turn consume the new KnowledgeQueryEngine/KnowledgeContext.

Primary current sources:

- `src/echo_masque/character_turn_context_v3.py`;
- `src/echo_masque/context_resolver_v3.py`;
- `src/echo_masque/connector_runtime.py`;
- `src/echo_masque/api/app.py`;
- `src/echo_masque/knowledge_gap_discovery_v3.py`;
- external Tool/browser/search routing;
- Character-turn/context tests.

Required behavior:

- app composes one KnowledgeQueryEngine;
- CharacterTurnContext no longer depends conceptually on separate RAG + Server Wiki stores;
- Context Resolver receives normalized KnowledgeContext/evidence and applies its budget;
- server access + overlay + Character epistemic policy gate happens before prompt injection;
- stale/missing high-importance current facts may escalate to authorized live Web/API evidence;
- Discovery candidate remains non-authoritative;
- query engine failure keeps normal Character availability where knowledge grounding is non-blocking.

Performance invariant:

- full KnowledgeQueryEngine retrieval runs after Character/turn selection, not for every Smart Participation candidate.

Required gate:

- mention/reply/Smart/Social Character-turn tests;
- KnowledgeContext reaches provider prompt with provenance/uncertainty safety;
- unauthorized/epistemically denied facts do not reach prompt;
- stale -> external current-turn evidence behavior;
- no duplicate old RAG/Wiki injection;
- no Topic/legacy fallback;
- latency/budget guard for Smart Participation and Character turn.

Commit gate: one real-runtime Knowledge cutover commit.

## Phase 7 — Projection Layer and internal tool cutover

Status: **planned**

Goal: retire Wiki as a separate runtime universe.

Primary current sources:

- `src/echo_masque/knowledge_wiki.py`;
- `src/echo_masque/persistence/wiki_aware_knowledge_repository.py`;
- current Wiki models/repositories;
- `src/echo_masque/knowledge_consolidation_v3.py`;
- Server Wiki models/repository;
- `src/echo_masque/internal_context.py`;
- Wiki/Knowledge tests.

Required behavior:

- one Projection abstraction with dependency/source hashes/staleness/provenance;
- entity/corpus/project/concept/event/timeline/relationship/source views as needed;
- lazy rebuild where useful;
- `wiki.lookup` becomes provider-neutral `knowledge.search`;
- `memory.search` and `conversation.search` remain separate;
- exact/evidence query cannot be satisfied solely by a projection.

Cutover/deletion requirement:

Only after every runtime/API/Portal consumer moves may KB Wiki/Server Wiki compatibility classes/tables be removed or migrated. Do not leave a shadow Wiki authority after the phase is complete.

Required gate:

- projection stale/invalidation/rebuild tests;
- source/provenance tests;
- internal `knowledge.search` contract tests;
- static/reference proof that Character runtime no longer depends on Wiki repository abstractions.

Commit gate: one projection/tool cutover commit.

## Phase 8 — first Source adapters: Git and uploaded documents

Status: **planned**

Goal: prove the generic ingestion contract with high-value private/project use cases before broad Web crawling.

Recommended order inside the phase:

- Git/GitHub repository Source adapter;
- manual text/legacy RAG import adapter;
- Markdown/text;
- DOCX structured parser;
- PDF layout parser with OCR/document-vision fallback only when needed;
- structured tables/images/assets where supported.

Git requirements:

- commit/tree/diff incremental sync;
- ignore/deny secret and build/dependency paths;
- source code AST/symbol/import/dependency extraction where practical;
- no requirement to LLM-summarize every code file.

Document requirements:

- preserve headings/paragraphs/lists/tables/links/images/page/section provenance;
- store structured table + retrieval representation;
- keep raw artifact in object storage;
- LLM enrichment selective/lazy only.

Required gate:

- fixture-based parsing tests;
- incremental Git change tests;
- secret-exclusion tests;
- scanned/digital PDF branch tests;
- source-version/evidence/provenance tests;
- ingestion job retry/idempotency tests.

Commit gate: one initial Source adapter commit. Split into two coherent phases only if Git and document parser dependencies become too large to validate together; update this plan first.

## Phase 9 — Website/Wiki/API/feed adapters and adaptive freshness

Status: **planned**

Goal: support external continuously maintained sources without making Wiki the architecture.

Required behavior:

- Generic Website Adapter: canonical URL, main content, sitemap/link discovery, dedup, hash/change signals;
- specialized adapters preserve source-native structure for MediaWiki/docs/feed/forum/API systems;
- adaptive sync uses Git revision/API revision/Wiki revision/ETag/Last-Modified/hash where available;
- source-specific authority/freshness profiles;
- normal network/safety/credentials restrictions;
- no broad crawl of arbitrary websites merely because a Character asked a question.

Required gate:

- generic + at least one specialized adapter fixture/integration test;
- conditional/no-change sync proof;
- changed-section-only invalidation proof;
- source authority/freshness routing tests;
- network/auth failure handling.

Commit gate: one external Source adapter/freshness commit or explicitly split coherent sub-phases after plan update.

## Phase 10 — Character epistemic policy

Status: **planned**

Goal: prevent “server can access corpus” from becoming “every Character knows the corpus.”

Minimum contract:

- corpus/domain allow/deny per Character/deployment policy;
- explicit authored overrides;
- clean extension for timeline/story position, spoiler level, perspective and known entities.

Recommended advanced behavior:

- timeline/story validity filtering;
- spoiler thresholds;
- role/perspective restrictions;
- explainable denial reason in safe trace metadata.

Required gate:

- same Server/corpus with two Characters receiving different knowledge access;
- spoiler/timeline regression fixtures when implemented;
- no denied content in prompt/trace/query inspector available to unauthorized Character context;
- explicit owner/admin policy update tests.

Commit gate: one epistemic-policy commit.

## Phase 11 — Portal/Admin operations, lifecycle hardening, scale and cleanup

Status: **planned**

Goal: expose the new architecture coherently and remove dead old product surfaces.

Primary current Portal sources:

- `web/src/KnowledgeBasePanel.tsx`;
- `web/src/knowledgeApi.ts`;
- `web/src/DeploymentCenter.tsx`;
- `web/src/ServerAccessSettingsPanel.tsx`;
- `web/src/serverAccessApi.ts`;
- `web/src/AdministrationSettingsPanel.tsx`;
- `web/src/AdminSettings.tsx`;
- relevant routing/styles/tests.

Target surfaces:

Super Admin:
- Global Knowledge Library;
- Corpus/Source management;
- sync/index/job health;
- authority/freshness/source credential linkage;
- retry/rebuild/publish/availability controls;
- evidence/query inspector.

Server:
- available global/shared corpus grants;
- server-local corpus/sources;
- overlay policy;
- Character epistemic settings;
- scoped Query/Evidence Inspector.

Operational work:

- account deletion/local claim/object artifact cleanup finalized;
- observability/job/index health finalized;
- current RAG V1 docs/API/UI removed or clearly archived after proven migration;
- Wiki compatibility removed after reference proof;
- deployment/security/operator docs updated;
- OpenWiki regenerated only after manual/source contracts are accepted.

Required gate:

- Portal typecheck/tests/build;
- API authorization/Public Demo tests;
- lifecycle tests;
- full Python relevant/full suite on PostgreSQL;
- Connector tests/build if runtime contract changed;
- static/reference scan for dead RAG/Wiki/SQLite production authority;
- synthetic large-corpus performance and isolation test;
- final docs/link/security review.

Commit gate: one final product/cutover cleanup commit, or split Portal and cleanup only after updating this plan with non-overlapping gates.

## Known implementation decisions that still require evidence in a phase

The architecture is approved, but these implementation details are intentionally not invented in Phase 0:

- exact PostgreSQL migration framework/tool;
- exact SQL schema/table/class names;
- exact pgvector index type and tuning parameters (HNSW/IVFFlat/etc. must be measured);
- exact sparse retrieval configuration/tokenization for multilingual corpora;
- exact background job framework/process topology;
- exact S3/R2 provider and deployment credentials contract;
- exact reranker model/algorithm and thresholds;
- exact LLM enrichment model/prompt/budget;
- exact Web crawler limits/robots/network policy additions;
- exact Local Sync Agent protocol;
- exact timeline/spoiler schema.

Resolve each in its owning phase from source constraints/tests/measurements. Do not ask for user input on routine implementation details unless the choice materially changes product/security/cost/authority.

## Handoff template for every completed phase

Record under the phase before handing off:

```text
Status: complete
Commit: <sha>
Changed authority/contracts: <short statement>
Key files: <paths>
Validation: <commands + results>
Migration/data action: <none or exact action>
Known deviations: <none or explicit>
Next action: <one concrete phase/action>
```

## Immediate takeover instruction

If you are an AI Coding Agent arriving on this branch now:

- do not implement a Furina/Genshin-specific schema;
- do not start with a Wiki scraper;
- do not add PDF upload directly to legacy Knowledge Base CRUD;
- do not bolt pgvector onto `KnowledgeChunkRecord` and call the architecture complete;
- do not merge imported world facts into `BeliefV3`;
- do not duplicate global corpus records per Server.

Start with **Phase 1 PostgreSQL production foundation**, preserve current runtime behavior, and only move to Corpus/Source schema after the database gate passes.