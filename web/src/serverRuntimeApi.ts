export const DEFAULT_SERVER_TIMEZONE = "Asia/Kuala_Lumpur";

export interface ServerRuntimeTimezone {
  profile_id: string;
  timezone: string;
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

export function browserTimezone(): string {
  // Character Relay uses Malaysia time as the product-level default. A Server owner can
  // still explicitly save another IANA timezone in Server settings afterwards.
  return DEFAULT_SERVER_TIMEZONE;
}

export const serverRuntimeApi = {
  getTimezone: (profileId: string) =>
    request<ServerRuntimeTimezone>(
      `/api/discord/server-profiles/${encodeURIComponent(profileId)}/runtime`
    ),
  updateTimezone: (profileId: string, timezone: string) =>
    request<ServerRuntimeTimezone>(
      `/api/discord/server-profiles/${encodeURIComponent(profileId)}/runtime`,
      {
        method: "PATCH",
        body: JSON.stringify({ timezone })
      }
    )
};
