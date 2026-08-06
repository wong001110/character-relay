export type InteractionStatus = "active" | "paused" | "stopped" | "completed";
export type InteractionIntensity = "light" | "playful" | "sharp";

export interface InteractionTemplate {
  id: string;
  server_profile_id: string;
  name: string;
  template_type: "roast";
  participant_character_card_ids: string[];
  participant_names: string[];
  rounds_per_trigger: number;
  maximum_triggers: number;
  maximum_replies_per_trigger: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  created_at: string;
  updated_at: string;
}

export interface InteractionTemplateCreate {
  server_profile_id: string;
  name: string;
  participant_character_card_ids: string[];
  rounds_per_trigger: number;
  maximum_triggers: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
}

export type InteractionTemplateUpdate = Partial<Omit<InteractionTemplateCreate, "server_profile_id">>;

export interface InteractionTemplateApply {
  channel_id: string;
  target_user_id: string;
  target_display_name: string;
  status: "active" | "paused";
}

export interface InteractionSession {
  id: string;
  connection_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  category_id: string;
  target_user_id: string;
  target_display_name: string;
  participant_deployment_ids: string[];
  participant_names: string[];
  session_type: "roast";
  rounds_per_trigger: number;
  maximum_triggers: number;
  completed_triggers: number;
  maximum_replies_per_trigger: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  status: InteractionStatus;
  started_at: string | null;
  expires_at: string | null;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InteractionSessionCreate {
  connection_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  category_id: string;
  target_user_id: string;
  target_display_name: string;
  participant_deployment_ids: string[];
  rounds_per_trigger: number;
  maximum_triggers: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  status: "active" | "paused";
}

export interface StickerSemantic {
  id: string;
  connection_id: string;
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export type ExpressionResourceType = "emoji" | "sticker";
export type ExpressionAction = "none" | "inline" | "reaction" | "sticker";

export interface ExpressionSemantic {
  id: string;
  resource_key: string;
  connection_id: string;
  guild_id: string;
  resource_type: ExpressionResourceType;
  resource_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  animated: boolean;
  available: boolean;
  enabled: boolean;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  aliases: string[];
  situations: string[];
  avoid_when: string[];
  allowed_actions: Array<"inline" | "reaction" | "sticker">;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export type ExpressionSemanticCreate = Omit<
  ExpressionSemantic,
  | "id"
  | "resource_key"
  | "semantic_source"
  | "semantic_confidence"
  | "last_seen_at"
  | "created_at"
  | "updated_at"
>;

export interface ExpressionNode {
  id: string;
  node_name: string;
  node_index: number;
  attempt: number;
  status: "running" | "completed" | "failed" | "skipped";
  input_summary: Record<string, unknown>;
  output_summary: Record<string, unknown>;
  error: string;
  started_at: string;
  completed_at: string | null;
}

export interface ExpressionRun {
  id: string;
  connection_id: string;
  guild_id: string;
  channel_id: string;
  source_message_id: string;
  deployment_id: string;
  character_card_id: string;
  status: "running" | "completed" | "failed" | "skipped";
  current_node: string;
  attempt_count: number;
  selected_action: ExpressionAction;
  selected_resource_key: string;
  state: Record<string, unknown>;
  last_error: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ExpressionRunDetail extends ExpressionRun {
  nodes: ExpressionNode[];
}

export interface ExpressionSuggestionRequest {
  resource_type: ExpressionResourceType;
  resource_id: string;
  name: string;
  description: string;
  tags: string[];
  animated: boolean;
  asset_url: string;
  usage_context: string;
  language: "en" | "zh-CN";
}

export interface ExpressionSuggestionResult {
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  aliases: string[];
  situations: string[];
  avoid_when: string[];
  provider_model: string;
  correction_used: boolean;
}

export interface StickerSemanticCreate {
  connection_id: string;
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve raw response.
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

export const interactionApi = {
  listTemplates: (serverProfileId: string) =>
    request<InteractionTemplate[]>(
      `/api/interaction-templates?server_profile_id=${encodeURIComponent(serverProfileId)}`
    ),
  createTemplate: (payload: InteractionTemplateCreate) =>
    request<InteractionTemplate>("/api/interaction-templates", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateTemplate: (templateId: string, payload: InteractionTemplateUpdate) =>
    request<InteractionTemplate>(`/api/interaction-templates/${templateId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  applyTemplate: (templateId: string, payload: InteractionTemplateApply) =>
    request<InteractionSession>(`/api/interaction-templates/${templateId}/apply`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  deleteTemplate: (templateId: string) =>
    request<void>(`/api/interaction-templates/${templateId}`, { method: "DELETE" }),
  listSessions: (options: { connectionId?: string; guildId?: string } = {}) => {
    const query = new URLSearchParams();
    if (options.connectionId) query.set("connection_id", options.connectionId);
    if (options.guildId) query.set("guild_id", options.guildId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<InteractionSession[]>(`/api/interaction-sessions${suffix}`);
  },
  createSession: (payload: InteractionSessionCreate) =>
    request<InteractionSession>("/api/interaction-sessions", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateSessionStatus: (sessionId: string, status: InteractionStatus) =>
    request<InteractionSession>(`/api/interaction-sessions/${sessionId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status })
    }),
  deleteSession: (sessionId: string) =>
    request<void>(`/api/interaction-sessions/${sessionId}`, { method: "DELETE" }),
  listStickers: (connectionId?: string, guildId?: string) => {
    const query = new URLSearchParams();
    if (connectionId) query.set("connection_id", connectionId);
    if (guildId) query.set("guild_id", guildId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<StickerSemantic[]>(`/api/discord/sticker-dictionary${suffix}`);
  },
  saveSticker: (payload: StickerSemanticCreate) =>
    request<StickerSemantic>("/api/discord/sticker-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteSticker: (recordId: string) =>
    request<void>(`/api/discord/sticker-dictionary/${recordId}`, {
      method: "DELETE"
    }),
  listExpressions: (connectionId?: string, guildId?: string) => {
    const query = new URLSearchParams();
    if (connectionId) query.set("connection_id", connectionId);
    if (guildId) query.set("guild_id", guildId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<ExpressionSemantic[]>(`/api/discord/expression-dictionary${suffix}`);
  },
  saveExpression: (payload: ExpressionSemanticCreate) =>
    request<ExpressionSemantic>("/api/discord/expression-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  suggestExpression: (payload: ExpressionSuggestionRequest) =>
    request<ExpressionSuggestionResult>(
      "/api/discord/expression-dictionary/suggest",
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    ),
  listExpressionRuns: (connectionId?: string, guildId?: string) => {
    const query = new URLSearchParams({ limit: "50" });
    if (connectionId) query.set("connection_id", connectionId);
    if (guildId) query.set("guild_id", guildId);
    return request<ExpressionRun[]>(`/api/discord/expression-runs?${query.toString()}`);
  },
  getExpressionRun: (runId: string) =>
    request<ExpressionRunDetail>(`/api/discord/expression-runs/${runId}`)
};
