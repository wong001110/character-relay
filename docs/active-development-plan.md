# Active development plan — Knowledge Fabric foundation

Status: **branch-local execution record — Phases 1–10 are complete; Phase 11 remains**

| Field | Value |
| --- | --- |
| Active branch | `codex/knowledge-fabric-foundation` |
| Starting baseline | `main` at `68169b8d878ef4d8475e1e52c812fffcb19249a4` |
| Delivery mode | coherent phase batches; at most one implementation commit per phase |
| Current phase | Phase 11 — Portal/Admin operations and final cutover (planned) |
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
- Mutation reports are evidence about the configured code scope only; a surviving mutant is not
  silently ignored, and an equivalent/timeout/tooling classification is recorded with its phase.

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

Status: **complete — commit pending final diff review**

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
- establish the bounded Python/Portal/Connector mutation runners and scheduled/manual CI baseline
  without changing Knowledge behavior or adding a repository-wide score threshold.

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
- the configured Python/Portal/Connector mutation-runner smoke scopes on their supported
  platforms, with reports recorded as non-blocking Phase 1 baselines;
- no Knowledge behavior changes in this phase.

Commit gate: one database-foundation commit.

## Phase 2 — Corpus, Source, Access Grant and overlay policy schema

Status: **complete — implementation and Phase 2 gate passed; one phase commit pending final review**

Goal: establish the scope/authorization model before importing large content.

Approved Phase 2 authority decision (2026-08-25): canonical Server scope is the durable tuple
`(platform, connection_id, workspace_id)`. `KnowledgeServerAdministrator` is the sole
server-local administrator membership, and only an authenticated Super Admin may bootstrap a
scope or manage that membership. Do not infer Knowledge Fabric authorization from Discord roles,
Discord catalog/profile rows, join-code access, or owner-scoped Server Profiles. Scope or corpus
visibility must be non-enumerating for unauthorized accounts; Public Demo receives no Fabric read
or administration access.

Lifecycle decision: deleting or removing a Server Administrator revokes that membership only. It
does not delete the durable scope, server-local corpus, global grant, or another member. Connector
deprovision is a future explicit, audited operation; catalog synchronization must not silently
delete canonical Fabric scope data.

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
- targeted mutation scope for grants, overlay precedence, Super Admin, lifecycle, and Public Demo
  decisions; resolve or classify every survivor;
- PostgreSQL migration/idempotency checks.

Commit gate: one scope/access schema commit.

### Phase 2 completion record — 2026-08-25

Evidence: `src/echo_masque/persistence/knowledge_fabric_models.py`,
`knowledge_fabric_repository.py`, `knowledge_fabric_policy.py`,
`src/echo_masque/api/routes/knowledge_fabric.py`,
`src/echo_masque/evaluation_lifecycle.py`, `src/echo_masque/persistence/database.py`, and
`src/echo_masque/persistence/schema_migrations.py`; canonical authority contract in
`docs/knowledge-fabric-architecture.md`; proof in `tests/test_knowledge_fabric_policy.py`,
`tests/test_knowledge_fabric_phase2.py`, and `tests/test_database_foundation.py`.

Changed authority: `KnowledgeServerScope(platform, connection_id, workspace_id)` and explicit
`KnowledgeServerAdministrator` membership are independent of Discord catalog/profile/join-code
state. Only authenticated Super Admin manages membership and system-global corpus/source state.
Server-local corpora are private to the canonical scope. Global data is granted by reference, never
copied. Public Demo is denied/non-enumerating at the Fabric read boundary as well as by its write
middleware. Account delete/claim only affects explicit user-owned/grantee rows and preserves
system/server data.

Validation: focused Phase 2/security/lifecycle suite passed —
`python -m pytest tests/test_knowledge_fabric_policy.py tests/test_knowledge_fabric_phase2.py tests/test_database_foundation.py tests/test_phase15_account_lifecycle.py tests/test_account_admin_scoping.py tests/test_public_demo.py tests/test_server_access_repository.py tests/test_superadmin_server_claims.py tests/test_knowledge_api.py`
(53 passed, 2 explicit PostgreSQL tests skipped when no URL was configured); full Ruff and strict
Mypy passed. Disposable WSL/Docker pgvector PostgreSQL 16 passed both guarded foundation tests
(fresh schema/restart plus SQLite-to-PostgreSQL copy, idempotent rerun, and changed-source
protection). Windows mutmut was unsupported, so the configured scope ran in an isolated WSL copy;
`mutmut results` was empty after the run (no survivors, timeout, or unclassified result).

Deliberate omissions: this phase stores source registration metadata only; it does not import
content, versions, artifacts, credentials, indexes, query results, Character epistemic policy, or
Portal surfaces. User/organization/shared schema values are reserved but have no V1 grant path.
`augment`/`override` are explicit precedence modes; linking a local evidence corpus and resolving
conflicting evidence is Phase 3+ Query Engine work. Connector deprovision remains an explicit
future audited lifecycle operation, never a catalog-sync side effect.

Commit: pending the single Phase 2 final diff review. Next concrete action: Phase 3, choose and
document the object-storage provider/credential boundary before adding Source Version, canonical
content, Evidence Unit, artifact, or ingestion-job persistence.

## Phase 3 — canonical content, source versioning, Evidence Units and object storage

Status: **complete — current branch HEAD implementation commit**

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

Approved Phase 3 storage decision (2026-08-25): Cloudflare R2 is the production object store.
The persistence boundary uses the S3-compatible protocol so a future AWS S3 deployment can be
configured explicitly without changing Knowledge records or callers. The service-level R2 endpoint,
bucket, access-key ID, and secret access key are deployment-only configuration; secret values are
server-side `SecretStr` settings and never Source fields, API responses, audit metadata, logs, or
traces. Per-Source credentials (for private Git/API/Web adapters) remain an explicit later
Credential Vault concern rather than being reused as R2 infrastructure credentials. Objects are
private by default and database records store only provider/bucket/key/hash/size/content metadata.

Required gate:

- version/diff/idempotency tests;
- object storage failure/cleanup/access tests;
- duplicate job delivery/restart tests;
- secret/private locator redaction tests;
- lifecycle deletion tests.

Commit gate: one canonical-content/evidence foundation commit.

Sequencing findings to resolve in their owning phases: Phase 6 requires a Character epistemic gate
before prompt injection even though the detailed Character policy phase is currently Phase 10; do
not introduce a permissive interim fallback. Phase 7 may not delete Wiki compatibility until every
runtime, API, and Portal consumer has migrated, so its deletion boundary must be aligned with the
Phase 11 Portal cutover before either phase claims completion.

Phase 3 completion record:

