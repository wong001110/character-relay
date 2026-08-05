export type InteractionStatus = "active" | "paused" | "stopped" | "completed";
export type InteractionIntensity = "light" | "playful" | "sharp";

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
  listSessions: () => request<InteractionSession[]>("/api/interaction-sessions"),
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
  listStickers: () =>
    request<StickerSemantic[]>("/api/discord/sticker-dictionary"),
  saveSticker: (payload: StickerSemanticCreate) =>
    request<StickerSemantic>("/api/discord/sticker-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteSticker: (recordId: string) =>
    request<void>(`/api/discord/sticker-dictionary/${recordId}`, {
      method: "DELETE"
    })
};
