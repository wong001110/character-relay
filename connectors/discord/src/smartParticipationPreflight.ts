import { smartParticipationProfileFor } from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

export interface SmartParticipationCandidatePreflight {
  deploymentId: string;
  eligible: boolean;
  minimumScore: number;
  reason: "eligible" | "profile_disabled" | "avoid_phrase" | "not_smart";
  signals: Record<string, number>;
}

function normalizeText(value: string): string {
  return value.normalize("NFKC").toLocaleLowerCase().replace(/\s+/gu, " ").trim();
}

export function preflightSmartParticipationCandidate(
  deployment: DiscordDeployment,
  message: string
): SmartParticipationCandidatePreflight {
  if (deployment.participation_mode !== "smart") {
    return {
      deploymentId: deployment.deployment_id,
      eligible: false,
      minimumScore: 0,
      reason: "not_smart",
      signals: {}
    };
  }
  const profile = smartParticipationProfileFor(deployment);
  if (!profile.enabled) {
    return {
      deploymentId: deployment.deployment_id,
      eligible: false,
      minimumScore: profile.minimumScore,
      reason: "profile_disabled",
      signals: { profile_disabled_blocked: 1 }
    };
  }
  const text = normalizeText(message);
  if (profile.avoidPhrases.some((phrase) => phrase && text.includes(phrase))) {
    return {
      deploymentId: deployment.deployment_id,
      eligible: false,
      minimumScore: profile.minimumScore,
      reason: "avoid_phrase",
      signals: { avoid_phrase_blocked: 1 }
    };
  }
  return {
    deploymentId: deployment.deployment_id,
    eligible: true,
    minimumScore: profile.minimumScore,
    reason: "eligible",
    signals: {}
  };
}

export function preflightSmartParticipationCandidates(
  deployments: DiscordDeployment[],
  message: string
): SmartParticipationCandidatePreflight[] {
  return deployments.map((deployment) => preflightSmartParticipationCandidate(deployment, message));
}