```text
Status: complete — current branch HEAD implementation commit
Commit: `feat: add Knowledge Fabric ingestion foundation` (resolve final hash with `git log -1 --oneline`)
Changed authority/contracts: immutable Source Versions, canonical documents/sections/blocks/assets,
Evidence Units, source-version job/checkpoint/invalidation state, and private content-addressed
artifact records now exist. Cloudflare R2 is the production private object-storage provider through
an S3-compatible boundary; AWS S3 is an explicit deployment alternative. No Source credential,
public object URL/ACL, LLM dependency, Character Belief authority, or synchronous Character reply
path was added.
Key files: src/echo_masque/knowledge_fabric_ingestion.py;
src/echo_masque/knowledge_fabric_ingestion_policy.py;
src/echo_masque/knowledge_object_storage.py;
src/echo_masque/persistence/knowledge_fabric_content_repository.py;
src/echo_masque/persistence/knowledge_fabric_models.py;
src/echo_masque/persistence/schema_migrations.py;
tests/test_knowledge_fabric_phase3.py;
tests/test_knowledge_fabric_ingestion_policy.py
Validation: python -m ruff check . and python -m mypy passed (352 source files). Focused
Python regression batch passed: 69 passed, 2 expected PostgreSQL skips, 1 existing TestClient
deprecation warning. WSL-native mutmut scope ran 24 mutants: 20 killed, 0 timeout/tooling failures,
4 equivalent survivors. Real WSL Docker pgvector PostgreSQL 16 passed the guarded foundation and
SQLite-to-PostgreSQL migration tests: 2 passed, 7 deselected (6.31s); its named disposable
container was removed.
Mutation equivalence: deterministic_artifact_key mutants 11, 12, 17, and 19 alter only private
ValueError message capitalization/prefix text. Callers receive no message as a persisted/API
contract and behavior tests prove the exception class and safe error code boundary; they are
recorded equivalently rather than made brittle string contracts. Mutant 3 (incorrectly stripping
valid prefix content) was killed by a behavior-level prefix-preservation assertion.
Migration/data action: new idempotent knowledge-fabric-content-v1 revision creates the content/job
tables for SQLite/PostgreSQL. Existing source data is not imported or converted in this phase.
Known deviations: real Cloudflare credentials/bucket access is deliberately not exercised locally;
the S3-compatible client contract, private/no-ACL behavior, unavailable-storage failure, and
lifecycle cleanup are covered without deployment secrets. Source adapters and their Vault-backed
credentials remain later phases.
Next action: begin Phase 4 canonical corpus entities/assertions/events and the Evidence Graph bridge
without merging imported corpus facts into BeliefV3.
```

## Phase 4 — canonical corpus entities, assertions/events and Evidence Graph bridge

Status: **complete — current branch HEAD implementation commit**

Goal: add world/corpus interpretation without abusing server-scoped Entity or Character Belief.

Phase 4 identity decision: the first canonical identity boundary is one `KnowledgeCorpus`, not a
name-derived cross-corpus global namespace. `(corpus_id, entity_type, normalized_name)` may identify
one canonical entity and is reusable by many runtime/server entities that resolve into that corpus.
Cross-corpus/domain identity linking requires a future explicit domain model and evidence-backed
mapping; Phase 4 must not infer it from equal names.

Primary current sources:

- `src/echo_masque/persistence/entity_evidence_models.py`;
- `src/echo_masque/persistence/entity_evidence_repository.py`;
- `src/echo_masque/entity_grounding_v3.py`;
- `src/echo_masque/evidence_graph_v3.py`;
- `src/echo_masque/persistence/intelligence_v3_lifecycle_repository.py` for owner deletion/claim
  boundaries;
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

### Phase 4 completion record — 2026-08-25

Commit: `feat: add Knowledge Fabric corpus interpretations` (the current branch implementation
commit; resolve the final hash with `git log -1 --oneline`).

Evidence: `src/echo_masque/persistence/knowledge_fabric_models.py`,
`knowledge_fabric_interpretation_repository.py`,
`knowledge_fabric_interpretation_policy.py`, `knowledge_fabric_repository.py`,
`intelligence_v3_lifecycle_repository.py`, `database.py`, and `schema_migrations.py`; proof in
`tests/test_knowledge_fabric_entity_policy.py`, `tests/test_knowledge_fabric_phase4.py`, and
`tests/test_database_foundation.py`.

Authority and lifecycle: canonical identity is exactly `(corpus_id, entity_type, normalized_name)`.
Runtime `EntityV3` retains its owner/connection/guild authority and can only resolve through that
exact scope. Reassignment creates a successor record; rejected and superseded history remains.
Assertions may conflict, and events, assertions, runtime resolutions, and typed graph relations
retain Evidence Unit provenance. The Phase 4 repository never writes `BeliefV3` or
`ConversationEpisodeV3`. User-corpus deletion removes corpus interpretations before source content;
runtime-owner deletion removes only its resolution mappings before `EntityV3` deletion.

Validation: `python -m ruff check .` and `python -m mypy` passed (354 source files). The focused
Phase 2–4/Intelligence/lifecycle/database batch passed: 54 passed, 2 expected PostgreSQL skips,
and 1 existing TestClient deprecation warning. WSL-native `mutmut` ran 7 mutants against
`knowledge_fabric_interpretation_policy.py`: all 7 killed, with no survivor, equivalent, timeout,
or tooling classification. A disposable WSL/Docker pgvector PostgreSQL 16 container passed the
guarded foundation migration test (1 passed, 1 skipped, 7 deselected) and was removed.

Deliberate omissions: no name-derived cross-corpus/global identity, automatic Belief/Episode
promotion, graph-database dependency, query/index integration, API/Portal surface, or source
adapter was added. A future explicit domain model must own cross-corpus mappings.

Next action: Phase 5 should implement access-filtered FTS/pgvector/entity/temporal retrieval and
the single Knowledge Query Engine without changing the Phase 4 authority boundaries.

## Phase 5 — FTS + pgvector indexes and Knowledge Query Engine

Status: **completed — FTS/pgvector index layer and internal Query Engine committed**

Goal: replace current bounded SQL scan/in-process vector ranking for the new corpus path.

Phase 5 retrieval decisions:

- `KnowledgeFabricRepository.list_effective_corpora(server_scope_id)` is the sole current
  server/corpus authorization resolver. Its non-empty corpus-id result is an immutable input to
  every retrieval channel; an unknown scope returns no candidates and Phase 5 never calls the
  state-creating `ensure_server_scope()` path.
- Query modes are `overview`, `exact`, `relational`, `current`, and `code`. `exact` returns only
  source-aligned Evidence Unit provenance. `code` is sparse-only until a source adapter provides
  symbol/dependency structure.
- The first sparse baseline uses PostgreSQL's `simple` FTS configuration, with a deterministic
  portable sparse fallback for SQLite tests. The first ANN index is an HNSW cosine expression index
  for the existing E5-small/384 profile; a different configured embedding model/dimension remains
  queryable by exact vector distance but requires an explicit later index/rebuild decision.
- Temporal validity is half-open: an interpretation is available when `valid_from <= as_of` and
  `as_of < valid_to` when those endpoints exist. `current` returns local evidence together with
  `insufficient` freshness because `freshness_policy_json` has no approved schema yet; Phase 5
  does not invoke Web/API fallback.
- `deny` remains an authorization exclusion. `augment` and `override` remain provenance/precedence
  metadata only: no record-level shadowing key exists, so Phase 5 must not infer one from names,
  embeddings, or assertion prose.

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
- targeted mutation scope for authorization-before-ranking, freshness, and query-mode decisions;
- no cross-server/global metadata leakage.

Commit gate: one query/index engine commit.

### Phase 5 completion record — 2026-08-25

Commit: `feat: add Knowledge Fabric query indexes` (the current branch implementation commit;
resolve the final hash with `git log -1 --oneline`).

Evidence: `src/echo_masque/knowledge_fabric_query.py`,
`knowledge_fabric_query_policy.py`, `persistence/knowledge_fabric_index_repository.py`,
`knowledge_fabric_models.py`, `schema_migrations.py`, `database.py`, and lifecycle cleanup in
`knowledge_fabric_content_repository.py`; proof in
`tests/test_knowledge_fabric_phase5.py`, `tests/test_knowledge_fabric_query_policy.py`, and
`tests/test_database_foundation.py`.

Authority and lifecycle: the Query Engine resolves the effective corpus set before every channel
and rejects an empty/unknown scope without creating it. FTS, dense, entity/event/graph, and temporal
evidence all retain Evidence Unit/source-version provenance; RRF only fuses already-authorized
candidates. The derived retrieval and embedding rows are deleted before Evidence Unit deletion.
No Character epistemic policy, legacy-RAG fallback, record-level overlay conflict inference,
source adapter, or Character/context cutover is included.

