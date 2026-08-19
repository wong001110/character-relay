export interface CharacterRelationshipPrior {
  id: string;
  source_character_card_id: string;
  target_character_card_id: string;
  relationship_type: string;
  description: string;
  familiarity: number;
  affinity: number;
  trust: number;
  comfort: number;
}

export interface RelationshipGeneration {
  relationship_type: string;
  description: string;
  familiarity: number;
  affinity: number;
  trust: number;
  comfort: number;
  rationale: string;
  provider_model: string;
}

export interface DeploymentRelationshipState {
  id: string;
  source_deployment_id: string;
  target_type: "actor" | "deployment";
  target_key: string;
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

export interface PersonImpression {
  target_type: "actor" | "deployment";
  target_key: string;
  summary: string;
  observations: string[];
  evidence_refs: string[];
  confidence: number;
}

export interface DeploymentRelationshipCandidate {
  target_deployment_id: string;
  target_character_card_id: string;
  target_display_name: string;
  canonical_prior: CharacterRelationshipPrior | null;
  dynamic_state: DeploymentRelationshipState | null;
  impression: PersonImpression | null;
}

export interface DeploymentRelationshipCandidates {
  source_deployment_id: string;
  source_character_card_id: string;
  source_display_name: string;
  items: DeploymentRelationshipCandidate[];
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

export const relationshipApi = {
  listPriors(characterId: string) {
    return request<{ items: CharacterRelationshipPrior[] }>(
      `/api/characters/${encodeURIComponent(characterId)}/relationships`
    );
  },

  candidates(deploymentId: string) {
    return request<DeploymentRelationshipCandidates>(
      `/api/deployments/${encodeURIComponent(deploymentId)}/relationships/candidates`
    );
  },

  generatePrior(
    sourceCharacterId: string,
    targetCharacterId: string,
    input: { relationship_type: string; description: string }
  ) {
    return request<RelationshipGeneration>(
      `/api/characters/${encodeURIComponent(sourceCharacterId)}/relationships/${encodeURIComponent(targetCharacterId)}/generate`,
      { method: "POST", body: JSON.stringify(input) }
    );
  },

  savePrior(sourceCharacterId: string, targetCharacterId: string, input: Omit<CharacterRelationshipPrior, "id" | "source_character_card_id" | "target_character_card_id">) {
    return request<CharacterRelationshipPrior>(
      `/api/characters/${encodeURIComponent(sourceCharacterId)}/relationships/${encodeURIComponent(targetCharacterId)}`,
      { method: "PUT", body: JSON.stringify(input) }
    );
  },

  initialize(sourceDeploymentId: string, targetDeploymentId: string) {
    return request<DeploymentRelationshipState>(
      `/api/deployments/${encodeURIComponent(sourceDeploymentId)}/relationships/initialize/${encodeURIComponent(targetDeploymentId)}`,
      { method: "POST" }
    );
  }
};
