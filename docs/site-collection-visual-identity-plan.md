# Site Collection and Visual Identity Delivery Plan

Branch: `codex/site-collection-visual-identity`
Base: `origin/main` at `b30ddc3c421379d8a0b2a94da79e9bb7a8c47362`

## Evidence map and invariants

- External source authority: `knowledge_fabric_external_policy.py`, the pinned fetcher, scheduler,
  external schedule/sync repositories, and their website/Atom tests.
- Immutable content/current-page authority: `knowledge_fabric_ingestion.py`,
  `persistence/knowledge_fabric_content_repository.py`, index/projection repositories, and Atom
  current-entry tests.
- Canonical identity and media authority: Fabric canonical entity/evidence records; scoped
  `EntityV3`, `entity_grounding_v3.py`, `live_media.py`, and conversation-media tests.
- Canonical contracts: `docs/knowledge-fabric-architecture.md` and
  `docs/media-awareness-and-generation-roadmap.md`. The Global Library UI reference is deliberately
  excluded because its redesign remains paused by product direction.

The work must preserve default-disabled Super Admin scheduling; pinned, public HTTPS only egress;
immutable artifacts/versions; server authorization before Character epistemic policy; no raw user
attachment retention; and `unresolved` for weak visual matches. A Source registration never grants
runtime crawling or Character knowledge.

## Route

1. **Delivered in this phase — bounded Site Collection.** Add a generic public site source type
   with a root page plus an upper-bounded direct, same-origin HTML link set. Reuse current-entry
   semantics so changed/new/removed pages are reflected without treating historical source evidence
   as current. The first slice deliberately has no recursive crawling, sitemap traversal, robots
   enforcement, per-page validators, or media fetching.
2. **Delivered in this phase — page-level collection state.** Persist per-page
   validators/discovery provenance and discovery generations; accept bounded same-origin sitemap
   manifests (including bounded nested indexes); publish changed pages as current-entry deltas;
   remove prior current entries only after a complete successful generation. Source-native adapters
   (MediaWiki, Docusaurus, GitBook) still require their own policies and tests.
3. **Delivered foundation — evidence-backed visual references.** Corpus-scoped
   `CanonicalVisualReference` records bind canonical entities to approved source Evidence and
   private Assets; references are revocable. This does not reuse server-scoped `EntityV3` as a
   global character catalogue.
4. **Delivered guarded Discord resolution.** Resolve only after effective-corpus and authored
   Character policy pass. The current runtime confirms only an exact private-asset SHA-256 match,
   or reports an explicit caption as text context. Similar-looking images remain unresolved; no
   model-only candidate is named in the prompt or creates a runtime entity.
5. **Delivered onboarding API — approval inventory.** Global administrators can list safe image
   candidate provenance, create/list corpus-local canonical entities, then approve/revoke a
   reference. This stays API-only while the Global Library redesign is paused; it returns no
   private object keys, hashes, URLs, or bytes.
6. **Delivered authorized pairwise comparison.** A Super Admin can explicitly authorize an
   approved `fictional_character` reference for external comparison. Only then may the Runtime
   send the current Discord image plus no more than five anonymous private references to the
   Character's configured Media Understanding provider. The model receives no canonical name and
   must return an index/confidence; low-confidence, unavailable, malformed, or out-of-range
   results remain unresolved. It is not available for real-person entities.
7. **Separate product phase — UI.** Replace the formal Global Library experience and expose a
   guided Site Collection flow only after the paused UI direction is re-authorized.

## Phase handoff

- Status: Site Collection discovery/current-entry, bounded image ingestion, and visual-reference
  onboarding API complete; visual similarity remains a subsequent capability.
- Deliberate omissions: no UI change, no visual similarity, no recursive HTML crawl, no
  cross-origin discovery, no robots/terms policy, and no source-native Wiki adapter.
- Evidence: `python -m ruff check` passed for the changed source/tests; `python -m compileall -q`
  passed for the three new Site Collection modules. Focused pytest gate passed 9 tests
  (`test_knowledge_fabric_website_collection.py` and external schedule); compatibility gate passed
  11 tests (website sync, Atom sync/current entries, and scheduler).
- Implementation commit: `02474e9` (`feat: add bounded website collection sync`).
- Mutation note: the configured Python `mutmut` scopes do not cover Site Collection yet. No score
  is claimed. Add this deterministic discovery/current-entry policy to a bounded runner scope before
  treating it as a protected mutation-tested surface.
- Page-state implementation: `knowledge_fabric_site_collection_repository.py`,
  `knowledge_fabric_website_sitemap_policy.py`, and delta current-entry mode in the content
  repository. The additive migration ledger revision is
  `knowledge-fabric-site-collection-state-v1`.
- Validation: targeted Ruff passed; Site Collection plus Website/Atom/current-entry/schedule
  regression batch passed after the page-state implementation. Mutation coverage is still pending
  runner configuration; no score is claimed.
- Next concrete action: select and authorize a real pairwise/multi-image media capability before
  expanding comparison candidate limits or model support; do not claim model-only matches as
  general character identity. The paused UI can later turn the existing API workflow into guided
  source/asset review.

## Image asset delivery

- Site Collection now admits only bounded same-origin raster `<img src>` candidates. Each response
  must be PNG/JPEG/GIF/WebP, pass matching byte-signature validation, and remain at or below 8 MiB.
  Rejected candidates do not fail a page's textual knowledge sync.
- Admitted image bytes are independently content-addressed private objects. Publication atomically
  binds each object to its page document, AssetReference, and image Evidence; the current-entry map
  deliberately excludes asset Evidence so a page still has one current text Evidence identity.
