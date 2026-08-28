# Knowledge Fabric Architecture Contract

Status: **implemented architecture contract for `codex/knowledge-fabric-foundation`; Phases 1–11c are delivered, with current validation recorded in the active plan**

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

Original large artifacts belong in private object storage. PostgreSQL stores the structured records,
references, hashes, permissions, and queryable metadata rather than large opaque blobs. Cloudflare
R2 and AWS S3 are the normal multi-replica stores; an explicitly configured private mounted
filesystem is supported only for a single-replica durable deployment. Missing storage configuration
must fail ingestion rather than publish a partial Source Version, and none of these stores creates
public object URLs.

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

### Phase 8a uploaded-document boundary

The first delivered document adapter is deliberately library-only. An already-authorized caller
supplies bytes for an existing Fabric Source, and the adapter deterministically emits the existing
snapshot/canonical-document contract; only the ingestion service publishes the private R2/S3
artifact and Source Version. It supports UTF-8 manual text/Markdown, OOXML DOCX structure, and
PDF text layers. A PDF without usable text is an explicit OCR-required outcome, not synthetic
Evidence. This does not define a public upload endpoint, arbitrary local-file access, child-asset
store, OCR worker, or Credential Vault mapping. Those surfaces require their own authority and
lifecycle contracts.

### Phase 8b Git snapshot boundary

The initial Git adapter is likewise library-only. An already-authorized acquisition boundary supplies
one immutable `git_snapshot` Source, complete commit/tree identity, and in-memory repository-relative
file bytes. The adapter neither invokes Git nor reads a local checkout, performs network requests,
accepts a token, or writes an object directly; the existing Phase 3 ingestion service remains the
only private R2/S3 publication authority. A future acquisition worker must separately define public
HTTPS, Credential Vault, repository access, and Git diff selection. It may use no-change and
changed-commit outcomes from this adapter, but cannot infer any broader access from it.

Only full compatible SHA-1/SHA-256 commit and tree identities are accepted. The sanitized artifact
contains the accepted UTF-8 repository text plus immutable commit/tree identity, not excluded file
bytes. Paths with traversal, absolute/separator abuse, controls, `.git`, `.env*`, common
credential/private-key names or suffixes, and approved dependency/build/cache directories are
discarded before an artifact, document, Evidence Unit, job metadata, or error can contain them.
Binary/undecodable files remain a later asset-ingestion concern. Python source preserves top-level
AST classes/functions and imports with source lines; other text currently preserves a whole-file
block. This is deterministic structure, not an LLM code summary.

Git current-version visibility is explicit: publishing or deduplicating a Git snapshot atomically
marks other currently available Versions of the same Source `superseded`, while retaining their
artifacts, canonical content, Evidence, and derived index rows for audit and future reactivation.
Query providers already require `available` Evidence and Source Versions, so a current-code query
cannot select a superseded Git revision. Re-seeing a retained immutable commit reactivates it and
supersedes the formerly current Git Version. This transition is unavailable to generic/manual/
document Sources, whose historical visibility behavior remains unchanged.

### Websites

Generic websites use canonical URL detection, main-content extraction, sitemap/link discovery, deduplication, and conditional requests where available. Specialized adapters should preserve revision/category/navigation/thread semantics instead of scraping rendered text only.

### Phase 9a external-response boundary

The first continuously maintained external Source is not an unrestricted web client. A
worker/library-only `website_public_https` synchronizer accepts an injected, separately approved
fetcher and one exact configured public HTTPS locator. It has no default HTTP client, public sync
route, scheduler, Character-triggered live lookup, redirect traversal, credential, crawl, or
browser authority. This distinction is intentional: `PublicUrlGuard` remains a useful public-host
preflight, but does not by itself establish an approved pinned-DNS worker egress transport.

The first contract accepts only canonical HTTPS pages with no credentials, query, fragment, or
alternate port. It can issue ETag/Last-Modified conditional headers from a one-per-Source derived
sync-state record. A valid bounded text/HTML response deterministically becomes an existing private
source snapshot; 304 and same-content 200 outcomes create no new artifact/version. Source-visible
`last_checked_at`/`last_changed_at` remain timestamps, while the derived record contains only
validated single-line validators and bounded safe outcome/error codes. An invalid validator fails
before the private artifact or Source Version can be published. Raw response/error detail,
credentials, and arbitrary configuration values cannot be recorded there. HTML/text extraction is
deterministic; source-native MediaWiki/feed/API parsing and actual egress policy remain Phase 9b
work.

### Phase 9b-1 pinned transport and Atom boundary

