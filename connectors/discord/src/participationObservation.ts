import { RelayClient } from "./relayClient.js";
import type {
  SmartParticipationDecision,
  SmartParticipationCandidateScore
} from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

export interface DiscordParticipationTurnObservation {
  deployment_id: string;
  role: string;
  order: number;
}

export interface DiscordParticipationCandidateObservation {
  deployment_id: string;
  character_card_id: string;
  character_name: string;
  score: number | null;
  minimum_score: number;
  eligible: boolean;
  semantic_relevance: number | null;
  signals: Record<string, number>;
  matched_topics: string[];
  matched_keywords: string[];
  matched_trigger_phrases: string[];
  matched_avoid_phrases: string[];
}

export interface DiscordParticipationObservation {
  source: "smart" | "explicit" | "lightweight";
  reason: string;
  selected_deployment_ids: string[];
  turns: DiscordParticipationTurnObservation[];
  candidates: DiscordParticipationCandidateObservation[];
  minimum_margin: number | null;
}

const pending = new Map<string, DiscordParticipationObservation>();

function characterName(deployment: DiscordDeployment): string {
  return deployment.identity_display_name || deployment.character_display_name;
}

function candidateObservation(
  candidate: SmartParticipationCandidateScore
): DiscordParticipationCandidateObservation {
  return {
    deployment_id: candidate.deployment.deployment_id,
    character_card_id: candidate.deployment.character_card_id,
    character_name: characterName(candidate.deployment),
    score: Number.isFinite(candidate.score) ? candidate.score : null,
    minimum_score: candidate.minimumScore,
    eligible: candidate.eligible,
    semantic_relevance: candidate.semanticRelevance,
    signals: Object.fromEntries(Object.entries(candidate.signals).slice(0, 20)),
    matched_topics: candidate.matchedTopics.slice(0, 12),
    matched_keywords: candidate.matchedKeywords.slice(0, 12),
    matched_trigger_phrases: candidate.matchedTriggerPhrases.slice(0, 12),
    matched_avoid_phrases: candidate.matchedAvoidPhrases.slice(0, 12)
  };
}

export function recordParticipationDecision(
  decision: SmartParticipationDecision,
  minimumMargin: number
): void {
  if (!decision.selectedDeployments.length) return;
  const observation: DiscordParticipationObservation = {
    source: decision.reason === "selected_lightweight" ? "lightweight" : "smart",
    reason: decision.reason,
    selected_deployment_ids: decision.selectedDeployments
      .map((item) => item.deployment_id)
      .slice(0, 8),
    turns: decision.turns.slice(0, 8).map((item) => ({
      deployment_id: item.deployment.deployment_id,
      role: item.role,
      order: item.order
    })),
    candidates: decision.candidates.slice(0, 12).map(candidateObservation),
    minimum_margin: minimumMargin
  };
  for (const deployment of decision.selectedDeployments) {
    pending.set(deployment.deployment_id, observation);
  }
}

export function recordExplicitParticipation(deployments: DiscordDeployment[]): void {
  if (!deployments.length) return;
  const ids = deployments.map((item) => item.deployment_id).slice(0, 8);
  const observation: DiscordParticipationObservation = {
    source: "explicit",
    reason: "explicit_address",
    selected_deployment_ids: ids,
    turns: deployments.slice(0, 8).map((item, index) => ({
      deployment_id: item.deployment_id,
      role: index === 0 ? "primary" : "complement",
      order: index + 1
    })),
    candidates: [],
    minimum_margin: null
  };
  for (const deployment of deployments) {
    pending.set(deployment.deployment_id, observation);
  }
}

export function takeParticipationObservation(
  deploymentId: string
): DiscordParticipationObservation | undefined {
  const value = pending.get(deploymentId);
  pending.delete(deploymentId);
  return value;
}

export function resetParticipationObservations(): void {
  pending.clear();
}

let transportInstalled = false;

function installObservationTransport(): void {
  if (transportInstalled) return;
  transportInstalled = true;

  const processMessage = RelayClient.prototype.processMessage;
  RelayClient.prototype.processMessage = async function (payload) {
    const observation = takeParticipationObservation(payload.deployment_id);
    const observedPayload = observation
      ? ({ ...payload, participation_observation: observation } as typeof payload)
      : payload;
    return processMessage.call(this, observedPayload);
  };

  const processSocialTurnStep = RelayClient.prototype.processSocialTurnStep;
  RelayClient.prototype.processSocialTurnStep = async function (request) {
    const observation = takeParticipationObservation(request.payload.deployment_id);
    const observedPayload = observation
      ? ({
          ...request.payload,
          participation_observation: observation
        } as typeof request.payload)
      : request.payload;
    return processSocialTurnStep.call(this, { ...request, payload: observedPayload });
  };
}

installObservationTransport();
