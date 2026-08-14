import { resolveAudience, type AudienceResolution } from "./routing.js";
import type { DiscordDeployment } from "./types.js";

const EXPLICIT_REASONS = new Set<AudienceResolution["reason"]>([
  "selected_reply",
  "selected_alias",
  "selected_multiple",
  "selected_all"
]);

function withoutSmartParticipation(deployment: DiscordDeployment): DiscordDeployment {
  if (deployment.participation_mode !== "smart") return deployment;
  return { ...deployment, participation_mode: "mention_only" };
}

/**
 * Resolve only platform/author-explicit audience signals before E5 or Utility work.
 *
 * The normal routing parser remains authoritative. Smart candidates are cloned as mention-only
 * solely for this side-effect-free preflight, which prevents proactive Smart Participation from
 * running while preserving the exact same reply/name/group parsing rules.
 */
export function resolveExplicitAudiencePreflight(
  candidates: DiscordDeployment[],
  text: string,
  replyDeploymentId: string | null = null,
  groupAliases: string[] = []
): AudienceResolution | null {
  if (!candidates.length) return null;
  const byId = new Map(candidates.map((item) => [item.deployment_id, item]));
  const preflight = resolveAudience(
    candidates.map(withoutSmartParticipation),
    text,
    replyDeploymentId,
    groupAliases,
    {}
  );
  if (!EXPLICIT_REASONS.has(preflight.reason)) return null;

  return {
    ...preflight,
    deployments: preflight.deployments.flatMap((item) => {
      const original = byId.get(item.deployment_id);
      return original ? [original] : [];
    })
  };
}

export function semanticScoringRequired(
  candidates: DiscordDeployment[],
  explicitAudience: AudienceResolution | null
): boolean {
  return (
    explicitAudience === null &&
    candidates.some((item) => item.participation_mode === "smart")
  );
}