The approved automatic worker is opt-in per Source and is configured only by Super Admin. Its
schedule defaults disabled, has a 15-minute minimum cadence, durable leases/retries, and a global
per-host cooldown. The worker resolves a canonical public hostname once, rejects the request if
any returned address is non-global, then dials one literal address while retaining the original
hostname for HTTP Host and verified TLS SNI/certificate validation. It does not use proxy
configuration, redirects, credentials, Tool Runtime, browser runtime, or a Character request.

`atom_public_https` is the first source-native adapter. It accepts bounded Atom 1.0 XML using
`defusedxml`, rejects DTD/entity declarations, and preserves only bounded entry evidence and safe
link provenance. It never follows feed or entry links.

### Phase 9b-2 Atom entry identity and selective invalidation

Each Atom document locator (`atom:<feed locator>#<entry-id hash>`) is a stable source-local entry
identity. A mutable, derived current-entry map points that identity at its retained current Evidence
Unit; it never replaces an immutable Source Version, canonical document, or Evidence Unit. Its
entry fingerprint includes retained text, title, and canonical metadata, so a changed safe link or
title is an entry change rather than stale provenance hidden behind old retrieval text.

A later Atom snapshot reuses an unchanged entry's prior Evidence and retrieval row, remaps only
new or materially changed entries, and marks disappeared entries removed. It deletes derived
retrieval rows only for replaced/removed Evidence. Candidate selection and source-overview
projections fail closed to the available current-entry map, while a projection dependency keeps the
actual historical Source Version/hash of each retained Evidence. A byte-order/format-only Atom
snapshot advances map observation but creates no index/projection invalidation and does not rebuild
the existing projection. This is Atom-specific; generic Source snapshots retain whole-source
invalidation semantics.

### Phase 9c Site Collection boundary

`website_collection_public_https` is a separate, opt-in Source type for a bounded public site
collection. Its configured root is an exact canonical public HTTPS URL. A scheduled worker uses
the existing pinned transport and first attempts the same-origin conventional sitemap. It accepts
bounded `urlset` and nested `sitemapindex` manifests only after DTD/entity rejection, type/size
checks, canonical URL validation, and same-origin admission. A missing root sitemap falls back to
at most 50 direct HTML links; the default collector never recursively crawls HTML, follows a
cross-origin page URL, invokes a browser, or accepts credentials.

A Super Admin may separately approve a `browser` rendered-collection recipe for a public
client-rendered site that has no admissible sitemap or useful static links. Analysis fetches the
root through the pinned transport and returns only bounded hostnames declared in public
`preconnect` or `dns-prefetch` markup. Saving the recipe rechecks that every approved external
hostname was observed; registration and analysis alone do not authorize rendered sync. The worker
then creates a one-use, cookie-free browser context with service workers and downloads disabled,
permits HTTPS requests only to the root host and the exact approved host set, and admits the
post-render, same-origin page DOM. It may additionally preserve at most eight successful public
`GET` XHR/fetch JSON responses from those approved hosts (128 KiB each and 512 KiB total), after
normalizing their JSON and without retaining request URLs, query values, headers, or credentials.
Those bytes are appended only to the private root-page artifact. Within the already approved page
budget, the worker may also discover root-relative or absolute HTTPS strings from generic
URL-valued JSON fields (`href`, `url`, `uri`, `link`, or path variants). Each candidate must still
pass canonical no-query/no-fragment validation and same-origin admission before it becomes a crawl
locator. The worker traverses this bounded DOM/JSON same-origin graph (at most 100 pages and depth
3), and stores its artifact privately with `rendered_browser` acquisition provenance. Rendered
runs do not collect images, reuse browser tool sessions, transmit credentials, or relax
corpus/Character access policy.

The private immutable artifact contains the approved raw page bytes. Each page creates exactly one
canonical document/Evidence Unit, whose canonical page locator is also a stable current-entry key.
Per-page discovery provenance, ETag/Last-Modified validators, content digest, and an incrementing
discovery generation are derived state, never raw content. Changed pages publish delta snapshots;
page `304` responses preserve their current Evidence without a new Source Version. Only a fully
parsed manifest plus successful page pass may mark entries absent from that generation as removed,
so a failed/partial run cannot retract prior evidence. Indexes and source-overview projections read
only available current entries.

The sitemap cap is 20 XML documents and 1,000 page locators. Robots/terms enforcement,
MediaWiki/Docusaurus/GitBook source-native adapters, browser interaction, visual matching, and
license workflows remain explicit later phases rather than implicit crawler authority.

Super Admin operational state may expose a current, redaction-safe Site Collection sync summary:
last completed generation plus aggregate available, removed, checked, and failed page counts. It
contains no page locators, validators, raw response details, artifacts, or credentials.

