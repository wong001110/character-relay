import type { DiscordConnectorEventInput } from "./eventReporter.js";
import type { SmartParticipationCandidateScore, SmartParticipationDecision } from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

const MAX_PENDING_DECISIONS = 300;
const pending: DiscordConnectorEventInput[] = [];

function displayName(deployment: DiscordDeployment): string {
  return deployment.identity_display_name || deployment.character_display_name;
}

function candidateDetails(
  deployment: DiscordDeployment,
  score: SmartParticipationCandidateScore | undefined,
  selectedIds: Set<string>
): Record<string, unknown> {
  return {
    deployment_id: deployment.deployment_id,
    character_card_id: deployment.character_card_id,
    character_name: displayName(deployment),
    participation_mode: deployment.participation_mode,
    selected: selectedIds.has(deployment.deployment_id),
    scored: Boolean(score),
    score: score && Number.isFinite(score.score) ? score.score : null,
    minimum_score: score?.minimumScore ?? null,
    eligible: score?.eligible ?? null,
    semantic_relevance: score?.semanticRelevance ?? null,
    signals: score?.signals ?? {},
    matched_topics: score?.matchedTopics ?? [],
    matched_keywords: score?.matchedKeywords ?? [],
    matched_trigger_phrases: score?.matchedTriggerPhrases ?? [],
    matched_avoid_phrases: score?.matchedAvoidPhrases ?? []
  };
}

export function recordSmartParticipationDecision(input: {
  message: string;
  decision: SmartParticipationDecision;
  deployments: DiscordDeployment[];
}): void {
  const smartDeployments = input.deployments.filter(
    (deployment) => deployment.participation_mode === "smart"
  );
  if (!smartDeployments.length) return;

  const first = smartDeployments[0]!;
  const byDeployment = new Map(
    input.decision.candidates.map((candidate) => [candidate.deployment.deployment_id, candidate])
  );
  const selectedIds = new Set(
    input.decision.selectedDeployments.map((deployment) => deployment.deployment_id)
  );
  const candidates = smartDeployments.map((deployment) =>
    candidateDetails(deployment, byDeployment.get(deployment.deployment_id), selectedIds)
  );

  const event: DiscordConnectorEventInput = {
    level: "info",
    event_type: "smart_participation_decision",
    message: "Smart Participation evaluated the available character candidates.",
    guild_id: first.workspace_id,
    guild_name: first.workspace_name,
    channel_id: first.channel_id,
    channel_name: first.channel_name,
    thread_id: first.thread_id,
    thread_name: first.thread_name,
    source_message_id: "",
    deployment_id: "",
    character_name: "",
    details: {
      trigger_preview: input.message.trim().slice(0, 600),
      reason: input.decision.reason,
      candidate_count: candidates.length,
      scored_candidate_count: input.decision.candidates.length,
      selected_count: selectedIds.size,
      selected_deployment_ids: [...selectedIds],
      score_is_sum_of_signals: true,
      candidates
    }
  };

  if (pending.length >= MAX_PENDING_DECISIONS) pending.shift();
  pending.push(event);
}

export function drainSmartParticipationDecisionEvents(): DiscordConnectorEventInput[] {
  return pending.splice(0, pending.length);
}

export function pendingSmartParticipationDecisionCount(): number {
  return pending.length;
}
