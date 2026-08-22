import type {
  ConnectorHeartbeat,
  DiscordConnectorEvent,
  DiscordInteractionClaim,
  DiscordInteractionClaimRequest,
  DiscordInteractionRunComplete,
  DiscordDeployment,
  DiscordExpressionContent,
  DiscordExpressionNodeReport,
  DiscordExpressionResolveRequest,
  DiscordExpressionRetrieval,
  DiscordExpressionRetrieveRequest,
  DiscordInboundMessage,
  DiscordMessageRouteLookup,
  DiscordMessageRouteRegistration,
  DiscordMessageRouteView,
  DiscordReply,
  DiscordServerCatalogSync,
  DiscordSocialTurnStepReply,
  DiscordSocialTurnStepRequest,
  DiscordStickerContent,
  DiscordStickerObservation,
  DiscordWebhookRegistration,
  DiscordWebhookRegistrationResult,
  DiscordWebhookStatusReport
} from "./types.js";
import type { DiscordPortalParticipationProfile } from "./smartParticipation.js";
import type {
  DiscordDeliveryAckRequest,
  DiscordDeliveryClaim,
  DiscordDeliveryClaimRequest,
  DiscordDeliveryFailureRequest,
  DiscordPendingSocialOperation,
  DiscordSocialOperationClaim,
  DiscordSocialOperationClaimRequest
} from "./durableRuntime.js";

export interface DiscordV3ParticipationCandidate {
  deployment_id: string;
  character_card_id: string;
  eligible: boolean;
  deterministic_score: number;
  minimum_score: number;
  deterministic_signals: Record<string, number>;
  raw_e5_relevance: number;
  profile_ready: boolean;
  semantic_points: number;
  final_evidence_score: number;
}

export interface DiscordV3SpeakerPlanItem {
  deployment_id: string;
  turn_role: string;
  reason: string;
  guidance: string;
}

export interface DiscordV3ConversationSegment {
  id: string;
  message_ids: string[];
  participant_ids: string[];
  kind: string;
  summary: string;
  conversation_thread_id: string;
  membership_relation: string;
  membership_confidence: number;
  confidence: number;
  source: string;
}

export interface DiscordV3ReplyTarget {
  deployment_id: string;
  segment_id: string;
  conversation_thread_id: string;
  score: number;
  reason: string;
  grounding_level: string;
  context_sufficiency: string;
}

export interface DiscordV3ParticipationResult {
  resolver_version: "conversation-intelligence-v3";
  available: boolean;
  reason: string;
  model: string;
  dimension: number;
  burst_id: string;
  burst_message_count: number;
  analysis_chars: number;
  candidates: DiscordV3ParticipationCandidate[];
  segmentation_used: boolean;
  segmentation_source: string;
  conversation_segments: DiscordV3ConversationSegment[];
  reply_targets: DiscordV3ReplyTarget[];
  speaker_plan: DiscordV3SpeakerPlanItem[];
  speaker_plan_authoritative: true;
  participation_plan_reason: string;
  media_grounding_level: string;
  media_grounding_reason: string;
  context_sufficiency: Record<string, string>;
  utility_used: boolean;
}

export interface DiscordParticipationBurstMessage {
  message_id: string;
  author_id: string;
  author_display_name: string;
  text: string;
  created_at: string;
  reply_to_message_id: string;
}

export interface DiscordSmartParticipationCandidatePreflight {
  deployment_id: string;
  eligible: boolean;
  deterministic_score: number;
  minimum_score: number;
  signals: Record<string, number>;
}

export interface DiscordConversationBurstRuntimeConfig {
  enabled: boolean;
  quiet_window_ms: number;
  max_wait_ms: number;
  max_messages: number;
  max_characters: number;
}


export interface DiscordPlannerMediaDescriptor {
  ref: string;
  kind: "image" | "video" | "article" | "link" | "file";
  state: "resolved" | "preview_only" | "unresolved";
  label: string;
  subject: string;
  summary: string;
  source_key: string;
  source_url: string;
}

export interface DiscordPlannerMediaResult {
  descriptors: DiscordPlannerMediaDescriptor[];
  dependency: "required" | "optional" | "none";
  dependency_reason: string;
  dependency_locked: boolean;
  planning_text: string;
}

