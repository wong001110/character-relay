export interface KnowledgeFabricScope {
  id: string;
  platform: string;
  connection_id: string;
  workspace_id: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeFabricCorpus {
  id: string;
  name: string;
  description: string;
  owner_type: string;
  owner_id: string;
  visibility: string;
  default_authority_profile: string;
  status: string;
  overlay_mode: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeFabricAccessGrant {
  corpus_id: string;
  grantee_type: string;
  grantee_id: string;
  enabled: boolean;
  access_mode: string;
  updated_at: string;
}

export interface KnowledgeFabricGlobalCorpusAccess {
  corpus_id: string;
  enabled: boolean;
  overlay_mode: KnowledgeFabricOverlayMode;
}

export interface KnowledgeFabricSource {
  id: string;
  corpus_id: string;
  source_type: string;
  locator: string;
  parser_profile: Record<string, string>;
  sync_policy: Record<string, string>;
  freshness_policy: Record<string, string>;
  authority_profile: string;
  enabled: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeFabricCharacterCorpusPolicy {
  deployment_id: string;
  character_card_id: string;
  corpus_id: string;
  effect: "allow" | "deny";
  updated_at: string;
}

export type KnowledgeFabricOverlayMode = "inherit" | "augment" | "override" | "deny";

export interface KnowledgeFabricSourceCreate {
  source_type: string;
  locator: string;
  authority_profile: string;
}

export interface KnowledgeFabricExternalSourceSchedule {
  source_id: string;
  enabled: boolean;
  interval_seconds: number;
  next_run_at: string | null;
  last_error_code: string | null;
  updated_at: string;
}

export interface KnowledgeFabricExternalSourceSyncState {
  source_id: string;
  last_outcome: string;
  last_error_code: string | null;
  updated_at: string;
}

export interface KnowledgeFabricDerivedWorkSummary {
  pending: number;
  running: number;
  failed: number;
}

/** Aggregate Site Collection progress only; page URLs, validators, and artifacts stay private. */
export interface KnowledgeFabricSiteCollectionSyncSummary {
  source_id: string;
  last_completed_at: string | null;
  available_page_count: number;
  removed_page_count: number;
  checked_page_count: number;
  failed_page_count: number;
}

/** Approval metadata only; private image bytes and object locations never reach the portal. */
export interface KnowledgeFabricImageAssetCandidate {
  source_id: string;
  source_version_id: string;
  document_id: string;
  document_locator: string;
  asset_id: string;
  evidence_unit_id: string;
  asset_type: string;
  caption: string;
}

export interface KnowledgeFabricCanonicalEntity {
  id: string;
  corpus_id: string;
  entity_type: string;
  canonical_name: string;
  aliases: string[];
  status: string;
  metadata: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeFabricVisualReference {
  id: string;
  corpus_id: string;
  canonical_entity_id: string;
  evidence_unit_id: string;
  asset_id: string;
  descriptor: Record<string, string>;
  comparison_authorized: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

/** Safe operational state only: it intentionally has no locator, profiles, or artifacts. */
export interface KnowledgeFabricOperationalSource {
  id: string;
  corpus_id: string;
  source_type: string;
  authority_profile: string;
  enabled: boolean;
  status: string;
  last_checked_at: string | null;
  last_changed_at: string | null;
  created_at: string;
  updated_at: string;
  external_sync: KnowledgeFabricExternalSourceSyncState | null;
  external_schedule: KnowledgeFabricExternalSourceSchedule | null;
  site_collection_summary: KnowledgeFabricSiteCollectionSyncSummary | null;
  sync_run_reports: KnowledgeFabricExternalSyncRunReport[];
  derived_work: KnowledgeFabricDerivedWorkSummary;
}

/** A short-lived, redacted record of one completed automatic source check. */
export interface KnowledgeFabricExternalSyncRunReport {
  id: string;
  source_id: string;
  outcome: string;
  error_code: string | null;
  started_at: string;
  completed_at: string;
  discovered_page_count: number;
  changed_page_count: number;
  unchanged_page_count: number;
  failed_page_count: number;
  removed_page_count: number;
  admitted_image_count: number;
}

export interface KnowledgeFabricQueryInspectorHit {
  evidence_unit_id: string;
  corpus_id: string;
  source_version_id: string;
  evidence_locator: string;
  document_title: string;
  text_content: string;
  authority_profile: string;
  channels: string[];
}

export interface KnowledgeFabricQueryInspectorResult {
  mode: string;
  accessible_corpus_count: number;
  freshness_status: string;
  hits: KnowledgeFabricQueryInspectorHit[];
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const payload = JSON.parse(raw) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
  } catch {
    // Preserve the server's raw message below.
  }
  return raw || `Request failed with ${response.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/knowledge-fabric${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers }
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function scopePath(scopeId: string): string {
  return `/server-scopes/${encodeURIComponent(scopeId)}`;
}

export const knowledgeFabricApi = {
  listScopes: () => request<KnowledgeFabricScope[]>("/server-scopes"),
  listGlobalCorpora: () => request<KnowledgeFabricCorpus[]>("/admin/corpora"),
  createGlobalCorpus: (payload: {
    name: string;
    description: string;
    default_authority_profile: string;
  }) => request<KnowledgeFabricCorpus>("/admin/corpora", {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  listGlobalOperationalSources: (corpusId: string) =>
    request<KnowledgeFabricOperationalSource[]>(
      `/admin/corpora/${encodeURIComponent(corpusId)}/operational-sources`
    ),
  createGlobalSource: (corpusId: string, payload: KnowledgeFabricSourceCreate) =>
    request<KnowledgeFabricSource>(`/admin/corpora/${encodeURIComponent(corpusId)}/sources`, {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        parser_profile: {},
        sync_policy: {},
        freshness_policy: {}
      })
    }),
  listGlobalCanonicalEntities: (corpusId: string) =>
    request<KnowledgeFabricCanonicalEntity[]>(
      `/admin/corpora/${encodeURIComponent(corpusId)}/canonical-entities`
    ),
  createGlobalCanonicalEntity: (
    corpusId: string,
    payload: {
      entity_type: string;
      canonical_name: string;
      aliases: string[];
      metadata: Record<string, string>;
    }
  ) =>
    request<KnowledgeFabricCanonicalEntity>(
      `/admin/corpora/${encodeURIComponent(corpusId)}/canonical-entities`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  listGlobalImageAssetCandidates: (corpusId: string) =>
    request<KnowledgeFabricImageAssetCandidate[]>(
      `/admin/corpora/${encodeURIComponent(corpusId)}/image-assets`
    ),
  listGlobalVisualReferences: (corpusId: string) =>
    request<KnowledgeFabricVisualReference[]>(
      `/admin/corpora/${encodeURIComponent(corpusId)}/visual-references`
    ),
  createGlobalVisualReference: (
    corpusId: string,
    payload: {
      canonical_entity_id: string;
      evidence_unit_id: string;
      asset_id: string;
      descriptor: Record<string, string>;
      comparison_authorized: boolean;
    }
  ) =>
    request<KnowledgeFabricVisualReference>(
      `/admin/corpora/${encodeURIComponent(corpusId)}/visual-references`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  revokeGlobalVisualReference: (corpusId: string, referenceId: string) =>
    request<void>(
      `/admin/corpora/${encodeURIComponent(corpusId)}/visual-references/${encodeURIComponent(referenceId)}`,
      { method: "DELETE" }
    ),
  configureExternalSourceSchedule: (
    sourceId: string,
    payload: { enabled: boolean; interval_seconds: number }
  ) =>
    request<KnowledgeFabricExternalSourceSchedule>(
      `/admin/sources/${encodeURIComponent(sourceId)}/external-sync-schedule`,
      { method: "PUT", body: JSON.stringify(payload) }
    ),
  retryFailedDerivedWork: (sourceId: string) =>
    request<KnowledgeFabricDerivedWorkSummary>(
      `/admin/sources/${encodeURIComponent(sourceId)}/derived-work/retry`,
      { method: "POST" }
    ),
  listCorpora: (scopeId: string) =>
    request<KnowledgeFabricCorpus[]>(`${scopePath(scopeId)}/corpora`),
  listAvailableGlobal: (scopeId: string) =>
    request<KnowledgeFabricCorpus[]>(`${scopePath(scopeId)}/available-global-corpora`),
  listGlobalAccess: (scopeId: string) =>
    request<KnowledgeFabricGlobalCorpusAccess[]>(`${scopePath(scopeId)}/global-corpora/access`),
  grantGlobal: (scopeId: string, corpusId: string, enabled: boolean) =>
    request<KnowledgeFabricAccessGrant>(
      `${scopePath(scopeId)}/global-corpora/${encodeURIComponent(corpusId)}/grant`,
      { method: "PUT", body: JSON.stringify({ enabled }) }
    ),
  setOverlay: (scopeId: string, corpusId: string, mode: KnowledgeFabricOverlayMode) =>
    request<void>(
      `${scopePath(scopeId)}/global-corpora/${encodeURIComponent(corpusId)}/overlay`,
      { method: "PUT", body: JSON.stringify({ mode }) }
    ),
  createLocalCorpus: (
    scopeId: string,
    payload: { name: string; description: string; default_authority_profile: string }
  ) => request<KnowledgeFabricCorpus>(`${scopePath(scopeId)}/corpora`, {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  listLocalSources: (scopeId: string, corpusId: string) =>
    request<KnowledgeFabricSource[]>(
      `${scopePath(scopeId)}/corpora/${encodeURIComponent(corpusId)}/sources`
    ),
  createLocalSource: (
    scopeId: string,
    corpusId: string,
    payload: KnowledgeFabricSourceCreate
  ) => request<KnowledgeFabricSource>(
    `${scopePath(scopeId)}/corpora/${encodeURIComponent(corpusId)}/sources`,
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        parser_profile: {},
        sync_policy: {},
        freshness_policy: {}
      })
    }
  ),
  listCharacterPolicies: (scopeId: string) =>
    request<KnowledgeFabricCharacterCorpusPolicy[]>(
      `${scopePath(scopeId)}/character-corpus-policies`
    ),
  inspectQuery: (
    scopeId: string,
    payload: { query: string; mode: string; as_of?: string }
  ) =>
    request<KnowledgeFabricQueryInspectorResult>(`${scopePath(scopeId)}/query-inspector`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  setCharacterPolicy: (
    scopeId: string,
    deploymentId: string,
    corpusId: string,
    effect: "allow" | "deny"
  ) =>
    request<KnowledgeFabricCharacterCorpusPolicy>(
      `${scopePath(scopeId)}/deployments/${encodeURIComponent(deploymentId)}/corpora/${encodeURIComponent(corpusId)}/epistemic-policy`,
      { method: "PUT", body: JSON.stringify({ effect }) }
    )
};
