export type DiscordDebugCaptureTtlMinutes = 15 | 60 | 1440;
export type DiscordDebugCaptureSessionStatus = "active" | "stopped" | "expired";
export type DiscordDebugCaptureOutcome =
  | "pending"
  | "succeeded"
  | "conflict"
  | "provider_error";

export interface DiscordDebugCaptureSession {
  id: string;
  server_profile_id: string;
  connection_id: string;
  guild_id: string;
  guild_name: string;
  status: DiscordDebugCaptureSessionStatus;
  started_at: string;
  expires_at: string;
  stopped_at: string | null;
  record_count: number;
  evicted_record_count: number;
  captured_bytes: number;
}

export interface DiscordDebugCaptureRecordSummary {
  id: string;
  session_id: string;
  captured_at: string;
  source_message_id: string;
  channel_id: string;
  thread_id: string;
  deployment_id: string;
  character_count: number;
  payload_bytes: number;
  outcome: DiscordDebugCaptureOutcome;
}

export interface DiscordDebugCaptureRecordPage {
  items: DiscordDebugCaptureRecordSummary[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface DiscordDebugCaptureRecordDetail
  extends DiscordDebugCaptureRecordSummary {
  payload: unknown;
}

const API_PREFIX = "/api/admin/discord-debug-captures";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    cache: "no-store",
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

async function access(): Promise<boolean> {
  const response = await fetch(`${API_PREFIX}/access`, {
    cache: "no-store",
    credentials: "include"
  });
  if (response.status === 200) return true;
  if (response.status === 401 || response.status === 403) return false;
  if (response.ok) return false;
  throw new Error(await errorMessage(response));
}

async function currentSession(
  serverProfileId: string
): Promise<DiscordDebugCaptureSession | null> {
  const response = await fetch(
    `${API_PREFIX}/sessions/current?server_profile_id=${encodeURIComponent(serverProfileId)}`,
    {
      cache: "no-store",
      credentials: "include"
    }
  );
  if (response.status === 404 || response.status === 204) return null;
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json() as Promise<DiscordDebugCaptureSession>;
}

export const discordDebugCaptureApi = {
  access,
  startSession: (
    serverProfileId: string,
    ttlMinutes: DiscordDebugCaptureTtlMinutes
  ) =>
    request<DiscordDebugCaptureSession>("/sessions", {
      method: "POST",
      body: JSON.stringify({
        server_profile_id: serverProfileId,
        ttl_minutes: ttlMinutes
      })
    }),
  currentSession,
  stopSession: (sessionId: string) =>
    request<DiscordDebugCaptureSession>(
      `/sessions/${encodeURIComponent(sessionId)}/stop`,
      { method: "POST" }
    ),
  listRecords: (sessionId: string, page = 1, pageSize = 100) => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize)
    });
    return request<DiscordDebugCaptureRecordPage>(
      `/sessions/${encodeURIComponent(sessionId)}/records/page?${query.toString()}`
    );
  },
  recordDetail: (recordId: string) =>
    request<DiscordDebugCaptureRecordDetail>(
      `/records/${encodeURIComponent(recordId)}`
    ),
  clearRecords: (sessionId: string) =>
    request<void>(`/sessions/${encodeURIComponent(sessionId)}/records`, {
      method: "DELETE"
    })
};