export interface DiscordSmartParticipationScoreRequest {
  message: string;
  deployment_ids: string[];
  guild_id?: string;
  channel_id?: string;
  thread_id?: string;
  message_id?: string;
  author_id?: string;
  reply_to_message_id?: string;
  burst_id?: string;
  burst_messages?: DiscordParticipationBurstMessage[];
  minimum_margin?: number;
  max_participants?: number;
  channel_cooldown_seconds?: number;
  window_seconds?: number;
  max_replies_per_window?: number;
  candidate_preflight?: DiscordSmartParticipationCandidatePreflight[];
  media_descriptors?: DiscordPlannerMediaDescriptor[];
  media_dependency?: "required" | "optional" | "none";
  media_dependency_locked?: boolean;
}

interface ConnectorAttachment {
  attachment_id: string;
  url: string;
  proxy_url: string;
  filename: string;
  content_type: string;
  size_bytes: number | null;
  width: number | null;
  height: number | null;
}

interface ConnectorEmbed {
  embed_type: string;
  url: string;
  title: string;
  description: string;
  provider_name: string;
  author_name: string;
}

interface DiscordMessageApiAttachment {
  id?: unknown;
  url?: unknown;
  proxy_url?: unknown;
  filename?: unknown;
  content_type?: unknown;
  size?: unknown;
  width?: unknown;
  height?: unknown;
}

interface DiscordMessageApiEmbed {
  type?: unknown;
  url?: unknown;
  title?: unknown;
  description?: unknown;
  provider?: unknown;
  author?: unknown;
}

interface DiscordMessageMedia {
  attachments: ConnectorAttachment[];
  embeds: ConnectorEmbed[];
  reply_to_message_id: string;
}

interface AttachmentCacheEntry extends DiscordMessageMedia {
  expiresAt: number;
}

const RETRY_DELAYS_MS = [0, 1_000, 2_000, 4_000, 8_000, 15_000];
const TRANSIENT_STATUS_CODES = new Set([502, 503, 504]);
const DISCORD_API_BASE = "https://discord.com/api/v10";
const ATTACHMENT_CACHE_MS = 5 * 60 * 1_000;

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function errorDetail(error: unknown): string {
  if (!(error instanceof Error)) return String(error);
  const cause = error.cause;
  if (cause instanceof Error && cause.message) {
    return `${error.message}: ${cause.message}`;
  }
  return error.message;
}

function stringValue(value: unknown, maximum: number): string {
  return typeof value === "string" ? value.trim().slice(0, maximum) : "";
}

function integerValue(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : null;
}

function nestedString(value: unknown, key: string, maximum: number): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  return stringValue((value as Record<string, unknown>)[key], maximum);
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strictStringValue(
  value: unknown,
  maximum: number,
  requireNonEmpty = false
): string | null {
  if (typeof value !== "string" || value.length > maximum) return null;
  const normalized = value.trim();
  return requireNonEmpty && !normalized ? null : normalized;
}

