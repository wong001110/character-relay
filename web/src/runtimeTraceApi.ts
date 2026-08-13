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

interface ParticipationCandidateObservation {
  deployment_id: string;
  character_name?: string;
  score: number | null;
  minimum_score: number;
  eligible: boolean;
  semantic_relevance: number | null;
  signals: Record<string, number>;
}

interface ParticipationObservation {
  source: string;
  reason: string;
  selected_deployment_ids: string[];
  candidates: ParticipationCandidateObservation[];
  minimum_margin: number | null;
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

function parseParticipation(value: string | undefined): ParticipationObservation | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as ParticipationObservation;
    return parsed && Array.isArray(parsed.selected_deployment_ids) ? parsed : null;
  } catch {
    return null;
  }
}

function signalSummary(signals: Record<string, number>): string {
  return Object.entries(signals)
    .filter(([, score]) => score !== 0)
    .map(([name, score]) => `${name} ${score > 0 ? "+" : ""}${score}`)
    .join(", ");
}

function expandTurnContext(event: RuntimeTraceEvent): RuntimeTraceEvent {
  if (event.node_name !== "turn_context") return event;
  const raw = Object.fromEntries(event.metadata);
  const expanded: Array<[string, string]> = [];
  if (raw.topic_label || raw.topic_id) {
    const suffix = [raw.topic_status, raw.topic_message_count && `${raw.topic_message_count} msgs`]
      .filter(Boolean)
      .join(" · ");
    expanded.push(["Topic", `${raw.topic_label || raw.topic_id}${suffix ? ` · ${suffix}` : ""}`]);
  }
  if (raw.continuity_reason) {
    const retry = Number(raw.retry_score || "0");
    expanded.push([
      "Continuity",
      `${raw.continuity_reason}${retry > 0 ? ` · retry ${retry.toFixed(3)}` : ""}`
    ]);
  }
  if (raw.recalled_media === "available") {
    expanded.push([
      "Media continuity",
      `restored skipped source · message ${raw.recalled_media_source_message_id || "—"}`
    ]);
  }

  const participation = parseParticipation(raw.participation_observation);
  if (participation) {
    expanded.push([
      "Selection",
      `${participation.source} / ${participation.reason}${
        participation.minimum_margin !== null
          ? ` · margin ${participation.minimum_margin}`
          : ""
      }`
    ]);
    for (const candidate of participation.candidates) {
      const selected = participation.selected_deployment_ids.includes(candidate.deployment_id);
      const semantic =
        candidate.semantic_relevance === null
          ? ""
          : ` · semantic ${candidate.semantic_relevance.toFixed(3)}`;
      const signals = signalSummary(candidate.signals);
      expanded.push([
        `Speaker · ${candidate.character_name || candidate.deployment_id}`,
        `${selected ? "SELECTED" : candidate.eligible ? "candidate" : "blocked"} · score ${
          candidate.score ?? "—"
        } / ${candidate.minimum_score}${semantic}${signals ? ` · ${signals}` : ""}`
      ]);
    }
    if (!participation.candidates.length) {
      expanded.push([
        "Speaker routing",
        "explicit Tag / Reply / Character selection; no synthetic Smart Participation score"
      ]);
    }
  }

  const diagnosticKeys = [
    "rag_pipeline",
    "source_message_id",
    "recalled_media",
    "recalled_media_source_message_id"
  ];
  for (const key of diagnosticKeys) {
    if (raw[key]) expanded.push([key, raw[key]]);
  }
  return { ...event, metadata: expanded.length ? expanded : event.metadata };
}

function expandRuntimeTrace(view: RuntimeTraceView): RuntimeTraceView {
  return { ...view, events: view.events.map(expandTurnContext) };
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
  detail: async (graphRunId: string, signal?: AbortSignal) =>
    expandRuntimeTrace(
      await request<RuntimeTraceView>(
        `/api/admin/runtime-traces/${encodeURIComponent(graphRunId)}`,
        { signal }
      )
    ),
  clear: (ownerId?: string) => {
    const selected = ownerId?.trim() ?? "";
    const suffix = selected ? `?owner_id=${encodeURIComponent(selected)}` : "";
    return request<{ deleted_count: number }>(`/api/admin/runtime-traces${suffix}`, {
      method: "DELETE"
    });
  }
};