Validation: `python -m ruff check .` and `python -m mypy` passed (357 source files). The focused
Phase 2–5/policy/lifecycle/database batch passed: 62 passed, 2 expected PostgreSQL skips, and 1
existing TestClient deprecation warning; final Query Policy/Phase 5 regression passed: 8 passed,
1 expected PostgreSQL skip. A disposable WSL/Docker pgvector PostgreSQL 16 container passed both
guarded foundation migration/index health and live FTS+dense query tests (2 passed), then was
removed. Scoped WSL `mutmut` generated 53 mutations in Query Policy: 49 killed; four equivalent
mutants remain only in RRF's output-invariant implementation details (stable insertion mechanism,
uniform first-occurrence score offset, or uniform score scale), with no surviving behavioral
authorization, mode, temporal, freshness, or ranking-order mutant.

Deliberate omissions: no approved record-level overlay shadowing key, freshness-policy schema or
external current-data fallback, reranker threshold, source-code structure adapter, API/Portal
surface, or Character runtime cutover. A different embedding model/dimension is exact-distance
queryable but has no ANN index until an explicit profile/rebuild decision.

Next action: Phase 6 should compose the Query Engine into the real Character Context boundary,
apply a fail-closed Character epistemic gate before prompt injection, and remove the duplicate
legacy RAG/Wiki prompt path. External current-data fallback stays deferred until its authority
contract is approved.

## Phase 6 — Character Context cutover and freshness/external lookup integration

Status: **completed — Fabric Character Context cutover committed**

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
- current-data Web/API fallback is deliberately deferred: `freshness_policy_json` has no approved
  schema, Query requests do not carry Character/deployment/tool authority, and no typed
  turn-local external-evidence contract exists. Phase 9 owns that adapter/freshness work;
- Discovery candidate remains non-authoritative;
- query engine failure keeps normal Character availability where knowledge grounding is non-blocking.

Performance invariant:

- full KnowledgeQueryEngine retrieval runs after Character/turn selection, not for every Smart Participation candidate.

Required gate:

- mention/reply/Smart/Social Character-turn tests;
- KnowledgeContext reaches provider prompt with provenance/uncertainty safety;
- unauthorized/epistemically denied facts do not reach prompt;
- `current` remains local-only and reports its existing freshness insufficiency without invoking
  Discovery, Browser, or Tool Runtime;
- no duplicate old RAG/Wiki injection;
- no Topic/legacy fallback;
- targeted mutation scope for epistemic denial, prompt-injection boundary, and Smart Participation
  admission/performance decisions;
- latency/budget guard for Smart Participation and Character turn.

Commit gate: one real-runtime Knowledge cutover commit.

### Phase 6 completion record — 2026-08-25

Implementation commit: `a16f78d feat: cut Character context over to Knowledge Fabric`.

Evidence: `src/echo_masque/knowledge_fabric_context.py`,
`knowledge_fabric_epistemic_policy.py`, `character_turn_context_v3.py`,
`context_resolver_v3.py`, `persistence/knowledge_fabric_repository.py`, `api/app.py`, and
`api/routes/smart_participation_vnext.py`; proof in
`tests/test_character_turn_context_v3.py` and
`tests/test_knowledge_fabric_epistemic_policy.py`.

Authority and runtime: the app composes one `KnowledgeQueryEngine` and the Character path looks up
only an existing `(platform, connection_id, guild_id)` Fabric Scope before it queries. It neither
creates a Scope nor runs the query while Smart Participation is evaluating candidates. The old RAG
and Server Wiki prompt paths are removed from the direct Character and candidate-context routes.
Fabric hits cross a fail-closed `CharacterEpistemicPolicy` boundary before the one normalized,
bounded Context section; the default policy denies every hit until Phase 10 supplies persisted
authored policy. Query and policy failure both fail closed without silencing the selected Character
turn. Prompt evidence is untrusted, instruction-delimited, provenance-labelled, and excludes raw
source locators from prompts and ordinary trace.

Freshness reconciliation: Phase 6 does not call Discovery, Browser, or Tool Runtime to answer a
current query. There is no approved freshness schema/threshold, importance signal, source match,
deployment tool authority, consent, or typed turn-local external-evidence contract. Discovery
remains candidate-only; Phase 9 owns adapters/adaptive freshness through the existing Tool Runtime
authority boundary.

Validation: `python -m ruff check .` passed. `python -m mypy` passed 359 source files. The final
affected regression batch passed: 47 passed, 1 expected PostgreSQL skip, and 2 existing third-party
warnings (Starlette TestClient deprecation and a Pydantic serializer warning). A prior broader
Phase 2–6/context batch passed 61 passed, 1 expected PostgreSQL skip, with the same two warnings.
The focused new Fabric/epistemic batch passed 8 tests. In an isolated WSL Ubuntu copy, `mutmut run`
against `knowledge_fabric_epistemic_policy.py` generated 11 mutants and killed all 11; no mutants
survived or were classified equivalent.

Deliberate omissions: no persisted Character epistemic allow/deny, timeline, spoiler, perspective,
or authored override policy (Phase 10); therefore the production default intentionally injects no
Fabric Evidence. No Web/API freshness fallback, Source Adapter, external-result persistence,
Projection/internal-tool migration, Portal surface, source-code adapter, or record-level overlay
shadowing inference is added.

Next action: Phase 7 should replace the remaining Wiki runtime/tool boundary with regenerable
provenance-aware Knowledge Projections without bypassing the Phase 6 Character Context, and keep
exact/source-evidence queries separate from derived Projections.

## Phase 7 — Projection Layer and internal tool cutover

Status: **complete — Fabric source overview Projection and Character internal-tool cutover delivered; Wiki compatibility deletion remains deferred to Phase 11**

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

### Phase 7 delivery record

Evidence map: `knowledge_fabric_models.py`, `knowledge_fabric_content_repository.py`,
`knowledge_fabric_projection_repository.py`, `knowledge_fabric_projection_policy.py`,
`knowledge_fabric_context.py`, `internal_context.py`, the Internal Context tool registry/contracts,
and the Phase 3/5/6/7 tests. `Corpus → Source → SourceVersion → EvidenceUnit` remains the only
knowledge authority; Projection text is derived-only and cannot satisfy exact/source Evidence
queries. Server scope authorization still occurs inside `KnowledgeQueryEngine`, and Character
epistemic admission still fails closed before a Tool result can return to the model.

Implemented: additive `KnowledgeProjection` and explicit `KnowledgeProjectionDependency` records
store corpus, typed subject, derived text, source hash, stale state, SourceVersion/Evidence IDs,
and evidence content hash. The first deterministic materialization is a lazily rebuilt source
overview; publishing a new snapshot marks views derived from any older version of that Source
stale, and account/corpus deletion removes dependency rows before Evidence rows. The pure
Projection-current policy requires an identical source hash and `stale == false`.

The Character-facing internal Tool is now `knowledge.search`, retaining only its existing bounded
`query` and `limit` input. It invokes the shared `KnowledgeContextBuilder`, so unknown scope,
query failure, and epistemic denial return no Fabric evidence; admitted results stay explicitly
untrusted and omit raw evidence locators. `memory.search` and `conversation.search` remain
separate. The old Server Wiki lookup is not composed into Character/internal-tool runtime.

Compatibility decision: Phase 7 does **not** delete legacy KB Wiki/Server Wiki persistence,
`/api/knowledge`, or Portal consumers. Those are Phase 11 compatibility consumers, and the plan's
earlier Phase 7/11 sequencing constraint takes precedence over a premature deletion claim. They
are no longer a Character-facing Fabric search authority.