function booleanValue(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function stringArrayValue(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const parsed = value.map((item) => strictStringValue(item, 200, true));
  return parsed.every((item): item is string => item !== null) ? parsed : null;
}

function stringRecordValue(value: unknown): Record<string, string> | null {
  const source = record(value);
  if (!source || !Object.values(source).every((item) => typeof item === "string")) return null;
  return source as Record<string, string>;
}

function numberRecordValue(value: unknown): Record<string, number> | null {
  const source = record(value);
  if (!source || !Object.values(source).every((item) => numberValue(item) !== null)) return null;
  return source as Record<string, number>;
}

function parseV3Candidate(value: unknown): DiscordV3ParticipationCandidate | null {
  const source = record(value);
  if (!source) return null;
  const deploymentId = strictStringValue(source.deployment_id, 64, true);
  const cardId = strictStringValue(source.character_card_id, 64, true);
  const eligible = booleanValue(source.eligible);
  const deterministicScore = numberValue(source.deterministic_score);
  const minimumScore = numberValue(source.minimum_score);
  const signals = numberRecordValue(source.deterministic_signals);
  const relevance = numberValue(source.raw_e5_relevance);
  const profileReady = booleanValue(source.profile_ready);
  const semanticPoints = numberValue(source.semantic_points);
  const finalEvidenceScore = numberValue(source.final_evidence_score);
  if (
    !deploymentId || !cardId || eligible === null || deterministicScore === null ||
    minimumScore === null || !signals || relevance === null || profileReady === null ||
    semanticPoints === null || finalEvidenceScore === null
  ) return null;
  return {
    deployment_id: deploymentId,
    character_card_id: cardId,
    eligible,
    deterministic_score: deterministicScore,
    minimum_score: minimumScore,
    deterministic_signals: signals,
    raw_e5_relevance: relevance,
    profile_ready: profileReady,
    semantic_points: semanticPoints,
    final_evidence_score: finalEvidenceScore
  };
}

function parseV3PlanItem(value: unknown): DiscordV3SpeakerPlanItem | null {
  const source = record(value);
  if (!source) return null;
  const deploymentId = strictStringValue(source.deployment_id, 64, true);
  const turnRole = strictStringValue(source.turn_role, 80, true);
  const reason = strictStringValue(source.reason, 240);
  const guidance = strictStringValue(source.guidance, 240);
  return deploymentId && turnRole && reason !== null && guidance !== null
    ? { deployment_id: deploymentId, turn_role: turnRole, reason, guidance }
    : null;
}

function parseV3Segment(value: unknown): DiscordV3ConversationSegment | null {
  const source = record(value);
  if (!source) return null;
  const id = strictStringValue(source.id, 200, true);
  const messageIds = stringArrayValue(source.message_ids);
  const participantIds = stringArrayValue(source.participant_ids);
  const kind = strictStringValue(source.kind, 80, true);
  const summary = strictStringValue(source.summary, 2_000);
  const threadId = strictStringValue(source.conversation_thread_id, 200);
  const membershipRelation = strictStringValue(source.membership_relation, 80);
  const membershipConfidence = numberValue(source.membership_confidence);
  const confidence = numberValue(source.confidence);
  const sourceName = strictStringValue(source.source, 120);
  if (!id || !messageIds || !participantIds || !kind || summary === null || threadId === null || membershipRelation === null || membershipConfidence === null || confidence === null || sourceName === null) return null;
  return { id, message_ids: messageIds, participant_ids: participantIds, kind, summary, conversation_thread_id: threadId, membership_relation: membershipRelation, membership_confidence: membershipConfidence, confidence, source: sourceName };
}

function parseV3ReplyTarget(value: unknown): DiscordV3ReplyTarget | null {
  const source = record(value);
  if (!source) return null;
  const deploymentId = strictStringValue(source.deployment_id, 64, true);
  const segmentId = strictStringValue(source.segment_id, 200, true);
  const threadId = strictStringValue(source.conversation_thread_id, 200);
  const score = numberValue(source.score);
  const reason = strictStringValue(source.reason, 240);
  const groundingLevel = strictStringValue(source.grounding_level, 80);
  const sufficiency = strictStringValue(source.context_sufficiency, 80);
  if (!deploymentId || !segmentId || threadId === null || score === null || reason === null || groundingLevel === null || sufficiency === null) return null;
  return { deployment_id: deploymentId, segment_id: segmentId, conversation_thread_id: threadId, score, reason, grounding_level: groundingLevel, context_sufficiency: sufficiency };
}

function parsedArray<T>(value: unknown, parser: (item: unknown) => T | null): T[] | null {
  if (!Array.isArray(value)) return null;
  const parsed = value.map(parser);
  return parsed.every((item): item is T => item !== null) ? parsed : null;
}

function parseV3ParticipationResult(value: unknown): DiscordV3ParticipationResult | null {
  const source = record(value);
  if (!source || source.resolver_version !== "conversation-intelligence-v3") return null;
  const available = booleanValue(source.available);
  const reason = strictStringValue(source.reason, 240, true);
  const model = strictStringValue(source.model, 240);
  const dimension = integerValue(source.dimension);
  const burstId = strictStringValue(source.burst_id, 80);
  const burstCount = integerValue(source.burst_message_count);
  const analysisChars = integerValue(source.analysis_chars);
  const candidates = parsedArray(source.candidates, parseV3Candidate);
  const segmentationUsed = booleanValue(source.segmentation_used);
  const segmentationSource = strictStringValue(source.segmentation_source, 240);
  const segments = parsedArray(source.conversation_segments, parseV3Segment);
  const targets = parsedArray(source.reply_targets, parseV3ReplyTarget);
  const speakerPlan = parsedArray(source.speaker_plan, parseV3PlanItem);
  const authoritative = booleanValue(source.speaker_plan_authoritative);
  const planReason = strictStringValue(source.participation_plan_reason, 240);
  const groundingLevel = strictStringValue(source.media_grounding_level, 80);
  const groundingReason = strictStringValue(source.media_grounding_reason, 240);
  const sufficiency = stringRecordValue(source.context_sufficiency);
  const utilityUsed = booleanValue(source.utility_used);
  if (available === null || !reason || model === null || dimension === null || burstId === null || burstCount === null || analysisChars === null || !candidates || segmentationUsed === null || segmentationSource === null || !segments || !targets || !speakerPlan || authoritative !== true || planReason === null || groundingLevel === null || groundingReason === null || !sufficiency || utilityUsed === null) return null;
  const candidateIds = new Set(candidates.map((item) => item.deployment_id));
  const segmentIds = new Set(segments.map((item) => item.id));
  const targetIds = new Set(targets.map((item) => item.deployment_id));
  const speakerIds = speakerPlan.map((item) => item.deployment_id);
  if (
    candidateIds.size !== candidates.length ||
    segmentIds.size !== segments.length ||
    targetIds.size !== targets.length ||
    new Set(speakerIds).size !== speakerIds.length ||
    targets.some((item) => !candidateIds.has(item.deployment_id) || !segmentIds.has(item.segment_id)) ||
    speakerIds.some((deploymentId) => !candidateIds.has(deploymentId) || !targetIds.has(deploymentId)) ||
    Object.keys(sufficiency).some((deploymentId) => !candidateIds.has(deploymentId))
  ) return null;
  return { resolver_version: "conversation-intelligence-v3", available, reason, model, dimension, burst_id: burstId, burst_message_count: burstCount, analysis_chars: analysisChars, candidates, segmentation_used: segmentationUsed, segmentation_source: segmentationSource, conversation_segments: segments, reply_targets: targets, speaker_plan: speakerPlan, speaker_plan_authoritative: true, participation_plan_reason: planReason, media_grounding_level: groundingLevel, media_grounding_reason: groundingReason, context_sufficiency: sufficiency, utility_used: utilityUsed };
}

export class RelayClient {
  private readonly attachmentCache = new Map<string, AttachmentCacheEntry>();
  private readonly attachmentTasks = new Map<string, Promise<DiscordMessageMedia>>();
  private readonly deploymentCache = new Map<string, DiscordDeployment>();

  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
    private readonly connectionId: string
  ) {}

  async listDeployments(): Promise<DiscordDeployment[]> {
    const query = new URLSearchParams({ connection_id: this.connectionId });
    const deployments = await this.request<DiscordDeployment[]>(
      `/api/connectors/discord/deployments?${query.toString()}`
    );
    const profiles = await this.request<Record<string, DiscordPortalParticipationProfile>>(
      `/api/smart-participation/connector-profiles?${query.toString()}`
    ).catch((): Record<string, DiscordPortalParticipationProfile> => ({}));
    const resolved = deployments.map((deployment) => ({
      ...deployment,
      smart_participation_profile: profiles[deployment.deployment_id] ?? null
    }));
    this.deploymentCache.clear();
    for (const deployment of resolved) {
      this.deploymentCache.set(deployment.deployment_id, deployment);
    }
    return resolved;
  }

  async getSmartParticipationRuntime(): Promise<DiscordConversationBurstRuntimeConfig> {
    const query = new URLSearchParams({ connection_id: this.connectionId });
    return this.request<DiscordConversationBurstRuntimeConfig>(
      `/api/smart-participation/connector-runtime?${query.toString()}`
    );
  }

  async syncServerCatalog(
    payload: Omit<DiscordServerCatalogSync, "connection_id">
  ): Promise<void> {
    await this.request<void>("/api/connectors/discord/server-catalog", {
      method: "PUT",
      body: JSON.stringify({ connection_id: this.connectionId, ...payload })
    });
  }

  async registerWebhook(
    payload: Omit<DiscordWebhookRegistration, "connection_id">
  ): Promise<DiscordWebhookRegistrationResult> {
    return this.request<DiscordWebhookRegistrationResult>(
      "/api/connectors/discord/webhooks",
      {
        method: "PUT",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async reportWebhookStatus(payload: DiscordWebhookStatusReport): Promise<void> {
    await this.request<void>("/api/connectors/discord/webhooks/status", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  async registerMessageRoutes(
    payload: Omit<DiscordMessageRouteRegistration, "connection_id">
  ): Promise<void> {
    await this.request<void>("/api/connectors/discord/message-routes", {
      method: "PUT",
      body: JSON.stringify({ connection_id: this.connectionId, ...payload })
    });
  }

  async resolveMessageRoute(messageId: string): Promise<DiscordMessageRouteView | null> {
    const query = new URLSearchParams({
      connection_id: this.connectionId,
      message_id: messageId
    });
    const result = await this.request<DiscordMessageRouteLookup>(
      `/api/connectors/discord/message-routes?${query.toString()}`
    );
    return result.route;
  }

  async reportEvents(events: DiscordConnectorEvent[]): Promise<void> {
    if (!events.length) return;
    await this.request<void>("/api/connectors/discord/events", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, events })
    });
  }

  async heartbeat(payload: Omit<ConnectorHeartbeat, "connection_id">): Promise<void> {
    await this.request<void>("/api/connectors/discord/heartbeat", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, ...payload })
    });
  }

  async resolveExpression(
    payload: DiscordExpressionResolveRequest
  ): Promise<DiscordExpressionContent> {
    return this.request<DiscordExpressionContent>(
      "/api/connectors/discord/expressions/resolve",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async retrieveExpressions(
    payload: DiscordExpressionRetrieveRequest
  ): Promise<DiscordExpressionRetrieval> {
    return this.request<DiscordExpressionRetrieval>(
      "/api/connectors/discord/expressions/retrieve",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async reportExpressionNode(
    runId: string,
    payload: DiscordExpressionNodeReport
  ): Promise<void> {
    await this.request<void>(
      `/api/connectors/discord/expressions/runs/${runId}/nodes`,
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async resolveSticker(
    payload: DiscordStickerObservation
  ): Promise<DiscordStickerContent> {
    return this.request<DiscordStickerContent>("/api/connectors/discord/stickers/resolve", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, ...payload })
    });
  }

  async claimInteraction(
    payload: DiscordInteractionClaimRequest
  ): Promise<DiscordInteractionClaim> {
    return this.request<DiscordInteractionClaim>(
      "/api/connectors/discord/interaction-sessions/claim",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async completeInteractionRun(
    runId: string,
    payload: DiscordInteractionRunComplete
  ): Promise<void> {
    await this.request<void>(
      `/api/connectors/discord/interaction-sessions/runs/${runId}`,
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async resolveSmartParticipation(
    payload: DiscordSmartParticipationScoreRequest
  ): Promise<DiscordV3ParticipationResult> {
    const resolved = await this.request<unknown>("/api/smart-participation/resolve", {
      method: "POST",
      body: JSON.stringify({
            connection_id: this.connectionId,
            guild_id: payload.guild_id ?? "",
            channel_id: payload.channel_id ?? "",
            thread_id: payload.thread_id ?? "",
            message_id: payload.message_id ?? "",
            author_id: payload.author_id ?? "",
            reply_to_message_id: payload.reply_to_message_id ?? "",
            message: payload.message,
            burst_id: payload.burst_id ?? "",
            burst_messages: payload.burst_messages ?? [],
            minimum_margin: payload.minimum_margin ?? 2,
            max_participants: payload.max_participants ?? 2,
            channel_cooldown_seconds: payload.channel_cooldown_seconds ?? 45,
            window_seconds: payload.window_seconds ?? 600,
            max_replies_per_window: payload.max_replies_per_window ?? 3,
            media_descriptors: payload.media_descriptors ?? [],
            media_dependency: payload.media_dependency ?? "none",
            media_dependency_locked: payload.media_dependency_locked ?? false,
            candidates: payload.deployment_ids.map((deploymentId) => {
              const runtime = payload.candidate_preflight?.find(
                (candidate) => candidate.deployment_id === deploymentId
              );
              return {
                deployment_id: deploymentId,
                eligible: runtime?.eligible ?? true,
                deterministic_score: runtime?.deterministic_score ?? 0,
                minimum_score: runtime?.minimum_score ?? 0,
                signals: runtime?.signals ?? {}
              };
            })
          })
    });
    const parsed = parseV3ParticipationResult(resolved);
    if (!parsed) {
      throw new Error("Character Relay returned an invalid conversation-intelligence-v3 resolve response.");
    }
    return parsed;
  }

  async recentSmartParticipationSpeaker(input: {
    guild_id: string;
    channel_id: string;
    thread_id: string;
    maximum_age_seconds: number;
    allowed_deployment_ids: string[];
  }): Promise<string> {
    const result = await this.request<{ deployment_id: string }>(
      "/api/smart-participation/recent-speaker",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...input })
      }
    );
    return result.deployment_id ?? "";
  }

  async observeSmartParticipationOutcome(input: {
    guild_id: string;
    channel_id: string;
    thread_id: string;
    message_id: string;
    burst_id: string;
    author_id: string;
    author_display_name: string;
    author_global_name: string;
    author_username: string;
    author_avatar_url: string;
    author_is_bot: boolean;
    reply_to_message_id: string;
    selected_deployment_ids: string[];
    candidate_deployment_ids: string[];
  }): Promise<void> {
    await this.request<void>("/api/smart-participation/observe", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, ...input })
    });
  }

  async claimSocialTurnOperation(
    payload: DiscordSocialOperationClaimRequest
  ): Promise<DiscordSocialOperationClaim> {
    return this.request<DiscordSocialOperationClaim>(
      "/api/connectors/discord/social-turns/operations/claim",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      },
      true
    );
  }

  async listPendingSocialTurnOperations(): Promise<DiscordPendingSocialOperation[]> {
    const query = new URLSearchParams({ connection_id: this.connectionId });
    return this.request<DiscordPendingSocialOperation[]>(
      `/api/connectors/discord/social-turns/operations/pending?${query.toString()}`
    );
  }

  async cancelSocialTurnOperation(payload: {
    operation_id: string;
    guild_id: string;
    channel_id: string;
    thread_id: string;
    superseding_message_id: string;
    reason?: string;
  }): Promise<{ canceled: boolean; status: string; reason: string }> {
    return this.request<{ canceled: boolean; status: string; reason: string }>(
      "/api/connectors/discord/social-turns/operations/cancel",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async claimSocialTurnDelivery(
    payload: DiscordDeliveryClaimRequest
  ): Promise<DiscordDeliveryClaim> {
    return this.request<DiscordDeliveryClaim>(
      "/api/connectors/discord/social-turns/delivery/claim",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      },
      true
    );
  }

  async acknowledgeSocialTurnDelivery(
    payload: DiscordDeliveryAckRequest
  ): Promise<DiscordSocialOperationClaim> {
    return this.request<DiscordSocialOperationClaim>(
      "/api/connectors/discord/social-turns/delivery/ack",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      },
      true
    );
  }

  async markSocialTurnDeliveryUncertain(
    payload: DiscordDeliveryFailureRequest
  ): Promise<void> {
    await this.request<void>(
      "/api/connectors/discord/social-turns/delivery/uncertain",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async claimCharacterTurnDelivery(
    payload: DiscordDeliveryClaimRequest
  ): Promise<DiscordDeliveryClaim> {
    return this.request<DiscordDeliveryClaim>(
      "/api/connectors/discord/messages/delivery/claim",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      },
      true
    );
  }

  async acknowledgeCharacterTurnDelivery(payload: {
    operation_id: string;
    step_id: string;
    claim_nonce: string;
    sent_message_ids: string[];
  }): Promise<void> {
    await this.request<void>(
      "/api/connectors/discord/messages/delivery/ack",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      },
      true
    );
  }

  async markCharacterTurnDeliveryUncertain(
    payload: DiscordDeliveryFailureRequest
  ): Promise<void> {
    await this.request<void>(
      "/api/connectors/discord/messages/delivery/uncertain",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      },
      true
    );
  }

  async resolvePlannerMedia(payload: {
    message_id: string;
    guild_id: string;
    channel_id: string;
    thread_id: string;
    text: string;
    burst_media_message_ids?: string[];
  }): Promise<DiscordPlannerMediaResult> {
    const channelId = payload.thread_id || payload.channel_id;
    const media = await this.discordMedia(channelId, payload.message_id);
    return this.request<DiscordPlannerMediaResult>(
      "/api/connectors/discord/media/describe",
      {
        method: "POST",
        body: JSON.stringify({
          connection_id: this.connectionId,
          ...payload,
          attachments: media.attachments,
          embeds: media.embeds
        })
      }
    );
  }

  async processSocialTurnStep(
    request: Omit<DiscordSocialTurnStepRequest, "payload"> & {
      payload: Omit<DiscordInboundMessage, "connection_id">;
    }
  ): Promise<DiscordSocialTurnStepReply> {
    const payload = await this.withDiscordMedia(request.payload);
    return this.request<DiscordSocialTurnStepReply>(
      "/api/connectors/discord/social-turns/step",
      {
        method: "POST",
        body: JSON.stringify({
          ...request,
          payload: { connection_id: this.connectionId, ...payload }
        })
      }
    );
  }

  async processMessage(
    payload: Omit<DiscordInboundMessage, "connection_id">
  ): Promise<DiscordReply> {
    const enriched = await this.withDiscordMedia(payload);
    return this.request<DiscordReply>("/api/connectors/discord/messages", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, ...enriched })
    });
  }

  private async withDiscordMedia<T extends Omit<DiscordInboundMessage, "connection_id">>(
    payload: T
  ): Promise<T & DiscordMessageMedia> {
    const fallbackReplyId = payload.reply_to_message_id ?? "";
    if (payload.author_is_bot) {
      return {
        ...payload,
        attachments: [],
        embeds: [],
        reply_to_message_id: fallbackReplyId
      };
    }
    const channelId = payload.thread_id || payload.channel_id;
    if (!channelId || !payload.message_id) {
      return {
        ...payload,
        attachments: [],
        embeds: [],
        reply_to_message_id: fallbackReplyId
      };
    }
    const media = await this.discordMedia(channelId, payload.message_id);
    return {
      ...payload,
      ...media,
      reply_to_message_id: media.reply_to_message_id || fallbackReplyId
    };
  }

  private async discordMedia(
    channelId: string,
    messageId: string
  ): Promise<DiscordMessageMedia> {
    const token = process.env.DISCORD_BOT_TOKEN?.trim();
    if (!token) return { attachments: [], embeds: [], reply_to_message_id: "" };
    const cacheKey = `${channelId}:${messageId}`;
    const now = Date.now();
    const cached = this.attachmentCache.get(cacheKey);
    if (cached && cached.expiresAt > now) {
      return {
        attachments: cached.attachments,
        embeds: cached.embeds,
        reply_to_message_id: cached.reply_to_message_id
      };
    }

    let task = this.attachmentTasks.get(cacheKey);
    if (!task) {
      task = this.fetchDiscordMedia(channelId, messageId, token);
      this.attachmentTasks.set(cacheKey, task);
    }
    try {
      const media = await task;
      this.attachmentCache.set(cacheKey, {
        expiresAt: now + ATTACHMENT_CACHE_MS,
        ...media
      });
      if (this.attachmentCache.size > 1_000) {
        for (const [key, value] of this.attachmentCache.entries()) {
          if (value.expiresAt <= now) this.attachmentCache.delete(key);
        }
      }
      return media;
    } finally {
      if (this.attachmentTasks.get(cacheKey) === task) {
        this.attachmentTasks.delete(cacheKey);
      }
    }
  }

  private async fetchDiscordMedia(
    channelId: string,
    messageId: string,
    token: string
  ): Promise<DiscordMessageMedia> {
    try {
      const response = await fetch(
        `${DISCORD_API_BASE}/channels/${channelId}/messages/${messageId}`,
        {
          signal: AbortSignal.timeout(8_000),
          headers: {
            Authorization: `Bot ${token}`,
            Accept: "application/json"
          }
        }
      );
      if (!response.ok) {
        return { attachments: [], embeds: [], reply_to_message_id: "" };
      }
      const body = (await response.json()) as {
        attachments?: unknown;
        embeds?: unknown;
        message_reference?: unknown;
      };
      const attachments = Array.isArray(body.attachments)
        ? body.attachments
            .slice(0, 10)
            .map((raw): ConnectorAttachment | null => {
              if (!raw || typeof raw !== "object") return null;
              const value = raw as DiscordMessageApiAttachment;
              const attachmentId = stringValue(value.id, 200);
              const url = stringValue(value.url, 3_000);
              if (!attachmentId || !url) return null;
              return {
                attachment_id: attachmentId,
                url,
                proxy_url: stringValue(value.proxy_url, 3_000),
                filename: stringValue(value.filename, 255) || "attachment",
                content_type: stringValue(value.content_type, 160),
                size_bytes: integerValue(value.size),
                width: integerValue(value.width),
                height: integerValue(value.height)
              };
            })
            .filter((item): item is ConnectorAttachment => item !== null)
        : [];
      const embeds = Array.isArray(body.embeds)
        ? body.embeds
            .slice(0, 10)
            .map((raw): ConnectorEmbed | null => {
              if (!raw || typeof raw !== "object") return null;
              const value = raw as DiscordMessageApiEmbed;
              const title = stringValue(value.title, 500);
              const description = stringValue(value.description, 2_000);
              const url = stringValue(value.url, 3_000);
              const providerName = nestedString(value.provider, "name", 200);
              const authorName = nestedString(value.author, "name", 200);
              if (!title && !description && !url && !providerName && !authorName) return null;
              return {
                embed_type: stringValue(value.type, 80),
                url,
                title,
                description,
                provider_name: providerName,
                author_name: authorName
              };
            })
            .filter((item): item is ConnectorEmbed => item !== null)
        : [];
      return {
        attachments,
        embeds,
        reply_to_message_id: nestedString(body.message_reference, "message_id", 200)
      };
    } catch {
      return { attachments: [], embeds: [], reply_to_message_id: "" };
    }
  }

  private async request<T>(
    path: string,
    init?: RequestInit,
    retryable = init?.method === "GET"
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let response: Response | undefined;
    let lastNetworkError: unknown;

    const attempts = retryable ? RETRY_DELAYS_MS.length : 1;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const wait = RETRY_DELAYS_MS[attempt];
      if (wait) await delay(wait);

      try {
        response = await fetch(url, {
          ...init,
          signal: AbortSignal.timeout(45_000),
          headers: {
            Authorization: `Bearer ${this.token}`,
            "Content-Type": "application/json",
            ...(init?.headers ?? {})
          }
        });
      } catch (error) {
        lastNetworkError = error;
        if (attempt < attempts - 1) continue;
        throw new Error(
          `Unable to reach Character Relay at ${url}: ${errorDetail(error)}`,
          { cause: error }
        );
      }

      if (
        TRANSIENT_STATUS_CODES.has(response.status) &&
        attempt < attempts - 1
      ) {
        continue;
      }
      break;
    }

    if (!response) {
      throw new Error(
        `Unable to reach Character Relay at ${url}: ${errorDetail(lastNetworkError)}`,
        { cause: lastNetworkError }
      );
    }
    if (!response.ok) {
      const body = await response.text();
      let detail = body;
      try {
        const parsed = JSON.parse(body) as { detail?: unknown };
        if (typeof parsed.detail === "string") detail = parsed.detail;
      } catch {
        // Preserve the raw body.
      }
      throw new Error(
        `Character Relay returned HTTP ${response.status} from ${url}: ${detail}`
      );
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
}
