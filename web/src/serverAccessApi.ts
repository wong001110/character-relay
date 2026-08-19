export interface ServerAccessItem {
  connection_id: string;
  guild_id: string;
  guild_name: string;
  profile_id: string | null;
  access_source: string;
  joined_at: string | null;
}

export interface ServerAccessOverview {
  is_super_admin: boolean;
  servers: ServerAccessItem[];
}

export interface ServerAccessMember {
  user_id: string;
  display_name: string;
  email: string;
  access_source: string;
  joined_at: string;
}

export interface AdminServerAccess {
  connection_id: string;
  guild_id: string;
  guild_name: string;
  join_code: string;
  join_enabled: boolean;
  synced_at: string;
  members: ServerAccessMember[];
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Keep the raw response below.
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

export const serverAccessApi = {
  overview: () => request<ServerAccessOverview>("/api/account/server-access"),
  join: (code: string) =>
    request<ServerAccessItem>("/api/account/server-access/join", {
      method: "POST",
      body: JSON.stringify({ code })
    }),
  listAdminServers: () =>
    request<AdminServerAccess[]>("/api/admin/server-access/servers"),
  setJoinEnabled: (guildId: string, joinEnabled: boolean) =>
    request<AdminServerAccess>(
      `/api/admin/server-access/servers/${encodeURIComponent(guildId)}/join`,
      {
        method: "PATCH",
        body: JSON.stringify({ join_enabled: joinEnabled })
      }
    ),
  regenerateJoinCode: (guildId: string) =>
    request<AdminServerAccess>(
      `/api/admin/server-access/servers/${encodeURIComponent(guildId)}/join-code/regenerate`,
      { method: "POST" }
    ),
  grantMember: (guildId: string, userId: string) =>
    request<AdminServerAccess>(
      `/api/admin/server-access/servers/${encodeURIComponent(guildId)}/members/${encodeURIComponent(userId)}`,
      { method: "PUT" }
    ),
  revokeMember: (guildId: string, userId: string) =>
    request<AdminServerAccess>(
      `/api/admin/server-access/servers/${encodeURIComponent(guildId)}/members/${encodeURIComponent(userId)}`,
      { method: "DELETE" }
    )
};