Validation: `python -m ruff check src tests` passed; `python -m mypy` passed 361 source files; the
affected Phase 3–7 regression batch passed **60 passed, 3 expected PostgreSQL skips**. In an
isolated WSL Ubuntu cache, `mutmut run --max-children 4` against
`knowledge_fabric_projection_policy.py` generated 3 mutants and killed all 3 (0 survived,
timeouts, or equivalents).

Commit: `0ba2d6d` (`feat: add Fabric Projections and knowledge search`).

Deliberate omissions: no Fabric Projection query channel or projection-only exact answer; no
invented entity/event/timeline builder; no Portal/API compatibility rename; no persisted Character
epistemic policy; and no Source Adapter, freshness, or external lookup behavior.

Next action: Phase 8 should introduce deterministic-first Git/manual-import/structured-document
Source Adapters without broad crawling, while preserving the existing private R2-default S3
compatible object-storage boundary.

## Phase 8a — uploaded document and manual-text adapters

Status: **complete — deterministic manual/uploaded document adapter delivered; Git remains Phase 8b**

Goal: prove the existing immutable snapshot ingestion contract with caller-supplied, already
authorized manual text and uploaded documents before broad Web crawling.

Split decision (2026-08-25): Git requires a separate acquisition, ignore/deny, commit/tree/diff,
and version-visibility decision. The current Fabric has no Git credential-reference contract or
upload/sync endpoint, while document compilation can safely remain a deterministic library that
accepts already-authorized bytes and emits `SourceSnapshotIngestionRequest`. Keeping them together
would either invent an external acquisition/credential surface or hide a second lifecycle decision
inside a document parser. Phase 8a uses the existing private R2-default, S3-compatible artifact
boundary; Phase 8b owns Git after its explicit acquisition/retention contract is grounded.

Included order:

- manual text (including a manual import only for an explicitly selected Fabric Source, never an
  inferred legacy-RAG scope mapping);
- Markdown/text;
- DOCX structured parser;
- PDF layout-text parser with a typed `requires_ocr` outcome when no reliable text layer exists;
- structural headings/paragraphs/lists/tables/links/images/page/section provenance where the
  source format exposes it.

Authority and omission boundary:

- This is an adapter/library boundary, not a new public upload API or an arbitrary local-path
  reader. Existing Source registration remains the authorization boundary.
- It does not create object-store credentials, public object URLs, OCR, document vision, embedded
  child-asset storage, or automatic migration of legacy RAG bases. Raw bytes remain the one private
  source artifact, and unavailable scanned documents are not published as fabricated text.

Document requirements:

- preserve headings/paragraphs/lists/tables/links/images/page/section provenance;
- store structured table + retrieval representation where parser structure exposes it;
- keep raw artifact in object storage;
- LLM enrichment selective/lazy only.

Required gate:

- fixture-based Markdown, DOCX, and digital/scanned-PDF branch tests;
- source-version/evidence/provenance and private raw-artifact tests;
- ingestion job retry/idempotency regression;
- targeted mutation test for the pure document-type/scanned-content decision scope.

Commit gate: one Phase 8a document/manual adapter implementation commit.

### Phase 8a delivery record

Evidence map: `knowledge_fabric_ingestion.py`, `knowledge_object_storage.py`,
`knowledge_fabric_content_repository.py`, `knowledge_fabric_document_adapter.py`,
`knowledge_fabric_document_policy.py`, `tests/test_knowledge_fabric_document_adapter.py`, and
the Phase 3 content/storage lifecycle tests. The current Source registration APIs remain evidence
that a caller must select an existing authorized Fabric Source; they do not authorize an upload API.

Implementation: `KnowledgeFabricDocumentAdapter` is a deterministic library-only compiler for
already-authorized manual UTF-8 text, Markdown, OOXML DOCX, and text-layer PDF bytes. It produces
the existing immutable `SourceSnapshotIngestionRequest`; `KnowledgeFabricIngestionService` retains
sole object-storage/job/publication authority. Markdown preserves heading hierarchy, paragraphs,
lists, tables, inline links, and line coordinates. DOCX preserves heading/list/table/hyperlink/image
relationship provenance using only its standard OOXML package. Digital PDFs preserve page and text
layer provenance; a textless PDF raises typed `DocumentRequiresOcr` and cannot publish fabricated
Evidence. Filename/type/OCR decisions are explicit pure policy and no arbitrary metadata field can
carry credentials into a SourceVersion.

Validation: `python -m ruff check src tests` passed; `python -m mypy` passed 363 source files; the
combined Phase 3/5/6/7/8a regression batch passed **42 passed, 3 expected PostgreSQL skips**.
WSL-native Mutmut, after deleting its generated cache to invalidate older results, generated 48
mutants in `knowledge_fabric_document_policy.py` and killed all 48 (0 survived, timeout, or
equivalent).

Commit: `daf7a40` (`feat: add deterministic Fabric document adapters`).

Deliberate omissions: no public upload endpoint, arbitrary local-path reader, network acquisition,
Git client, private-Git credential contract, legacy RAG base-to-corpus inference, OCR/document
vision worker, embedded child-asset storage, or LLM enrichment. The private Cloudflare R2-default,
S3-compatible boundary and Phase 3 owner lifecycle stay unchanged.

Next action: Phase 8b needs an explicit Git acquisition, deny/ignore, and source-version retention
decision before code; it must not silently make current-code queries return obsolete Git revisions.

## Phase 8b — Git repository Source adapter

Status: **complete (2026-08-25)**

Goal: add a deterministic Git/GitHub adapter without expanding the document upload or credential
surface.

Phase 8b decisions (2026-08-25): the first adapter remains library-only. A trusted acquisition
boundary supplies an immutable commit/tree/file snapshot; this phase adds no subprocess Git client,
network request, public upload route, local-path reader, or private-Git Credential Vault mapping.
Its source type is `git_snapshot`. A successful Git snapshot activation keeps immutable prior
Versions, artifacts, Evidence, and derived index rows, but atomically changes other currently
available Versions of the same Git Source to `superseded`; query channels already exclude a
non-available Version. Re-seeing a previously superseded commit reactivates it and supersedes the
other available Version. Generic/manual/document Source Versions retain their existing history
behavior. This status transition must occur in the publication/deduplication transaction, never as
a post-publication cleanup.

The deliberately approved initial deny policy rejects an empty, absolute, traversal, or
separator-normalized unsafe path; `.git` content; `.env` files; common private-key/credential
filenames and key-store suffixes; and dependency/build/cache directories (`node_modules`, `vendor`,
`.venv`, `venv`, `__pycache__`, `dist`, `build`, `.cache`, `.pytest_cache`, `.mypy_cache`). Denied
bytes do not enter the stored sanitized Git snapshot, canonical documents, Evidence, job metadata,
or errors. Binary/undecodable files are not raw child assets in this phase; they remain a later
asset-ingestion concern.

Git requirements:

- immutable commit/tree identity plus deterministic no-change/changed-commit behavior; the
  authorized Git diff/acquisition driver is explicitly deferred to the Phase 9 external-source
  boundary rather than inferred by this library-only compiler;
- explicit ignore/deny secret, dependency, build, and cache policy;
- source-code AST/symbol/import/dependency extraction where practical;
- no acquisition surface in this compiler; a future public-HTTPS policy or explicitly authorized
  Credential Vault reference must be approved before a driver is added, and no token may enter a
  Source locator/profile metadata;
- explicit source-version retention/visibility semantics before an incremental sync claims that an
  obsolete revision cannot be returned by a current-code query;
- no requirement to LLM-summarize every code file.

Required gate:

- deterministic tree/commit fixture tests including no-change and changed-commit behavior;
- secret-exclusion proof that bytes do not reach artifacts, documents, Evidence, job metadata, or
  errors;
- source-version/query-visibility decision tests;
- ingestion retry/idempotency tests and targeted mutation testing of the pure allow/deny policy.

