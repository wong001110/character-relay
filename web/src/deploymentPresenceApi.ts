export type DeploymentPresenceState = "sleeping" | "idle" | "browsing" | "busy";

export interface DeploymentPresenceView {
  deployment_id: string;
  state: DeploymentPresenceState;
  activity_type: string;
  source: string;
  reason: string;
  version: number;
  started_at: string;
  expected_end_at: string | null;
  updated_at: string;
  persisted: boolean;
  available_for_character_runtime: boolean;
  discovery_allowed: boolean;
}

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "include" });
  if (response.ok) return response.json() as Promise<T>;
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") throw new Error(parsed.detail);
  } catch (reason) {
    if (reason instanceof Error && reason.message !== raw) throw reason;
  }
  throw new Error(raw || `Request failed with ${response.status}`);
}

export const deploymentPresenceApi = {
  get(deploymentId: string) {
    return request<DeploymentPresenceView>(
      `/api/deployments/${encodeURIComponent(deploymentId)}/presence`
    );
  }
};