The scheduler also retains a bounded, source-scoped journal of completed automatic checks so an
operator can diagnose a changed, unchanged, or failed collection pass. A journal entry carries
only start/completion time, safe outcome/error code, and aggregate discovered/changed/unchanged/
failed/removed page and admitted-image counts. It never carries page locators, validators, raw
responses, artifact/object identifiers, hashes, headers, credentials, or provider payloads. This
is derived operational state only: it cannot authorize egress, change collection current state, or
influence retrieval. Entries expire through a best-effort hourly TTL worker; the default retention
is seven days and deployments may set `CHARACTER_RELAY_KNOWLEDGE_EXTERNAL_SYNC_REPORT_RETENTION_DAYS`
between one and ninety days.

### Corpus visual references

An approved `CanonicalVisualReference` is corpus-bound and links one canonical entity to the
specific Evidence Unit and private Asset that justify the reference. It is revocable and never
reuses a server-scoped runtime `EntityV3` as a global identity catalogue. Discord runtime can name
an identity only after the server has access to the corpus and the Character has explicit corpus
admission. The current resolver confirms an exact private-asset SHA-256 match, or preserves an
author's explicit caption as text context; it returns unresolved for lookalikes and has no
face/character-similarity claim by default. Pairwise matching is enabled only for a
`fictional_character` entity when a Super Admin separately marks the approved reference for
external comparison. The Runtime sends a current Discord image plus at most five approved private
reference images to that Character's already configured Media Understanding provider. Canonical
names remain local: the model receives positional images only and returns an index plus confidence;
provider failure, malformed output, unsupported capability, an out-of-range index, or confidence
below 0.96 resolves as unknown. This flow is never used for real-person identification.

Site Collection may acquire a bounded page-local raster asset only through the worker's pinned,
same-origin transport. The generic adapter accepts explicit `img[src]` only, rejects query-bearing,
credential-bearing, SVG and non-raster content, validates both content type and magic bytes, and
stores the admitted bytes as a separate private content-addressed artifact. It creates Asset and
asset-Evidence provenance atomically with the Source Version, without treating a remote image URL
as permanent Knowledge or an automatic character identity.

Global administrators can list this provenance-safe image candidate inventory, create/list a
corpus-local canonical entity, and then approve/revoke the visual reference. These administrative
responses contain the page/document, Asset and Evidence identities plus retained caption only;
they never disclose private object keys, artifact hashes, or bytes. The portal redesign and an
image preview/dedicated approval UI remain separate product work.

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

### Phase 5 retrieval contract

The first implementation resolves a server's accessible corpus IDs solely through
`KnowledgeFabricRepository.list_effective_corpora(server_scope_id)` before any sparse, dense, or
entity/graph channel runs. An unknown scope creates no state and returns no candidate. All returned
hits retain Evidence Unit/source-version locator provenance; the engine does not consult legacy RAG
as a second authority.

PostgreSQL uses `simple` FTS and a cosine HNSW expression index for the existing
`intfloat/multilingual-e5-small` 384-dimension embedding profile. Other persisted embedding
profiles remain queryable by exact vector distance until an explicit rebuild/index decision. SQLite
has a deterministic test fallback rather than a production-scale retrieval claim.

`overview`, `exact`, `relational`, `current`, and `code` are the initial modes. `exact` and `code`
are sparse-only source-evidence paths; `code` gains symbol/dependency retrieval only with a later
source adapter. Interpretation validity is half-open (`valid_from <= as_of < valid_to`). Because
`freshness_policy_json` has no approved schema, `current` reports local evidence with
`insufficient` freshness and does not call a Web/API fallback.

The target `override` policy remains supported by the architecture, but Phase 5 does not infer a
record-level shadowing key from names, embeddings, or assertion prose. `deny` remains an access
exclusion; `augment` and `override` remain recorded provenance/precedence metadata until an
explicit conflict-resolution contract is implemented.

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

The retired Knowledge Base/KB Wiki/Server Wiki v3 stores must not be restored, migrated, or reused.
New readable views are Fabric Projections only; “Wiki” is not a runtime compatibility boundary.

### Phase 7 delivered boundary

`KnowledgeProjection` is an additive Fabric-derived cache with an explicit corpus, typed subject,
source hash, stale state, and derived text. `KnowledgeProjectionDependency` records the exact
SourceVersion, Evidence Unit, source hash, and Evidence content hash used to materialize it. The
first implementation is a deterministic source overview: it is rebuilt lazily from source Evidence
when absent or stale, and a newly published SourceVersion invalidates views derived from any older
version of the same Source. Projection dependencies are deleted before their Evidence lifecycle
rows, so a Projection never becomes stranded provenance.