Commit gate: one Phase 8b Git adapter implementation commit after the acquisition and retention
contract is documented from repository evidence.

### Phase 8b delivery record (2026-08-25)

Implementation: `KnowledgeFabricGitAdapter` accepts only a trusted immutable repository snapshot
(`source_id`, commit/tree identity, optional parent identity, and in-memory path/bytes entries) and
deterministically compiles it into the existing `SourceSnapshotIngestionRequest`. It has no Git CLI,
network, local-path, credential, or object-storage authority. The sanitized artifact includes only
accepted UTF-8 text files and the commit/tree identity, so a changed commit remains a distinct
immutable artifact even when a file body is unchanged. Python files retain top-level AST
class/function sections and blocks plus deterministic imports; other accepted text files retain a
file block. A no-change delivery has a stable retry key and reuses the existing source version.

The pure `knowledge_fabric_git_policy.py` permits only full, compatible SHA-1 or SHA-256
commit/tree identities and safe repository-relative paths. It rejects traversal, separator abuse,
control characters, `.git`, `.env*`, credential/key names and suffixes, and the approved
dependency/build/cache directories. The adapter omits denied and undecodable bytes before artifact,
document, Evidence, or job creation. `activate_git_version` is restricted to `git_snapshot`
Sources before any private upload. On a changed Git snapshot, publication atomically marks the
other available version(s) for that same Source `superseded`; retained artifacts, Evidence, and
derived index entries remain intact. Re-delivering a retained commit reactivates it in the same
dedupe path and supersedes the former current version. Generic manual/document history behavior is
unchanged.

Validation: the Phase 3/5/6/7/8a/8b regression batch passed **33 tests with 3 expected PostgreSQL
skips**; `python -m ruff check src tests` passed, and `python -m mypy` passed 365 source files.
WSL-native mutmut ran against `knowledge_fabric_git_policy.py` after clearing its generated cache:
**77/77 killed, 0 survived, timeout, or equivalent**. The generated `mutants/` cache was removed
after recording the result.

Commit: `60a8f39` (`feat: add deterministic Fabric Git snapshots`).

Deliberate omissions: this boundary does not acquire a Git repository, invoke a Git client, read a
local checkout, make public-HTTPS requests, implement a credential-vault reference, or determine a
Git diff itself. A future authorized acquisition/sync worker must obtain the immutable tree and
use Git revision/diff data to decide when to submit it. This phase deliberately provides the
deterministic no-change/retry and changed-commit retention semantics that worker needs, without
expanding its authority. It also does not ingest binary child assets, summarize code with an LLM,
or alter R2's private-by-default/S3-compatible storage contract.

Next action: Phase 9 must define the external acquisition/freshness boundary before adding any
website, Wiki, API, or feed client.

## Phase 9 — Website/Wiki/API/feed adapters and adaptive freshness

Status: **complete — Phase 9 is complete; Phase 10 is next (2026-08-26)**

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

### Phase 9a — Public-HTTPS Website response sync boundary

Decision: Phase 9a is deliberately worker/library-only. It will add one registered
`website_public_https` Source contract for a configured, exact public HTTPS page, a deterministic
HTML/text response compiler, conditional validator state, and changed/no-change outcome handling.
It will not expose a sync HTTP route, scheduler, Portal control, Character live lookup, source
credential, redirect following, discovery/crawl/sitemap traversal, browser rendering, feed/API/Wiki
client, or default outbound HTTP client. The worker must inject an approved fetcher. This preserves
the existing `PublicUrlGuard` as a preflight policy without treating a preflight DNS lookup as
authorization for a new unpinned production egress client; an approved worker transport/DNS
binding policy is a separate Phase 9b decision.

The first source locator is canonical public HTTPS only: no userinfo, query, fragment, alternate
port, or redirect. The fetch request may send only stored ETag/Last-Modified validators from a
one-per-Source derived sync-state record. It accepts bounded `text/html`, `text/plain`, and
`text/markdown` response bytes; a 304 creates no artifact/version, while a changed valid 200 flows
through the existing private R2/S3 immutable snapshot service. A same-content 200 reuses the
existing version/job and records a no-change check. HTTP/network/content rejections record only a
bounded outcome/error code and no raw response/provider detail. Existing `last_checked_at` and
`last_changed_at` become the source-visible timestamps; the new state stores only validators and
safe outcome data, never configuration JSON or a credential.

Phase 9a gate: deterministic generic Website fixtures for HTML/text structure; mocked changed 200,
conditional 304, same-content 200, rejected URL/redirect/content, and network/auth failure
outcomes; source timestamp/state and private artifact proof; targeted mutation testing of the pure
external-response/validator policy. Phase 9b will add an approved egress transport plus a
source-native specialized adapter (MediaWiki, feed, docs, forum, or API), explicit scheduling/rate
authority, and the remaining full Phase 9 gate.

### 2026-08-26 Phase 9a completion gate

    Status: complete — Phase 9a implementation is committed; Phase 9 remains open only for Phase 9b
    Commit: 1cd5fd6 (feat: add bounded Fabric Website source sync)
    Changed authority/contracts: one exact public-HTTPS Website Source can be synchronized only by an injected, separately approved worker fetcher. It has no default egress client, public API, scheduler, crawl, redirect, credential, browser, or Character-live-lookup authority. A one-per-Source derived state stores only bounded ETag/Last-Modified validators and safe outcomes; malformed validators fail before private artifact or Source Version publication. User-owned Source deletion removes that derived state in the existing lifecycle transaction.
    Key files: src/echo_masque/knowledge_fabric_external_policy.py; src/echo_masque/knowledge_fabric_website_adapter.py; src/echo_masque/knowledge_fabric_website_sync.py; src/echo_masque/persistence/knowledge_fabric_external_sync_repository.py; src/echo_masque/persistence/knowledge_fabric_models.py; src/echo_masque/persistence/knowledge_fabric_repository.py; src/echo_masque/persistence/schema_migrations.py; tests/test_knowledge_fabric_website_sync.py; tests/test_knowledge_fabric_phase3.py
    Validation: python -m pytest tests/test_knowledge_fabric_website_sync.py tests/test_knowledge_fabric_git_adapter.py tests/test_knowledge_fabric_document_adapter.py tests/test_knowledge_fabric_phase3.py tests/test_knowledge_fabric_phase5.py tests/test_database_foundation.py passed: 30 passed, 3 expected PostgreSQL skips (88.85s). python -m ruff check src tests and python -m mypy src passed (369 source files); git diff --check passed. Focused WSL mutmut scope completed: 117 killed / 3 equivalent / 0 timeout, no unclassified survivor. Equivalent IDs: canonical locator mutation 33 changes rstrip(".") to rstrip("XX.XX"); urllib's hostname accessor lowercases ASCII host text before this operation, so added uppercase X is unreachable while both strip trailing dots. Response-policy mutations 29 and 32 change split(";", maxsplit=1)[0] to split(";", )[0] and split(";", maxsplit=2)[0]; each returns the same first semicolon-delimited segment for every string.
    Migration/data action: additive knowledge_external_source_sync_states schema plus revision ledger; existing Sources begin with no derived state and require no backfill.
    Known deviations: Cloudflare R2 remains the configured default private artifact provider; AWS S3 remains only the existing explicit S3-compatible deployment alternative. The WSL systemd user-session warning is non-fatal. The generated mutants/ cache was removed after result recording.
    Next action: define an approved pinned egress transport and one source-native specialized adapter/scheduling authority for Phase 9b.

