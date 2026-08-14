import type {
  DiscordParticipationShadowCandidate,
  DiscordParticipationShadowPlanItem
} from "./relayClient.js";

export interface ParticipationShadowParity {
  observed: boolean;
  exactMatch: boolean;
  setMatch: boolean;
  shadowDeploymentIds: string[];
  actualDeploymentIds: string[];
  missingFromShadow: string[];
  extraInShadow: string[];
  shadowCandidateScores: DiscordParticipationShadowCandidate[];
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values.map((item) => item.trim()).filter(Boolean))];
}

export function compareParticipationShadowPlan(
  shadowPlan: readonly DiscordParticipationShadowPlanItem[] | undefined,
  actualDeploymentIds: readonly string[],
  shadowCandidateScores: readonly DiscordParticipationShadowCandidate[] | undefined
): ParticipationShadowParity {
  if (shadowPlan === undefined || shadowCandidateScores === undefined) {
    return {
      observed: false,
      exactMatch: false,
      setMatch: false,
      shadowDeploymentIds: [],
      actualDeploymentIds: unique(actualDeploymentIds),
      missingFromShadow: [],
      extraInShadow: [],
      shadowCandidateScores: []
    };
  }

  const shadowDeploymentIds = unique(shadowPlan.map((item) => item.deployment_id));
  const actual = unique(actualDeploymentIds);
  const shadowSet = new Set(shadowDeploymentIds);
  const actualSet = new Set(actual);
  return {
    observed: true,
    exactMatch:
      shadowDeploymentIds.length === actual.length &&
      shadowDeploymentIds.every((deploymentId, index) => deploymentId === actual[index]),
    setMatch:
      shadowSet.size === actualSet.size && [...shadowSet].every((item) => actualSet.has(item)),
    shadowDeploymentIds,
    actualDeploymentIds: actual,
    missingFromShadow: actual.filter((item) => !shadowSet.has(item)),
    extraInShadow: shadowDeploymentIds.filter((item) => !actualSet.has(item)),
    shadowCandidateScores: [...shadowCandidateScores]
  };
}
