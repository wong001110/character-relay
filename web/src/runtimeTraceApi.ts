export type RuntimeGraphName = "condition_watch" | "character_turn" | "social_turn";
export type RuntimeTraceStatus = "running" | "completed" | "failed";

export interface RuntimeTraceSummary {
  graph_run_id: string;
  trace_id: string;
  operation_id: string;
  graph_name: RuntimeGraphName;
  status: RuntimeTraceStatus;
  owner_id: string;
  deployment_id: string;
  character_card_id: string;
  last_node: string;
  event_count: number;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface RuntimeTraceEvent {
  id: number;
  node_name: string;
  node_kind: string;
  status: string;
  changed_keys: string[];
  metadata: Array<[string, string]>;
  error: string;
  created_at: string;
}

export interface RuntimeTraceView extends RuntimeTraceSummary {
  events: RuntimeTraceEvent[];
}

export interface RuntimeTracePage {
  items: RuntimeTraceSummary[];
  next_cursor: string | null;
  has_more: boolean;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve the raw response below.
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
  return response.json() as Promise<T>;
}

export const runtimeTraceApi = {
  access: (signal?: AbortSignal) =>
    request<{ allowed: boolean }>("/api/admin/runtime-traces/access", { signal }),
  list: (options: {
    limit?: number;
    graphName?: RuntimeGraphName | "all";
    status?: RuntimeTraceStatus | "all";
    ownerId?: string;
    operationId?: string;
    cursor?: string | null;
    signal?: AbortSignal;
  } = {}) => {
    const query = new URLSearchParams();
    query.set("limit", String(options.limit ?? 50));
    if (options.graphName && options.graphName !== "all") {
      query.set("graph_name", options.graphName);
    }
    if (options.status && options.status !== "all") {
      query.set("status", options.status);
    }
    if (options.ownerId?.trim()) query.set("owner_id", options.ownerId.trim());
    if (options.operationId?.trim()) {
      query.set("operation_id", options.operationId.trim());
    }
    if (options.cursor) query.set("cursor", options.cursor);
    return request<RuntimeTracePage>(
      `/api/admin/runtime-traces/page?${query.toString()}`,
      { signal: options.signal }
    );
  },
  detail: (graphRunId: string, signal?: AbortSignal) =>
    request<RuntimeTraceView>(
      `/api/admin/runtime-traces/${encodeURIComponent(graphRunId)}`,
      { signal }
    ),
  clear: (ownerId?: string) => {
    const selected = ownerId?.trim() ?? "";
    const suffix = selected ? `?owner_id=${encodeURIComponent(selected)}` : "";
    return request<{ deleted_count: number }>(`/api/admin/runtime-traces${suffix}`, {
      method: "DELETE"
    });
  }
};
