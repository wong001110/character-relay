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
  DiscordStickerContent,
  DiscordStickerObservation,
  DiscordWebhookRegistration,
  DiscordWebhookRegistrationResult,
  DiscordWebhookStatusReport
} from "./types.js";
import type { DiscordPortalParticipationProfile } from "./smartParticipation.js";

const RETRY_DELAYS_MS = [0, 1_000, 2_000, 4_000, 8_000, 15_000];
const TRANSIENT_STATUS_CODES = new Set([502, 503, 504]);

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

export class RelayClient {
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
    ).catch(() => ({}));
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

  async processMessage(
    payload: Omit<DiscordInboundMessage, "connection_id">
  ): Promise<DiscordReply> {
    return this.request<DiscordReply>("/api/connectors/discord/messages", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, ...payload })
    });
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