### 2026-08-26 Phase 9b / Phase 10 decision record

    Status: product decisions confirmed by the user on 2026-08-26. Phase 9b is complete; Phase 10 remains unimplemented.
    Evidence: src/echo_masque/network_safety.py validates a public URL but returns no resolved address for a caller to dial. Existing Tool Runtime clients resolve again, can carry a different scope/credential/redirect contract, and are not an approved Fabric worker transport. KnowledgeSource.sync_policy_json/freshness_policy_json have no schedule/rate semantics. Source snapshot publication invalidates the whole source projection/index set, so current code cannot prove entry/section-only invalidation. Phase 10 still installs DenyAllCharacterEpistemicPolicy, has no persisted Character policy, and has no existing corpus/evidence domain field.
    Confirmed decisions: only Super Admin may enable autonomous sync; schedules default disabled, require 15 minutes or more, use a 60-second global hostname cooldown and durable lease/retry state; Atom 1.0 is the first specialized source; `defusedxml` is required; Atom entry links remain provenance only and are never followed. Phase 10 remains corpus-level default-deny with allow/deny and deny precedence; authored override stays corpus-level and is writable only by Super Admin or an explicit Server Administrator. Timeline, spoiler, perspective and domain taxonomy remain unapproved.
    Recommended next split after approval: Phase 9b-1 implements a literal-IP/pinned-DNS public HTTPS worker transport, Atom 1.0 adapter, bounded durable schedule/lease state, and no link crawling; Phase 9b-2 defines entry/section identity and selective invalidation. Phase 10 then implements default-deny, scope-bound corpus allow/deny with the selected override/write semantics, preserving query authorization-before-ranking and the shared turn/tool fail-closed gate.
    Phase 9b-1 implementation: `PinnedPublicHttpsFetcher` resolves once, rejects any non-global DNS candidate, dials one literal address while retaining the registered hostname for TLS SNI/certificate validation and HTTP Host, and rejects redirects/proxies/credentials/oversize responses. A durable default-disabled schedule/lease table and Super-Admin-only schedule API own egress consent; the application worker starts only this bounded scheduler. Atom source snapshots are DTD/entity-free `defusedxml` parses and retain only feed-entry evidence plus safe provenance links. User-owned lifecycle deletion removes derived schedule state. Focused proof: pinned transport (15 tests), Atom adapter (5 tests), schedule/migration (3 tests), Phase 3 lifecycle (6 tests), Website sync (5 tests); Ruff and MyPy pass; application composition creates successfully. Mutation proof ran in a disposable WSL-native copy because mutmut cache writes on `/mnt/d` stall in the Windows 9p client: 36 mutants, 34 killed, 2 equivalent, no timeout/no-test/interrupted result. Equivalent mutations 29 and 32 change `split(";", maxsplit=1)[0]` to zero/two max-splits; element zero is the same pre-semicolon value for every string.
    Commit: 5848fcc (feat: add pinned Atom source synchronization)
    Deliberate omissions: no Tool Runtime/browser/Jina transport, proxy, redirect, credential mapping, manual sync trigger, crawl, Atom entry-link fetch, domain taxonomy, timeline/spoiler policy, or invented override semantic.

### 2026-08-26 Phase 9b-2 completion gate

    Status: complete — selective Atom entry invalidation is implemented; Phase 10 is now next.
    Changed authority/contracts: `knowledge_source_current_entries` is a derived source-local map from stable Atom entry locator to its current retained Evidence. It retains immutable source/document/Evidence history, reuses unchanged entry Evidence, remaps only new/materially changed entries (including title or safe-link provenance changes), and marks removed entries unavailable. Candidate retrieval and Atom source-overview rebuilds select only available mapped Evidence; retained projection dependencies retain their own source-version/hash. A reordered or raw-format-only Atom snapshot advances observation but creates neither index/projection invalidations nor a source-overview rebuild. Generic sources keep whole-source invalidation.
    Key files: src/echo_masque/knowledge_fabric_current_entry_policy.py; src/echo_masque/knowledge_fabric_atom_adapter.py; src/echo_masque/persistence/knowledge_fabric_content_repository.py; src/echo_masque/persistence/knowledge_fabric_index_repository.py; src/echo_masque/persistence/knowledge_fabric_projection_repository.py; src/echo_masque/persistence/knowledge_fabric_models.py; src/echo_masque/persistence/schema_migrations.py; tests/test_knowledge_fabric_atom_current_entries.py; tests/test_knowledge_fabric_current_entry_policy.py
    Validation: focused Atom/current-entry/projection/Phase 3/Phase 5/database batch passed before final review; targeted current-entry regression passed after lifecycle coverage was added. Ruff, strict MyPy (376 source files), and git diff --check passed. The tracked WSL runner `scripts/run_mutmut_wsl.sh` was syntax-checked and ran the configured current-entry policy scope from a disposable WSL-native copy: 12 killed / 0 survived / 0 timeout / 0 tooling failures. The non-fatal WSL systemd user-session warning remains unrelated to mutation execution.
    Migration/data action: additive `knowledge_source_current_entries` table and migration ledger; no backfill is inferred for pre-map Atom Evidence, so Atom candidates fail closed until the next trusted Atom snapshot creates pointers.
    Commit: 5186862 (feat: add selective Atom entry invalidation)
    Deliberate omissions: no generic section-diff protocol, source-link crawling, alteration of immutable historical records, new egress authority, or Phase 10 Character policy.
    Next action: implement Phase 10 corpus-level default-deny Character policy with explicit allow/deny precedence and preserve authorization-before-ranking.

## Phase 10 — Character epistemic policy

Status: **complete — corpus-level implementation committed; deferred schemas remain unapproved**

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
- targeted mutation scope for Character corpus/domain allow/deny and authored override decisions.

Commit gate: one epistemic-policy commit.

### 2026-08-26 Phase 10 completion gate

    Commit: 718326e (feat: add Character corpus epistemic policy)
    Changed authority/contracts: an additive, server-scope-bound `(deployment, Character card, corpus)` policy persists `allow` or `deny`; no policy denies by default and deny wins. Authoring verifies the current deployment/card belongs to the target scope and corpus is already server-authorized. Query authorization remains before ranking; this policy is only the shared final prompt/internal-tool admission gate. Super Admin or explicit scope administrators author through the audited API.
    Validation: focused persistence/API policy tests passed; existing epistemic, turn-context, internal-tool, Phase 2 and database batches were run as the coherent gate. Ruff, MyPy (377 files), and diff check passed. WSL-native mutmut: 3 killed / 0 survived / 0 timeout.
    Deliberate omissions: no invented domain, timeline, spoiler, perspective, or known-entity schema; authority profiles do not become domains by inference.
    Next action: Phase 11 Portal/Admin operational surfaces, lifecycle/audit hardening, and final compatibility cleanup.

## Phase 11 — Portal/Admin operations, lifecycle hardening, scale and cleanup

Status: **in progress — split into non-overlapping Portal and final-cutover batches**

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
- targeted Portal/Connector mutation scopes for privileged management and scoped inspection paths;
- synthetic large-corpus performance and isolation test;
- final docs/link/security review.

Commit gate: one final product/cutover cleanup commit, or split Portal and cleanup only after updating this plan with non-overlapping gates.

### Phase 11 execution split

The scope is intentionally split so the new Server Portal can be reviewed without burying
legacy deletion and lifecycle proof in the same diff. The main agent remains responsible for
the final integration and review.

1. **11a — Server Knowledge Fabric Portal.** Replace the active Deployment Workspace Knowledge
   page's RAG V1 entry with scope-bound Fabric management: effective Corpora, reversible global
   grants/overlays, server-local Corpus/Source registration, and Character allow/deny policy.
   Gate: targeted Fabric authorization/Public Demo regression, Portal typecheck/Vitest/build,
   changed-source Ruff/strict MyPy, and scoped management-request tests. It deliberately does
   not delete compatibility code or claim Super Admin operational completion.
