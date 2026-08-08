export type KnowledgeScopeType = "global" | "server" | "channel";

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  scope_type: KnowledgeScopeType;
  connection_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  character_card_id: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseWrite {
  name: string;
  description: string;
  scope_type: KnowledgeScopeType;
  connection_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  character_card_id: string;
  enabled: boolean;
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  title: string;
  source_type: string;
  content_sha256: string;
  chunk_count: number;
  content_chars: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeRetrieveHit {
  knowledge_base_id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  content: string;
  score: number;
  signals: Record<string, number>;
}

export interface KnowledgeRetrieveResult {
  eligible_base_count: number;
  candidate_chunk_count: number;
  hits: KnowledgeRetrieveHit[];
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve raw response below.
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

export const knowledgeApi = {
  listBases: () => request<KnowledgeBase[]>("/api/knowledge/bases"),
  createBase: (payload: KnowledgeBaseWrite) =>
    request<KnowledgeBase>("/api/knowledge/bases", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateBase: (baseId: string, payload: KnowledgeBaseWrite) =>
    request<KnowledgeBase>(`/api/knowledge/bases/${encodeURIComponent(baseId)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteBase: (baseId: string) =>
    request<void>(`/api/knowledge/bases/${encodeURIComponent(baseId)}`, {
      method: "DELETE"
    }),
  listDocuments: (baseId: string) =>
    request<KnowledgeDocument[]>(
      `/api/knowledge/bases/${encodeURIComponent(baseId)}/documents`
    ),
  createDocument: (baseId: string, payload: { title: string; content: string }) =>
    request<KnowledgeDocument>(
      `/api/knowledge/bases/${encodeURIComponent(baseId)}/documents`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  deleteDocument: (documentId: string) =>
    request<void>(`/api/knowledge/documents/${encodeURIComponent(documentId)}`, {
      method: "DELETE"
    }),
  retrieve: (payload: {
    query: string;
    connection_id: string;
    guild_id: string;
    channel_id: string;
    thread_id: string;
    character_card_id: string;
    top_k?: number;
  }) =>
    request<KnowledgeRetrieveResult>("/api/knowledge/retrieve", {
      method: "POST",
      body: JSON.stringify({ top_k: 4, ...payload })
    })
};
