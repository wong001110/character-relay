export type KeyGroupCapability = "character" | "media" | "image_generation";

export const AUTO_FREE_ANIME_MODEL = "auto:openrouter-free-anime";

export interface ProviderKeyGroup {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  default_models: Record<string, string>;
  credential_configured: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderKeyGroupCreate {
  name: string;
  provider: string;
  base_url: string;
  api_key: string;
  default_models: Partial<Record<KeyGroupCapability, string>>;
}

export interface ProviderKeyGroupUpdate {
  name: string;
  provider: string;
  base_url: string;
  api_key?: string | null;
  default_models: Partial<Record<KeyGroupCapability, string>>;
}

export interface ImageModelScoutCandidate {
  model_id: string;
  name: string;
  description: string;
  style_score: number;
  style_matches: string[];
  free_endpoint_count: number;
  provider_names: string[];
}

export interface ImageModelScoutResult {
  selected_model: string | null;
  candidates: ImageModelScoutCandidate[];
  checked_at: string;
  total_image_models: number;
  inspected_models: number;
  from_cache: boolean;
  cache_ttl_seconds: number;
}

export interface KeyGroupBulkApplyResult {
  applied: number;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Fall back to the raw response below.
  }
  return raw || `Request failed with ${response.status}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const keyGroupApi = {
  list: () => request<ProviderKeyGroup[]>("/api/account/key-groups"),
  create: (payload: ProviderKeyGroupCreate) =>
    request<ProviderKeyGroup>("/api/account/key-groups", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  update: (groupId: string, payload: ProviderKeyGroupUpdate) =>
    request<ProviderKeyGroup>(`/api/account/key-groups/${groupId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  remove: (groupId: string) =>
    request<void>(`/api/account/key-groups/${groupId}`, { method: "DELETE" }),
  scoutImageModels: (groupId: string, refresh = false) =>
    request<ImageModelScoutResult>(
      `/api/account/key-groups/${groupId}/image-model-scout?refresh=${refresh ? "true" : "false"}`
    ),
  bulkApply: (
    groupId: string,
    payload: {
      character_card_ids: string[];
      capabilities: KeyGroupCapability[];
      model_overrides?: Partial<Record<KeyGroupCapability, string>>;
    }
  ) =>
    request<KeyGroupBulkApplyResult>(`/api/account/key-groups/${groupId}/apply`, {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