2. **11b — Super Admin and operational inspection.** Add only source-backed management,
   sync/index/job health, retry/rebuild/publish controls, and Evidence/Query inspection that
   existing Runtime contracts can support. Gate: API authorization/lifecycle/observability proof,
   Portal verification, and a targeted privileged-management mutation scope.
3. **11c — Compatibility and final cutover.** Remove or archive old RAG/Wiki consumers only after
   static reference proof and replacement-surface validation; finish lifecycle, scale,
   PostgreSQL, documentation, Connector, mutation, and security gates listed above.

No batch may introduce a second retrieval authority, expose credentials, or use a denied Corpus
as effective query input.

### Phase 11b execution detail

11b is split into read-only inspection before operator mutations because no invalidation consumer
or configured embedding Runtime currently authorizes a rebuild/retry/publish promise.

1. **11b-1 — Authorized query and source-health inspection.** Add an administrator-scoped Query
   Inspector that delegates to the existing `KnowledgeQueryEngine`, and a Super-Admin-only,
   redacted global-source operational view assembled only from persisted Source/schedule/sync
   state. Its gate is Phase 2/5/schedule authorization proof, source-health privacy proof,
   Portal/API type and test verification, and a targeted query-authorization mutation scope.
2. **11b-2 — Operator actions only when executable.** Add retry/rebuild/publish or availability
   controls only alongside a source-backed worker/invalidation consumer and its lifecycle,
   idempotency, audit, and failure-path proof. It must not expose lease tokens, validator values,
   generic metadata, credentials, or raw artifacts.

### 2026-08-26 Phase 11a completion gate

```text
Status: complete — Server Knowledge Fabric Portal batch; Phase 11b/11c remain open
Commit: `3543dd9` (`feat: add Knowledge Fabric server portal`)
Changed authority/contracts: the active Deployment Workspace Knowledge page now resolves the
selected Discord `(connection_id, guild_id)` only to an authorized Fabric server scope, never to
legacy RAG. It manages effective Corpus visibility, reversible global grant/overlay state,
server-local Corpus/HTTP(S) Source registration, and persisted Character allow/deny policy.
The added access-state read model lists only active global Corpus IDs plus server-local grant and
overlay state; a denied Corpus remains unavailable to retrieval but visible to its authorized
administrator so it can be restored. Public Demo remains server-side denied and client-side
read-only. Source registration does not claim a source is published, synced, or indexed.
Key files: web/src/KnowledgeFabricPanel.tsx; web/src/knowledgeFabricApi.ts;
web/src/DeploymentCenter.tsx; web/src/knowledgeFabricApi.test.ts;
src/echo_masque/api/routes/knowledge_fabric.py;
src/echo_masque/persistence/knowledge_fabric_repository.py;
tests/test_knowledge_fabric_phase2.py
Validation: targeted Python authorization/Public Demo regression — 8 passed; changed-source
Ruff and strict MyPy (377 files) passed; Portal typecheck passed; Portal Vitest 22 files / 64
tests passed; production Vite build passed. Portal Stryker mutated portalEnvironment and
knowledgeFabricApi: 59 killed, 1 equivalent survivor, 34 TypeScript checker rejections, no
timeout/runtime/no-coverage result. The equivalent survivor is the comment-only body of the
non-JSON error catch: replacing it with an empty block preserves the same raw-body/fallback
return path for every input. Windows left completed Stryker sandboxes; their reports were read and
the exact generated sandboxes were removed before the final Portal test run.
Known deviation: `python -m ruff check src tests` still reports two pre-existing E501 lines in
tests/test_knowledge_fabric_external_schedule.py, outside this batch. The full Phase 11 gate and
its PostgreSQL/scale/lifecycle evidence remain for 11c.
Next action: Phase 11b must add only source-backed, redacted Super Admin and scoped query/evidence
read models. Do not expose rebuild/retry/publish controls until the invalidation worker and
embedding-runtime contracts exist.
```

### 2026-08-26 Phase 11b-1 completion gate

```text
Status: complete — authorized query and global-source health inspection; 11b-2/11c remain open
Commit: pending final diff review
Changed authority/contracts: `POST /server-scopes/{scope_id}/query-inspector` first resolves the
existing server scope through `_scope_for_actor`, then delegates to the one existing
`KnowledgeQueryEngine` with its established four-result bounded request. It writes only a
query-free audit summary. `GET /admin/corpora/{corpus_id}/operational-sources` is Super-Admin-only
and returns a redacted persisted Source/schedule/sync-state view; locators, profiles, artifacts,
validators, leases, generic metadata, and credentials remain private.
Validation: `pytest` Phase 2/5/external-schedule/query-policy batch: 13 passed, 1 PostgreSQL-only
skip; changed-source Ruff and strict MyPy (377 files) passed. WSL-native mutmut: 52 killed,
4 reviewed equivalent survivors, 0 timeout/no-coverage/compile results. The retained equivalents
are all in rank fusion: replacing first-seen values with identical values still uses Python's
insertion ordering, and adding the same constant/positive multiplier to every candidate score
preserves the ordered evidence IDs. The request-none and rank-offset behavioral mutations are
killed by explicit tests. The nonfatal WSL systemd user-session warning persists.
Deliberate omissions: no source/job/checkpoint/invalidation metadata, no raw artifacts, no dense
embedding claim, and no retry/rebuild/publish action. Those require 11b-2 worker ownership proof.
Next action: build the Super Admin Portal surface over these read models, then implement only
worker-backed actions with lifecycle/idempotency evidence.
```

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

Resume at the recorded current phase after verifying the branch and completion records. Do not
restart completed foundation phases or infer that an uncommitted phase record is already on `main`.

### 2026-08-25 Phase 1 mutation-testing foundation update

```text
Status: in progress
Commit: none; Phase 1 remains open and permits only one final database-foundation commit
Changed authority/contracts: mutation testing is required for configured protected decision scopes; it complements, not replaces, ordinary tests and migration/authorization proof
Key files: docs/mutation-testing.md; AGENTS.md; docs/ai-agent-development-workflow.md; docs/agent-handoff.md; docs/agent-map.md; docs/developer/README.md; pyproject.toml; web/stryker.config.json; connectors/discord/stryker.config.json; .github/workflows/mutation.yml
Validation: python -m ruff check . passed; python -m pytest tests/test_config.py passed (5); Portal typecheck + Vitest passed (20 files/55 tests); Connector typecheck + Vitest passed (17 files/91 tests); Portal Stryker baseline produced 9 killed / 3 survived / 5 compile-error mutants; Connector Stryker baseline produced 15 killed / 7 survived / 16 compile-error mutants; package/config JSON parse and git diff --check passed
Migration/data action: none
Known deviations: mutmut is installed/configured but native Windows explicitly requires WSL; local WSL enumeration is access-denied, so the Python mutant run remains for the Ubuntu scheduled/manual workflow. Stryker results are non-blocking Phase 1 baselines; their survivors and compile errors are recorded for classification before the relevant protected scope becomes a gate. Windows terminal process tracking left generated Stryker sandboxes/reports, which were removed after the completed reports were inspected.
Next action: continue the Phase 1 PostgreSQL source/migration/deployment audit; use Linux CI or an available WSL environment to record the initial Python mutmut report before the Phase 1 database gate.
```

### 2026-08-25 Phase 1 PostgreSQL implementation update

