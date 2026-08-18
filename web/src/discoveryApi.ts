export type DiscoveryMode = "off" | "shadow" | "review" | "auto";
export type DiscoveryPlatform = "youtube" | "bilibili";

export interface DiscoveryProfile {
  deployment_id: string;
  mode: DiscoveryMode;
  youtube_enabled: boolean;
  bilibili_enabled: boolean;
  bilibili_experimental_available: boolean;
  auto_share_enabled: boolean;
  auto_global_enabled: boolean;
  daily_share_budget: number;
  share_cooldown_minutes: number;
}

export interface DiscoveryItem {
  id: string;
  source: string;
  canonical_key: string;
  content_kind: string;
  title: string;
  creator: string;
  url: string;
  thumbnail_url: string;
  published_at: string | null;
}

export interface DiscoverySession {
  id: string;
  deployment_id: string;
  activity_type: string;
  platform: string;
  status: string;
  source: string;
  local_date: string;
  schedule_timezone: string;
  scheduled_start_at: string | null;
  latest_start_at: string | null;
  planned_duration_minutes: number;
  started_at: string | null;
  expected_end_at: string | null;
  ended_at: string | null;
  candidate_budget: number;
  open_budget: number;
  watch_budget: number;
  share_intent_budget: number;
  exploration_percent: number;
  candidate_count: number;
  notice_count: number;
  open_count: number;
  watch_count: number;
  engage_count: number;
  reason: string;
  error: string;
}

export interface DiscoveryExposure {
  id: string;
  deployment_id: string;
  item: DiscoveryItem;
  attention_level: string;
  interest_score: number;
  subjective_reason: string;
  exposure_count: number;
  first_exposed_at: string;
  last_exposed_at: string;
}

export interface DiscoveryDecision {
  id: string;
  deployment_id: string;
  item: DiscoveryItem;
  mode: string;
  decision: string;
  motivation: string;
  confidence: number;
  scores: Record<string, unknown>;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface DiscoveryShare {
  id: string;
  deployment_id: string;
  item: DiscoveryItem;
  mode: string;
  status: string;
  motivation: string;
  confidence: number;
  topic_id: string;
  relationship_subject_key: string;
  channel_id: string;
  thread_id: string;
  draft_text: string;
  attempt_count: number;
  last_error: string;
  approved_at: string | null;
  rejected_at: string | null;
  queued_at: string | null;
  delivered_at: string | null;
  discord_message_id: string;
  created_at: string;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers
    }
  });
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") throw new Error(parsed.detail);
  } catch (reason) {
    if (reason instanceof Error && reason.message !== raw) throw reason;
  }
  throw new Error(raw || `Request failed with ${response.status}`);
}

function root(deploymentId: string): string {
  return `/api/deployments/${encodeURIComponent(deploymentId)}/discovery`;
}

export const discoveryApi = {
  profile(deploymentId: string) {
    return request<DiscoveryProfile>(`${root(deploymentId)}/profile`);
  },

  updateProfile(deploymentId: string, profile: DiscoveryProfile) {
    return request<DiscoveryProfile>(`${root(deploymentId)}/profile`, {
      method: "PUT",
      body: JSON.stringify({
        mode: profile.mode,
        youtube_enabled: profile.youtube_enabled,
        bilibili_enabled: profile.bilibili_enabled,
        auto_share_enabled: profile.auto_share_enabled,
        daily_share_budget: profile.daily_share_budget,
        share_cooldown_minutes: profile.share_cooldown_minutes
      })
    });
  },

  sessions(deploymentId: string) {
    return request<{ items: DiscoverySession[] }>(`${root(deploymentId)}/sessions?limit=20`);
  },

  exposures(deploymentId: string) {
    return request<{ items: DiscoveryExposure[] }>(`${root(deploymentId)}/exposures?limit=50`);
  },

  decisions(deploymentId: string) {
    return request<{ items: DiscoveryDecision[] }>(`${root(deploymentId)}/decisions?limit=50`);
  },

  shares(deploymentId: string) {
    return request<{ items: DiscoveryShare[] }>(`${root(deploymentId)}/shares?limit=50`);
  },

  browse(deploymentId: string, platform?: DiscoveryPlatform) {
    return request<{ session: DiscoverySession; items: unknown[] }>(`${root(deploymentId)}/browse-shadow`, {
      method: "POST",
      body: JSON.stringify({ platform: platform ?? null })
    });
  },

  approve(deploymentId: string, shareId: string) {
    return request<DiscoveryShare>(
      `${root(deploymentId)}/shares/${encodeURIComponent(shareId)}/approve`,
      { method: "POST" }
    );
  },

  reject(deploymentId: string, shareId: string) {
    return request<DiscoveryShare>(
      `${root(deploymentId)}/shares/${encodeURIComponent(shareId)}/reject`,
      { method: "POST" }
    );
  }
};
