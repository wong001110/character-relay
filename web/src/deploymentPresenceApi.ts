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

export interface DeploymentPresenceRhythmView {
  deployment_id: string;
  enabled: boolean;
  preferred_sleep_start_minute: number;
  sleep_duration_min_minutes: number;
  sleep_duration_max_minutes: number;
  variation_minutes: number;
  config_version: number;
  schedule_local_date: string;
  schedule_timezone: string;
  scheduled_sleep_at: string | null;
  scheduled_wake_at: string | null;
  next_transition_at: string | null;
  next_state: string;
  last_transition_at: string | null;
  last_transition_reason: string;
}

export interface DeploymentPresenceRhythmUpdate {
  enabled: boolean;
  preferred_sleep_start_minute: number;
  sleep_duration_min_minutes: number;
  sleep_duration_max_minutes: number;
  variation_minutes: number;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...init });
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

function rhythmUrl(deploymentId: string): string {
  return `/api/deployments/${encodeURIComponent(deploymentId)}/presence/rhythm`;
}

export const deploymentPresenceApi = {
  get(deploymentId: string) {
    return request<DeploymentPresenceView>(
      `/api/deployments/${encodeURIComponent(deploymentId)}/presence`
    );
  },
  getRhythm(deploymentId: string) {
    return request<DeploymentPresenceRhythmView>(rhythmUrl(deploymentId));
  },
  updateRhythm(deploymentId: string, payload: DeploymentPresenceRhythmUpdate) {
    return request<DeploymentPresenceRhythmView>(rhythmUrl(deploymentId), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }
};
