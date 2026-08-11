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

export interface DiscordSemanticParticipationCandidate {
  deployment_id: string;
  character_card_id: string;
  semantic_relevance: number;
  profile_ready: boolean;
}

export interface DiscordSemanticParticipationResult {
  available: boolean;
  reason: string;
  model: string;
  dimension: number;
  candidates: DiscordSemanticParticipationCandidate[];
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

export class RelayClient {
  private readonly attachmentCache = new Map<string, AttachmentCacheEntry>();
  private readonly attachmentTasks = new Map<string, Promise<DiscordMessageMedia>>();

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
    return deployments.map((deployment) => ({
      ...deployment,
      smart_participation_profile: profiles[deployment.deployment_id] ?? null
    }));
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

  async scoreSmartParticipation(payload: {
    message: string;
    deployment_ids: string[];
  }): Promise<DiscordSemanticParticipationResult> {
    return this.request<DiscordSemanticParticipationResult>(
      "/api/smart-participation/semantic-score",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async claimSocialTurnOperation(
    payload: DiscordSocialOperationClaimRequest
  ): Promise<DiscordSocialOperationClaim> {
    return this.request<DiscordSocialOperationClaim>(
      "/api/connectors/discord/social-turns/operations/claim",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async listPendingSocialTurnOperations(): Promise<DiscordPendingSocialOperation[]> {
    const query = new URLSearchParams({ connection_id: this.connectionId });
    return this.request<DiscordPendingSocialOperation[]>(
      `/api/connectors/discord/social-turns/operations/pending?${query.toString()}`
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
      }
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
      }
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
    if (payload.author_is_bot) return { ...payload, attachments: [], embeds: [] };
    const channelId = payload.thread_id || payload.channel_id;
    if (!channelId || !payload.message_id) {
      return { ...payload, attachments: [], embeds: [] };
    }
    const media = await this.discordMedia(channelId, payload.message_id);
    return { ...payload, ...media };
  }

  private async discordMedia(
    channelId: string,
    messageId: string
  ): Promise<DiscordMessageMedia> {
    const token = process.env.DISCORD_BOT_TOKEN?.trim();
    if (!token) return { attachments: [], embeds: [] };
    const cacheKey = `${channelId}:${messageId}`;
    const now = Date.now();
    const cached = this.attachmentCache.get(cacheKey);
    if (cached && cached.expiresAt > now) {
      return { attachments: cached.attachments, embeds: cached.embeds };
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
      if (!response.ok) return { attachments: [], embeds: [] };
      const body = (await response.json()) as {
        attachments?: unknown;
        embeds?: unknown;
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
      return { attachments, embeds };
    } catch {
      return { attachments: [], embeds: [] };
    }
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let response: Response | undefined;
    let lastNetworkError: unknown;

    for (let attempt = 0; attempt < RETRY_DELAYS_MS.length; attempt += 1) {
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
        if (attempt < RETRY_DELAYS_MS.length - 1) continue;
        throw new Error(
          `Unable to reach Character Relay at ${url}: ${errorDetail(error)}`,
          { cause: error }
        );
      }

      if (
        TRANSIENT_STATUS_CODES.has(response.status) &&
        attempt < RETRY_DELAYS_MS.length - 1
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
