export type DeploymentIdentityMode = "bot" | "webhook";
export type DeploymentWebhookStatus =
  | "pending"
  | "active"
  | "error"
  | "not_required";

export interface DeploymentMessageIdentity {
  deployment_id: string;
  mode: DeploymentIdentityMode;
  display_name: string;
  avatar_url: string;
  address_aliases: string[];
  webhook_status: DeploymentWebhookStatus;
  last_error: string;
  updated_at: string;
}

export interface DeploymentMessageIdentityUpdate {
  mode: DeploymentIdentityMode;
  display_name: string;
  avatar_url: string | null;
  address_aliases: string[];
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

export const discordIdentityApi = {
  list: () =>
    request<DeploymentMessageIdentity[]>("/api/deployment-identities"),
  update: (deploymentId: string, payload: DeploymentMessageIdentityUpdate) =>
    request<DeploymentMessageIdentity>(
      `/api/deployment-identities/${deploymentId}`,
      {
        method: "PUT",
        body: JSON.stringify(payload)
      }
    ),
  delete: (deploymentId: string) =>
    request<void>(`/api/deployment-identities/${deploymentId}`, {
      method: "DELETE"
    })
};