The current check is intentionally narrow: a view is reusable only when its `source_hash` equals
the newest SourceVersion hash and it is not marked stale. Exact-detail, quotation, and provenance
queries continue to return raw Evidence through `KnowledgeQueryEngine`; no Projection can satisfy
those modes on its own.

The Character-facing internal tool is `knowledge.search`, not a Server Wiki lookup. It preserves
the bounded `query`/`limit` contract and goes through the same fail-closed `KnowledgeContextBuilder`
and Character epistemic policy as normal turn context. Thus it returns no evidence for an unknown
scope, unavailable query, or denied Character, and it sends no raw evidence locator to the model.
The legacy Wiki persistence/API/Portal compatibility surface was directly retired in Phase 11c;
it is not a backend for this tool and has no migration or archive path.

## Character runtime integration

`CharacterTurnContextV3Service` depends on one `KnowledgeQueryEngine`, not separately on raw RAG
or Server Wiki repositories.

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

### Phase 6 Character Context cutover

The implemented Character path resolves an existing Fabric Server Scope by the verified
`(platform, connection_id, guild_id)` tuple without calling `ensure_server_scope()`. Only after a
Character has been selected does it issue one bounded `overview` query and turn admitted results
into the single `KNOWLEDGE EVIDENCE` Context section. The old RAG and Server Wiki prompt paths are
not a second authority in either direct Character turns or Smart Participation candidate context.

Character admission is deliberately fail-closed in this phase: the runtime has a
`CharacterEpistemicPolicy` boundary, but its default denies every Evidence Unit. Phase 10 must
replace that default with the persisted authored corpus/domain, timeline, spoiler, perspective,
and override policy; server access alone is never inferred as Character knowledge.

Prompted Evidence is marked as untrusted reference data, delimited from Runtime instructions, and
includes only Evidence Unit/source-version identifiers plus authority/freshness metadata. Raw
source locators are not sent to the prompt or ordinary trace. Unknown scopes and non-blocking
query failures produce no knowledge evidence while keeping the normal Character turn available.

This cutover does not add a live Web/API fallback. The current Query request has no approved
freshness threshold, importance input, deployment tool authorization, user consent, registered
source match, or typed turn-local external evidence result. Discovery remains candidate-only and
is not a synchronous fact source. Phase 9 owns source adapters and adaptive freshness; any future
external lookup must use the existing deployment Tool Runtime authorization rather than call a
browser or provider directly.

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

Account deletion/local-workspace claim code owns current Fabric corpus/source/access/object rows.
The one-way cutover ledger owns retirement of the deleted legacy tables and vectors.

Deletion/claim policy must distinguish:

- system-global corpora, which are not deleted with an ordinary user;
- user/workspace-owned private corpora;
- server-local corpora;
- grants from a user/server to a system corpus;
- object-storage artifacts;
- derived vectors/projections/job records.

Derived indexes/projections must never survive as cross-owner data leaks after source/ownership deletion.

## Portal/Admin target

The direct document-CRUD panel was removed in the hard cutover. The current management surface is
Corpus/Source-first.

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

The following are retired pre-Fabric concepts, not implementation or compatibility contracts:

- `KnowledgeBaseRecord` as the primary corpus abstraction;
- manually pasted plain-text-only Knowledge Documents as the primary ingestion experience;
- fixed 900-character chunk identity as durable knowledge;
- bounded SQL scan then in-process dense scoring as large-corpus retrieval;
- `WikiAwareKnowledgeRepository` as a separate retrieval universe;
- `ServerWikiV3Repository` as a Character-facing knowledge subsystem;
- separate `knowledge_hits` and `wiki_hits` in final Context Resolver semantics;
- `wiki.lookup` as a permanent Character tool name;
- SQLite as the intended production database for the new large-corpus system.

Phase 11c removed these concepts directly. Do not reintroduce them, including as an import,
archive, or fallback path.

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
4. corpus-bound canonical entities, assertions/events, and an Evidence Graph bridge;
5. PostgreSQL FTS + pgvector index layer and Knowledge Query Engine, accessible-space resolution,
   fusion/rerank/freshness;
6. Character/Context integration;
7. unified Projection Layer;
8. ingestion adapters, beginning with Git and structured document import before broad generic Web crawling;
9. Character epistemic timeline/spoiler/perspective controls;
10. Portal/Admin operational UX, lifecycle hardening, observability and scale validation;
11. direct retirement of the old RAG/Wiki data, APIs, runtime state, and Portal surfaces.

A phase may refine field names or split repositories, but it must not violate the authority, access, epistemic, provenance, and derived-projection rules in this contract without first updating this contract and the active plan.