- Super Admin API provides create/list/revoke for global-corpus visual-reference approvals. It never
  returns object locations or raw bytes, and every approval/revocation is audited.
- Super Admin onboarding additionally lists private-image candidate provenance and creates/lists
  corpus-local canonical entities. The candidate response intentionally excludes private object
  storage identifiers and image bytes.
- `comparison_authorized` is false by default. It can only be set on a `fictional_character`
  reference, which is the explicit egress consent for a bounded private-reference comparison.

## Onboarding API phase handoff

- Evidence: `knowledge_fabric_content_repository.py`, the Fabric interpretation and visual
  reference repositories, `api/app.py`, `api/routes/knowledge_fabric.py`, their public schemas,
  and `test_knowledge_fabric_visual_reference_api.py`.
- Invariants: only a global administrator may enumerate or approve global-corpus assets; canonical
  entities remain corpus-local; approval still validates asset/Evidence/entity provenance; private
  object keys, hashes, and bytes never cross the API boundary; no UI change was made.
- Validation: scoped Ruff passed; strict mypy passed for 10 changed source files; `compileall`
  passed; Site Collection/image-policy/visual-reference/API/Discord-media regression batch passed
  33 tests; the two new private-asset publication/rollback tests passed. The wider 12-test Phase 3
  lifecycle module was collected but not recorded as a green gate because this Windows worktree's
  inherited pytest temp directories repeatedly stall its remaining old lifecycle cases.
- Implementation commit: current branch `HEAD` (`feat: add visual reference onboarding API`),
  amended to carry this handoff; its resolved hash is recorded in the delivery handoff.
- Next concrete action: retain the bounded pairwise capability unless a future product decision
  explicitly expands its candidate limit or provider support. The paused UI can later turn the
  existing API workflow into guided source/asset review.

## Authorized pairwise-comparison phase handoff

- Evidence: `knowledge_fabric_visual_reference_policy.py`,
  `knowledge_fabric_visual_identity.py`, the visual-reference repository, the OpenAI-compatible
  multimodal provider, `media_connector_runtime.py`, and their visual-reference/provider/runtime
  tests.
- Authorization and invariants: the approved use is limited to `fictional_character` references.
  A comparison-authorized reference is opt-in and revocable; at most five private reference images
  plus the current Discord image leave the service; canonical names, object keys, hashes, and
  reference bytes stay out of the provider request. The provider returns only an anonymous
  reference index and confidence. Any unavailable, malformed, out-of-range, or below-threshold
  result stays `unresolved`; no real-person comparison is available. Exact SHA/caption resolution
  remains the first path.
- Validation: scoped Ruff and strict mypy passed for 9 changed source modules; `compileall`
  passed. The consolidated Site Collection/image-policy/visual-reference/API/Discord-media/Phase 3
  regression batch passed 51 tests (with the existing TestClient deprecation warning).
- Mutation: the WSL-native configured Python scope mutated 5 files and 106 mutants: 101 killed,
  no timeout/tooling failures, and 5 reviewed equivalent survivors. The survivors predate this
  visual policy: two replace the unobserved `first_seen` value with `None`; one changes a missing
  score default by the same constant for every unique candidate; one uniformly doubles all fusion
  scores; and one raises a retry loop cap after the returned delay is already clamped to six hours.
  The new visual-reference policy has no surviving mutant. The runner is pinned to LF checkout so
  WSL Bash does not receive CRLF syntax.
- Implementation commit: current branch `HEAD` (`feat: add guarded fictional visual matching`).
- Deliberate omissions: no UI redesign, no real-person matching, no web-scale crawl expansion,
  no provider fallback beyond the configured compatible multimodal path, and no runtime promotion
  of a visual result into a canonical entity or Belief.
- Next concrete action: review and explicitly authorize the paused Global Library UI work before
  exposing the onboarding flow in the portal; keep this API-first workflow otherwise.

## Administration UI phase handoff

- Evidence: `web/src/KnowledgeFabricAdministrationPanel.tsx`,
  `web/src/knowledgeFabricApi.ts`, `web/src/settings-access.css`, and
  `web/src/knowledgeFabricApi.test.ts`.
- Delivered: the Super Admin Administration > Knowledge Fabric panel is now a focused three-step
  workspace: choose/create a global library, add a public Wiki/site using the recommended bounded
  `website_collection_public_https` source type, then review canonical fictional-character and
  visual-reference approvals. Source health and the opt-in schedule remain visible in the same
  context rather than as a separate technical form.
- Invariants: the Portal only renders existing redacted operational state; it does not promise an
  immediate sync, a page count, or a website preview. Image candidates expose only existing safe
  provenance metadata, never private bytes, object keys, hashes, or URLs. External image comparison
  remains opt-in, fictional-character-only, capped, and revocable; the consent language describes
  the already-approved egress boundary rather than broadening it. Server grants and Character
  epistemic policy remain in the Deployment Workspace.
- Validation: Portal TypeScript check and focused `knowledgeFabricApi.test.ts` passed; production
  Vite build passed. The current desktop session had no callable browser automation surface, so no
  browser screenshot claim is made.
- Deliberate omissions: this is not a global Portal redesign; Dashboard, Server Knowledge,
  deployment scope, and private image previews remain unchanged. A future approved reference can
  refine the wider Global Library visual direction without changing these API/security boundaries.
- Implementation commit: current branch `HEAD` (`feat: guide knowledge fabric administration`).
