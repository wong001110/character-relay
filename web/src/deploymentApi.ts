export type PlatformId = "discord" | "whatsapp" | "telegram";
export type ConnectionMode = "managed" | "local";
export type ConnectionStatus = "connected" | "offline" | "error" | "disconnected";
export type ParticipationMode =
  | "mention_only"
  | "reply_only"
  | "mention_and_reply"
  | "smart";
export type MemoryScope = "channel_isolated" | "server_shared" | "custom";
export type DeploymentStatus =
  | "active"
  | "paused"
  | "offline"
  | "error"
  | "disconnected";

export interface PlatformConnection {
  id: string;
  platform: PlatformId;
  display_name: string;
  connection_mode: ConnectionMode;
  external_account_id: string;
  status: ConnectionStatus;
  metadata: Record<string, unknown>;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformConnectionCreate {
  platform: PlatformId;
  display_name: string;
  connection_mode: ConnectionMode;
  external_account_id: string;
  status: ConnectionStatus;
  metadata: Record<string, unknown>;
}

export interface CharacterDeployment {
  id: string;
  character_card_id: string;
  character_display_name: string;
  connection_id: string;
  platform: PlatformId;
  workspace_id: string;
  workspace_name: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  participation_mode: ParticipationMode;
  memory_scope: MemoryScope;
  version_label: string;
  sticker_count: number;
  status: DeploymentStatus;
  last_message_at: string | null;
  last_error: string;
  created_at: string;
  updated_at: string;
}

export interface CharacterDeploymentCreate {
  character_card_id: string;
  connection_id: string;
  workspace_id: string;
  workspace_name: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  participation_mode: ParticipationMode;
  memory_scope: MemoryScope;
  version_label: string;
  sticker_count: number;
  status: DeploymentStatus;
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
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const deploymentApi = {
  listConnections: () => request<PlatformConnection[]>("/api/connections"),
  createConnection: (payload: PlatformConnectionCreate) =>
    request<PlatformConnection>("/api/connections", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateConnection: (
    connectionId: string,
    payload: Partial<Pick<PlatformConnection, "display_name" | "status" | "metadata">>
  ) =>
    request<PlatformConnection>(`/api/connections/${connectionId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteConnection: (connectionId: string) =>
    request<void>(`/api/connections/${connectionId}`, { method: "DELETE" }),
  listDeployments: (characterCardId?: string) =>
    request<CharacterDeployment[]>(
      characterCardId
        ? `/api/deployments?character_card_id=${encodeURIComponent(characterCardId)}`
        : "/api/deployments"
    ),
  createDeployment: (payload: CharacterDeploymentCreate) =>
    request<CharacterDeployment>("/api/deployments", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateDeployment: (
    deploymentId: string,
    payload: Partial<CharacterDeploymentCreate> & { last_error?: string }
  ) =>
    request<CharacterDeployment>(`/api/deployments/${deploymentId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  updateDeploymentStatus: (
    deploymentId: string,
    status: DeploymentStatus,
    lastError = ""
  ) =>
    request<CharacterDeployment>(`/api/deployments/${deploymentId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status, last_error: lastError })
    }),
  deleteDeployment: (deploymentId: string) =>
    request<void>(`/api/deployments/${deploymentId}`, { method: "DELETE" })
};
