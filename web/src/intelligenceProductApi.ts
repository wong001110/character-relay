export interface RelationshipEvidenceObservation {
  dimension: string;
  delta: number;
  confidence: number;
  reason_code: string;
  source_message_id: string;
  source_burst_id: string;
  recorded_at: string;
}

export interface PersonImpressionObservation {
  summary: string;
  observations: string[];
  evidence_refs: string[];
  confidence: number;
  updated_at: string;
}

export interface RelationshipStateObservation {
  familiarity: number;
  affinity: number;
  trust: number;
  comfort: number;
  familiarity_baseline: number;
  affinity_baseline: number;
  trust_baseline: number;
  comfort_baseline: number;
  last_evidence_at: string;
}

export interface SocialTargetObservation {
  target_type: "actor" | "deployment";
  target_key: string;
  target_kind: "user" | "bot" | "character" | "unknown";
  label: string;
  avatar_url: string;
  state: RelationshipStateObservation | null;
  impression: PersonImpressionObservation | null;
  recent_evidence: RelationshipEvidenceObservation[];
}

export interface DeploymentSocialIntelligence {
  deployment_id: string;
  character_card_id: string;
  character_display_name: string;
  connection_id: string;
  guild_id: string;
  items: SocialTargetObservation[];
}

export interface ParticipationDeploymentObservation {
  deployment_id: string;
  character_card_id: string;
  character_display_name: string;
  status: string;
  participation_mode: string;
  last_admitted_at: string | null;
  last_channel_id: string;
  last_thread_id: string;
}

export interface ParticipationScopeObservation {
  channel_id: string;
  thread_id: string;
  last_admitted_at: string | null;
  recent_deployment_id: string;
  window_started_at: string | null;
  window_count: number;
}

export interface ReplyPlannerDecisionObservation {
  deployment_id: string;
  character_card_id: string;
  character_display_name: string;
  burst_id: string;
  source_message_id: string;
  channel_id: string;
  thread_id: string;
  segment_id: string;
  semantic_thread_id: string;
  score: number;
  reason: string;
  guidance: string;
  plan_kind: string;
  authoritative: boolean;
  resolver_version: string;
  created_at: string;
}

export interface ServerParticipationIntelligence {
  server_profile_id: string;
  resolver_version: string;
  planner_model: string;
  deployments: ParticipationDeploymentObservation[];
  scopes: ParticipationScopeObservation[];
  recent_reply_decisions: ReplyPlannerDecisionObservation[];
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

export const intelligenceProductApi = {
  social(deploymentId: string) {
    return request<DeploymentSocialIntelligence>(
      `/api/deployments/${encodeURIComponent(deploymentId)}/social-intelligence`
    );
  },

  participation(serverProfileId: string) {
    return request<ServerParticipationIntelligence>(
      `/api/server-profiles/${encodeURIComponent(serverProfileId)}/participation-intelligence`
    );
  }
};