```text
Status: in progress
Commit: none; Phase 1 remains open and permits only one final database-foundation commit
Changed authority/contracts: PostgreSQL is now a first-class database backend with a persistent foundation revision, pgvector extension bootstrap, PostgreSQL equivalents of the Discord server uniqueness/runtime-cleanup invariants, and an explicit SQLite-to-empty-PostgreSQL copy ledger. SQLite remains supported only for dev/test and as a retained migration source until an operator completes the documented cutover.
Key files: src/echo_masque/persistence/database.py; src/echo_masque/persistence/schema_migration_models.py; src/echo_masque/persistence/schema_migrations.py; src/echo_masque/persistence/sqlite_to_postgres_migration.py; scripts/migrate_sqlite_to_postgres.py; tests/test_database_foundation.py; tests/test_storage_guard.py; .github/workflows/ci.yml; docs/railway-deployment.md; docs/storage-safety.md
Validation: focused SQLite regression passed — python -m pytest tests/test_database_foundation.py tests/test_deployment_server_invariant.py tests/test_storage_guard.py tests/test_phase15_migration.py (10 passed, 2 PostgreSQL integration tests skipped because no explicit local disposable PostgreSQL URL); ruff and strict mypy passed for changed persistence modules; CI YAML parsed; git diff --check passed. The new CI postgres-foundation job provisions the official pgvector PostgreSQL 16 image and runs the fresh-bootstrap, unique/cleanup, SQLite-copy, and idempotency integration tests.
Migration/data action: migrate_sqlite_to_postgres first creates a unique, consistent SQLite backup-API snapshot (including committed WAL content), fingerprints snapshot bytes, and copies only that snapshot. It requires a current completed Intelligence cutover with no non-empty legacy tables, takes a PostgreSQL advisory lock around a strict empty-target/unknown-object preflight, preserves IDs/sequences, and records success/failure without deleting or mutating the original source.
Known deviations: local Docker is unavailable, so the PostgreSQL-only two-test gate is configured in CI but not locally executed. The source migration tool intentionally fails stale SQLite schemas instead of performing source-side repair during a cross-database cutover.
Next action: review the combined Phase 1 diff and run the complete local Python/Portal/Connector validation gates; after the PostgreSQL CI evidence is available, make the single Phase 1 commit and begin Phase 2 Corpus/Source/access work.
```

### 2026-08-25 Phase 1 mutation baseline classification update

```text
Status: in progress
Commit: none; this evidence remains part of the single Phase 1 commit
Scope/results: Portal web/src/portalEnvironment.ts — 12 killed, 0 survived, 5 TypeScript-checker tooling/compile rejections (IDs 0, 5, 6, 10, 11). Discord Connector connectors/discord/src/audiencePreflight.ts — 22 killed, 0 survived, 0 timeout, 16 TypeScript-checker tooling/compile rejections (IDs 1-5, 9-11, 13, 17, 18, 22, 23, 25, 26, 37). No equivalent mutants or unclassified survivors remain in the configured Portal/Connector baseline scopes.
Evidence changes: Portal import-time environment/default-path tests now prove mock/live `isMockPortal`; Connector collaborator-boundary/default-alias/empty-short-circuit/smart-scoring tests now prove preflight decisions. The scheduled/manual workflow uploads HTML reports for both JavaScript scopes.
Platform result: both local Windows Stryker runs fully generated reports but exited 1 only after completion because worker cleanup's `taskkill` was access-denied. Elevated WSL inspection showed no installed Linux distribution. Ubuntu CI is therefore the supported passing platform for all three mutation runners; native Windows reports are diagnostic only.
Known deviation: the Python mutmut command is configured with `only_mutate = ["src/echo_masque/config.py"]` and runs in Ubuntu CI, but has not been executed locally because this machine has no WSL distro. Its initial CI report must be recorded before Phase 1 is declared complete.
Next action: obtain the scheduled/manual Ubuntu mutation workflow evidence, then run the full local validation/diff review and make the Phase 1 commit.
```

### 2026-08-25 Phase 1 final local validation update

```text
Status: in progress
Commit: none; the final Phase 1 commit remains intentionally pending the Linux-only Python mutation evidence
Validation: Python full gate — python -m pytest -x --junitxml <temporary path> passed: 696 passed, 2 skipped, 7 existing warnings, 0 failures, 0 errors (819.61s); temporary JUnit evidence was deleted after inspection. Changed persistence Ruff + strict mypy passed. Real disposable PostgreSQL 17 + psycopg verification passed: complete ORM schema, Discord partial unique index, runtime cleanup trigger, SQLite snapshot copy, serial reset, idempotent rerun, and changed-source refusal. pgvector extension bootstrap is exercised by the committed CI service definition because the local PostgreSQL install lacks pgvector. Portal full gate passed: typecheck, 20 files/56 tests, production build. Connector full gate passed: typecheck, 17 files/95 tests, build. CI/mutation workflow YAML and pyproject TOML parse; git diff --check passed.
Mutation classification: Portal 12 killed/0 survived/5 tooling-compile; Connector 22 killed/0 survived/16 tooling-compile. Python mutmut is configured to mutate only config.py, but cannot run locally: elevated WSL status succeeds yet reports no installed distribution. Native Windows mutmut is unsupported; native Windows Stryker is diagnostic only because post-report worker cleanup is access-denied.
Known deviations: no Linux distribution, Docker engine, or local pgvector is installed. No production database has been migrated or switched; the tool/docs provide a deliberate operator-controlled cutover only. Phase 2 reconnaissance found an unresolved product-authority decision: current source lacks a stable Server principal and a Server Admin predicate, so server-owned corpus/overlay authorization cannot safely be inferred from owner-scoped Discord profile IDs.
Next action: with explicit authority, install an Ubuntu WSL distribution and run `mutmut run` + `mutmut export-cicd-stats`; otherwise obtain the manual/scheduled Ubuntu workflow report after the Phase 1 commit. Resolve the canonical Server principal/Server Admin authorization decision before implementing Phase 2 schema/API work.
```

### 2026-08-25 Phase 1 completion gate

```text
Status: complete — one final database-foundation commit is pending the final diff review
Commit: pending; this completion record is included in the single Phase 1 implementation commit
Changed authority/contracts: PostgreSQL + pgvector is production-capable while SQLite remains development/test and a deliberately operator-controlled migration source. A running/failed SQLite-copy ledger blocks ordinary target startup; only the migration tool can bypass it. No Character Knowledge semantic authority changed.
Validation: Python full gate — 699 passed, 2 skipped, 7 existing warnings, 0 failures/errors (803.73s); changed persistence Ruff + strict mypy passed. Focused database/config regression — 13 passed, 2 explicit PostgreSQL tests skipped without a test URL. Real WSL/Docker pgvector PostgreSQL 16.15 — the two explicit foundation integration tests passed (2 passed in 8.10s), exercising CREATE EXTENSION vector, Discord unique deployment constraint, runtime cleanup trigger, SQLite-to-PostgreSQL copy, idempotent rerun, and changed-source refusal. The destructive test guard rejects both a missing opt-in and any database name other than the dedicated `echo_masque_test` before connecting/resetting. Portal — typecheck, 20 files/56 tests, production build passed. Connector — typecheck, 17 files/95 tests, build passed. Mutation baselines: Python mutmut (WSL-native temporary copy) 1 killed/0 survived/0 timeout; Portal 12 killed/0 survived/5 TypeScript checker rejections; Connector 22 killed/0 survived/16 TypeScript checker rejections. No equivalent or unclassified survivor remains. YAML/TOML parse and git diff --check passed.
Mutation platform note: WSL can run the command, but the Windows-mounted workspace denies pytest cache writes; the supported local invocation copies the current worktree to a disposable WSL-native directory. The WSL systemd user-session warning is non-fatal. Native Windows Stryker remains diagnostic only because post-report worker cleanup is access-denied.
Deliberate omissions: no production database was migrated or switched; the migration tool remains operator-invoked. No Phase 2 schema/API/runtime behavior was added.
Next action: make the single Phase 1 commit, then resolve the durable canonical Server identity and Server Admin predicate before beginning Phase 2. Existing user-owned profiles and connection-scoped access grants must not be reused by inference.
```
