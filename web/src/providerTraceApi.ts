export type ProviderTraceStatus = "pending" | "succeeded" | "error";
export type ProviderTraceCategory = "tool_calling" | "character_turn" | "model_call";

export interface ProviderTracePage {
  items: ProviderTraceView[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ProviderTraceView {
  trace_id: string;
  status: ProviderTraceStatus;
  category: ProviderTraceCategory;
  tool_names: string[];
  trace_mode: string;
  endpoint: string;
  request_model: string;
  response_model: string;
  request: Record<string, unknown>;
  retries: Array<Record<string, unknown>>;
  response: Record<string, unknown>;
  error: Record<string, unknown>;
  status_code: number | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
  updated_at: string;
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

export const providerTraceApi = {
  list: (options: {
    limit?: number;
    status?: ProviderTraceStatus | "all";
    category?: ProviderTraceCategory | "all";
    model?: string;
    traceId?: string;
    cursor?: string | null;
  } = {}) => {
    const query = new URLSearchParams();
    query.set("limit", String(options.limit ?? 100));
    if (options.status && options.status !== "all") {
      query.set("status", options.status);
    }
    if (options.category && options.category !== "all") {
      query.set("category", options.category);
    }
    if (options.model?.trim()) query.set("model", options.model.trim());
    if (options.traceId?.trim()) query.set("trace_id", options.traceId.trim());
    if (options.cursor) query.set("cursor", options.cursor);
    return request<ProviderTracePage>(
      `/api/admin/provider-traces/page?${query.toString()}`
    );
  },
  clear: () =>
    request<{ deleted_count: number }>("/api/admin/provider-traces", {
      method: "DELETE"
    })
};
