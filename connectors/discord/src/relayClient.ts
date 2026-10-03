import type { WebRoom, WebClaim, WebAck } from "./webRoomBridge.js";
import type { DraftPreflightRequest,DraftPreflightResult } from "./draftPreflight.js";
import type { DiscordDeliveryAckRequest,DiscordDeliveryClaim,DiscordDeliveryClaimRequest,DiscordDeliveryFailureRequest,DiscordPendingSocialOperation,DiscordSocialOperationClaim,DiscordSocialOperationClaimRequest } from "./durableRuntime.js";
import type { RoomEvidence,RoomRoutingRequest,RoomRoutingResult } from "./roomEvidence.js";
import { consumeTurnJob,TurnJobTerminalError,type TurnJobConsumeOptions,type TurnJobTransport } from "./turnJobs.js";
import type { ConnectorHeartbeat,DiscordConnectorEvent,DiscordDeployment,DiscordExpressionContent,DiscordExpressionResolveRequest,DiscordInboundMessage,DiscordMessageRouteLookup,DiscordMessageRouteRegistration,DiscordMessageRouteView,DiscordReply,DiscordServerCatalogSync,DiscordSocialTurnStepReply,DiscordSocialTurnStepRequest,DiscordStickerContent,DiscordStickerObservation,DiscordTurnJobDescriptor,DiscordTurnJobView,DiscordWebhookRegistration,DiscordWebhookRegistrationResult,DiscordWebhookStatusReport } from "./types.js";
export interface DiscordRoomBufferConfig {
    enabled: boolean;
    quiet_window_ms: number;
    max_wait_ms: number;
    max_messages: number;
    max_characters: number;
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
const RETRY_DELAYS_MS = [0, 1000, 2000, 4000, 8000, 15000];
const TRANSIENT_STATUS_CODES = new Set([502, 503, 504]);
const DISCORD_API_BASE = "https://discord.com/api/v10";
const ATTACHMENT_CACHE_MS = 5 * 60 * 1000;
const TURN_JOB_REQUEST_TIMEOUT_MS = 8000;
export interface TurnJobProgressOptions {
    onProgress?: (text: string) => Promise<void>;
    onProgressDeliveryError?: (error: unknown) => void;
}
function delay(milliseconds: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
function errorDetail(error: unknown): string {
    if (!(error instanceof Error))
        return String(error);
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
    if (!value || typeof value !== "object" || Array.isArray(value))
        return "";
    return stringValue((value as Record<string, unknown>)[key], maximum);
}
function record(value: unknown): Record<string, unknown> | null {
    return value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : null;
}
export class RelayClient {
    private readonly attachmentCache = new Map<string, AttachmentCacheEntry>();
    private readonly attachmentTasks = new Map<string, Promise<DiscordMessageMedia>>();
    private readonly deploymentCache = new Map<string, DiscordDeployment>();
    private readonly turnJobAbortController = new AbortController();
    private recoverableTurnJobCursor: string | null = null;
    constructor(private readonly baseUrl: string, private readonly token: string, private readonly connectionId: string, private readonly turnJobTimeoutMs = 330000) { }
    async webRooms(): Promise<WebRoom[]> {
        return this.request(`/api/connectors/discord/web-chat/rooms?${new URLSearchParams({connection_id: this.connectionId})}`, {method: "GET"}, false, 8000);
    }
    async registerWebRoomWebhook(roomId: string, webhookId: string): Promise<void> {
        return this.request(`/api/connectors/discord/web-chat/rooms/${encodeURIComponent(roomId)}/webhook`, {method: "PUT", body: JSON.stringify({connection_id: this.connectionId, webhook_id: webhookId})}, false, 8000);
    }
    async claimWebMessage(roomId: string, nonce: string): Promise<WebClaim | null> {
        return this.request(`/api/connectors/discord/web-chat/rooms/${encodeURIComponent(roomId)}/claim`, {method: "POST", body: JSON.stringify({connection_id: this.connectionId, claim_nonce: nonce})}, false, 8000);
    }
    async preflightWebMessage(claim: WebClaim): Promise<{allowed: boolean}> {
        return this.request(`/api/connectors/discord/web-chat/outbox/${encodeURIComponent(claim.id)}/preflight`, {method: "POST", body: JSON.stringify({connection_id: this.connectionId, claim_nonce: claim.claim_nonce})}, false, 8000);
    }
    async acknowledgeWebMessage(claim: WebClaim, result: WebAck): Promise<unknown> {
        return this.request(`/api/connectors/discord/web-chat/outbox/${encodeURIComponent(claim.id)}/ack`, {method: "POST", body: JSON.stringify({...result, connection_id: this.connectionId, claim_nonce: claim.claim_nonce})}, false, 8000);
    }
    async fetchWebAttachment(claim: WebClaim, attachmentId: string): Promise<Buffer> {
        const query = new URLSearchParams({
            connection_id: this.connectionId,
            claim_nonce: claim.claim_nonce
        });
        const url = `${this.baseUrl}/api/connectors/discord/web-chat/outbox/${encodeURIComponent(claim.id)}/attachments/${encodeURIComponent(attachmentId)}?${query.toString()}`;
        let response: Response;
        try {
            response = await fetch(url, {
                headers: {Authorization: `Bearer ${this.token}`},
                signal: AbortSignal.timeout(8000)
            });
        }
        catch (error) {
            throw Object.assign(
                new Error(`Unable to fetch Web Room attachment from Character Relay: ${errorDetail(error)}`),
                {status: 422}
            );
        }
        if (!response.ok) {
            throw Object.assign(
                new Error(`Character Relay rejected Web Room attachment with HTTP ${response.status}`),
                {status: 422}
            );
        }
        const declared = Number(response.headers.get("content-length") ?? 0);
        if (declared > 8 * 1024 * 1024) {
            throw Object.assign(new Error("web_attachment_too_large"), {status: 422});
        }
        const content = Buffer.from(await response.arrayBuffer());
        if (content.length > 8 * 1024 * 1024) {
            throw Object.assign(new Error("web_attachment_too_large"), {status: 422});
        }
        return content;
    }
    async webSource(messageId: string): Promise<WebClaim | null> {
        return this.request(`/api/connectors/discord/web-chat/source/${encodeURIComponent(messageId)}?${new URLSearchParams({connection_id: this.connectionId})}`, {method: "GET"}, false, 8000);
    }
    async webDispatch(): Promise<WebClaim[]> {
        return this.request(`/api/connectors/discord/web-chat/dispatch?${new URLSearchParams({connection_id: this.connectionId})}`, {method: "GET"}, false, 8000);
    }
    async finishWebDispatch(claim: WebClaim, outcome: "processed" | "failed" = "processed"): Promise<void> {
        return this.request(`/api/connectors/discord/web-chat/outbox/${encodeURIComponent(claim.id)}/dispatched`, {method: "POST", body: JSON.stringify({connection_id: this.connectionId, claim_nonce: claim.claim_nonce, outcome})}, false, 8000);
    }
    async listDeployments(): Promise<DiscordDeployment[]> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        const deployments = await this.request<DiscordDeployment[]>(`/api/connectors/discord/deployments?${query.toString()}`);
        this.deploymentCache.clear();
        for (const deployment of deployments) {
            this.deploymentCache.set(deployment.deployment_id, deployment);
        }
        return deployments;
    }
    async getRoomBufferConfig(): Promise<DiscordRoomBufferConfig> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        return this.request<DiscordRoomBufferConfig>(`/api/connectors/discord/rooms/runtime?${query.toString()}`);
    }
    async syncServerCatalog(payload: Omit<DiscordServerCatalogSync, "connection_id">): Promise<void> {
        await this.request<void>("/api/connectors/discord/server-catalog", {
            method: "PUT",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        });
    }
    async registerWebhook(payload: Omit<DiscordWebhookRegistration, "connection_id">): Promise<DiscordWebhookRegistrationResult> {
        return this.request<DiscordWebhookRegistrationResult>("/api/connectors/discord/webhooks", {
            method: "PUT",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        });
    }
    async reportWebhookStatus(payload: DiscordWebhookStatusReport): Promise<void> {
        await this.request<void>("/api/connectors/discord/webhooks/status", {
            method: "POST",
            body: JSON.stringify(payload)
        });
    }
    async registerMessageRoutes(payload: Omit<DiscordMessageRouteRegistration, "connection_id">): Promise<void> {
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
        const result = await this.request<DiscordMessageRouteLookup>(`/api/connectors/discord/message-routes?${query.toString()}`);
        return result.route;
    }
    async reportEvents(events: DiscordConnectorEvent[]): Promise<void> {
        if (!events.length)
            return;
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
    async resolveExpression(payload: DiscordExpressionResolveRequest): Promise<DiscordExpressionContent> {
        return this.request<DiscordExpressionContent>("/api/connectors/discord/expressions/resolve", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        });
    }
    async resolveSticker(payload: DiscordStickerObservation): Promise<DiscordStickerContent> {
        return this.request<DiscordStickerContent>("/api/connectors/discord/stickers/resolve", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        });
    }
    async preflightDraft(body: DraftPreflightRequest): Promise<DraftPreflightResult> {
        return this.request("/api/connectors/discord/rooms/drafts/preflight", {
            method: "POST", body: JSON.stringify({ ...body, connection_id: this.connectionId })
        });
    }
    async observeRoom(evidence: RoomEvidence): Promise<{
        accepted: boolean;
        revision: number;
    }> {
        return this.request("/api/connectors/discord/rooms/events", {
            method: "POST", body: JSON.stringify({ ...evidence, connection_id: this.connectionId })
        });
    }
    async resolveRoom(input: RoomRoutingRequest): Promise<RoomRoutingResult> {
        return this.request("/api/connectors/discord/rooms/resolve", {
            method: "POST", body: JSON.stringify({ ...input, connection_id: this.connectionId })
        });
    }
    async claimSocialTurnOperation(payload: DiscordSocialOperationClaimRequest): Promise<DiscordSocialOperationClaim> {
        return this.request<DiscordSocialOperationClaim>("/api/connectors/discord/social-turns/operations/claim", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        }, true);
    }
    async listPendingSocialTurnOperations(): Promise<DiscordPendingSocialOperation[]> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        return this.request<DiscordPendingSocialOperation[]>(`/api/connectors/discord/social-turns/operations/pending?${query.toString()}`);
    }
    async cancelSocialTurnOperation(payload: {
        operation_id: string;
        guild_id: string;
        channel_id: string;
        thread_id: string;
        superseding_message_id: string;
        reason?: string;
    }): Promise<{
        canceled: boolean;
        status: string;
        reason: string;
    }> {
        return this.request<{
            canceled: boolean;
            status: string;
            reason: string;
        }>("/api/connectors/discord/social-turns/operations/cancel", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        });
    }
    async claimSocialTurnDelivery(payload: DiscordDeliveryClaimRequest): Promise<DiscordDeliveryClaim> {
        return this.request<DiscordDeliveryClaim>("/api/connectors/discord/social-turns/delivery/claim", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        }, true);
    }
    async acknowledgeSocialTurnDelivery(payload: DiscordDeliveryAckRequest): Promise<DiscordSocialOperationClaim> {
        return this.request<DiscordSocialOperationClaim>("/api/connectors/discord/social-turns/delivery/ack", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        }, true);
    }
    async markSocialTurnDeliveryUncertain(payload: DiscordDeliveryFailureRequest): Promise<void> {
        await this.request<void>("/api/connectors/discord/social-turns/delivery/uncertain", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        });
    }
    async claimCharacterTurnDelivery(payload: DiscordDeliveryClaimRequest): Promise<DiscordDeliveryClaim> {
        return this.request<DiscordDeliveryClaim>("/api/connectors/discord/messages/delivery/claim", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        }, true);
    }
    async acknowledgeCharacterTurnDelivery(payload: {
        operation_id: string;
        step_id: string;
        claim_nonce: string;
        sent_message_ids: string[];
        applied?: boolean;
    }): Promise<void> {
        await this.request<void>("/api/connectors/discord/messages/delivery/ack", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        }, true);
    }
    async markCharacterTurnDeliveryUncertain(payload: DiscordDeliveryFailureRequest): Promise<void> {
        await this.request<void>("/api/connectors/discord/messages/delivery/uncertain", {
            method: "POST",
            body: JSON.stringify({ connection_id: this.connectionId, ...payload })
        }, true);
    }
    async processSocialTurnStep(request: Omit<DiscordSocialTurnStepRequest, "payload"> & {
        payload: Omit<DiscordInboundMessage, "connection_id">;
    }, options?: TurnJobProgressOptions): Promise<DiscordSocialTurnStepReply> {
        const payload = await this.withDiscordMedia(request.payload);
        const body = {
            ...request,
            payload: { connection_id: this.connectionId, ...payload }
        };
        if (options?.onProgress) {
            const view = await this.submitAndConsumeTurnJob("/api/connectors/discord/social-turns/jobs", body, {
                onProgress: options.onProgress,
                ...(options.onProgressDeliveryError
                    ? { onProgressDeliveryError: options.onProgressDeliveryError }
                    : {})
            });
            if (!view.social_step) {
                throw new TurnJobTerminalError("failed", "missing_social_step", view.job_id);
            }
            return view.social_step;
        }
        return this.request<DiscordSocialTurnStepReply>("/api/connectors/discord/social-turns/step", {
            method: "POST",
            body: JSON.stringify(body)
        });
    }
    stopTurnJobs(): void {
        this.turnJobAbortController.abort();
    }
    async listRecoverableTurnJobs(limit = 50): Promise<DiscordTurnJobDescriptor[]> {
        const boundedLimit = Number.isFinite(limit)
            ? Math.max(1, Math.min(50, Math.floor(limit)))
            : 50;
        const query = new URLSearchParams({
            connection_id: this.connectionId,
            limit: String(boundedLimit)
        });
        if (this.recoverableTurnJobCursor) {
            query.set("after_job_id", this.recoverableTurnJobCursor);
        }
        const result = await this.request<{
            items: DiscordTurnJobDescriptor[];
            next_cursor?: string | null;
        }>(`/api/connectors/discord/turn-jobs?${query.toString()}`);
        this.recoverableTurnJobCursor = result.next_cursor ?? null;
        return result.items;
    }
    async consumeTerminalTurnJob(jobId: string): Promise<void> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        await this.request<void>(`/api/connectors/discord/turn-jobs/${encodeURIComponent(jobId)}/consume?${query.toString()}`, { method: "POST" }, false, TURN_JOB_REQUEST_TIMEOUT_MS);
    }
    async cancelTurnJobs(input: {
        deployment_id: string;
        guild_id: string;
        channel_id: string;
        thread_id: string;
        category_id: string;
        source_message_id: string;
        source_author_id: string;
        reason: "user_cancelled" | "user_replaced";
    }): Promise<string[]> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        return this.request<string[]>(`/api/connectors/discord/turn-jobs/cancel?${query.toString()}`, { method: "POST", body: JSON.stringify(input) }, false, TURN_JOB_REQUEST_TIMEOUT_MS);
    }
    async resumeMessageTurnJob(jobId: string, options: Required<Pick<TurnJobProgressOptions, "onProgress">> & TurnJobProgressOptions): Promise<DiscordReply> {
        const signal = this.turnJobAbortController.signal;
        const view = await this.getTurnJob(jobId, signal);
        const completed = await this.consumeExistingTurnJob(view, options, signal);
        if (!completed.reply) {
            throw new TurnJobTerminalError("failed", "missing_reply", completed.job_id);
        }
        return completed.reply;
    }
    async processMessage(payload: Omit<DiscordInboundMessage, "connection_id">, options?: TurnJobProgressOptions): Promise<DiscordReply> {
        const enriched = await this.withDiscordMedia(payload);
        const body = { connection_id: this.connectionId, ...enriched };
        if (options?.onProgress) {
            const view = await this.submitAndConsumeTurnJob("/api/connectors/discord/messages/jobs", body, {
                onProgress: options.onProgress,
                ...(options.onProgressDeliveryError
                    ? { onProgressDeliveryError: options.onProgressDeliveryError }
                    : {})
            });
            if (!view.reply) {
                throw new TurnJobTerminalError("failed", "missing_reply", view.job_id);
            }
            return view.reply;
        }
        return this.request<DiscordReply>("/api/connectors/discord/messages", {
            method: "POST",
            body: JSON.stringify(body)
        });
    }
    private async submitAndConsumeTurnJob(path: string, body: Record<string, unknown>, options: Required<Pick<TurnJobProgressOptions, "onProgress">> & TurnJobProgressOptions): Promise<DiscordTurnJobView> {
        const signal = this.turnJobAbortController.signal;
        const initial = await this.request<DiscordTurnJobView>(path, { method: "POST", body: JSON.stringify(body), signal }, false, TURN_JOB_REQUEST_TIMEOUT_MS);
        return this.consumeExistingTurnJob(initial, options, signal);
    }
    private async consumeExistingTurnJob(initial: DiscordTurnJobView, options: Required<Pick<TurnJobProgressOptions, "onProgress">> & TurnJobProgressOptions, signal: AbortSignal): Promise<DiscordTurnJobView> {
        const transport: TurnJobTransport = {
            poll: (jobId) => this.getTurnJob(jobId, signal),
            claimProgress: (jobId, nonce) => this.claimTurnJobProgress(jobId, nonce, signal),
            acknowledgeProgress: (jobId, progressId, nonce) => this.acknowledgeTurnJobProgress(jobId, progressId, nonce, signal)
        };
        const consumeOptions: TurnJobConsumeOptions = {
            onProgress: options.onProgress,
            timeoutMs: this.turnJobTimeoutMs,
            signal,
            ...(options.onProgressDeliveryError
                ? { onProgressDeliveryError: options.onProgressDeliveryError }
                : {})
        };
        return consumeTurnJob(initial, transport, consumeOptions);
    }
    private async getTurnJob(jobId: string, signal: AbortSignal): Promise<DiscordTurnJobView> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        return this.request<DiscordTurnJobView>(`/api/connectors/discord/turn-jobs/${encodeURIComponent(jobId)}?${query.toString()}`, { signal }, true, TURN_JOB_REQUEST_TIMEOUT_MS);
    }
    private async claimTurnJobProgress(jobId: string, nonce: string, signal: AbortSignal): Promise<{
        id: number;
        nonce: string;
        text: string;
    } | null> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        const result = await this.request<{
            event: {
                id: number;
                nonce: string;
                text: string;
            } | null;
        }>(`/api/connectors/discord/turn-jobs/${encodeURIComponent(jobId)}/progress/claim?${query.toString()}`, { method: "POST", body: JSON.stringify({ nonce }), signal }, false, TURN_JOB_REQUEST_TIMEOUT_MS);
        return result.event;
    }
    private async acknowledgeTurnJobProgress(jobId: string, progressId: number, nonce: string, signal: AbortSignal): Promise<void> {
        const query = new URLSearchParams({ connection_id: this.connectionId });
        await this.request<void>(`/api/connectors/discord/turn-jobs/${encodeURIComponent(jobId)}/progress/${progressId}/ack?${query.toString()}`, { method: "POST", body: JSON.stringify({ nonce }), signal }, false, TURN_JOB_REQUEST_TIMEOUT_MS);
    }
    private async withDiscordMedia<T extends Omit<DiscordInboundMessage, "connection_id">>(payload: T): Promise<T & DiscordMessageMedia> {
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
    private async discordMedia(channelId: string, messageId: string): Promise<DiscordMessageMedia> {
        const token = process.env.DISCORD_BOT_TOKEN?.trim();
        if (!token)
            return { attachments: [], embeds: [], reply_to_message_id: "" };
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
            if (this.attachmentCache.size > 1000) {
                for (const [key, value] of this.attachmentCache.entries()) {
                    if (value.expiresAt <= now)
                        this.attachmentCache.delete(key);
                }
            }
            return media;
        }
        finally {
            if (this.attachmentTasks.get(cacheKey) === task) {
                this.attachmentTasks.delete(cacheKey);
            }
        }
    }
    private async fetchDiscordMedia(channelId: string, messageId: string, token: string): Promise<DiscordMessageMedia> {
        try {
            const response = await fetch(`${DISCORD_API_BASE}/channels/${channelId}/messages/${messageId}`, {
                signal: AbortSignal.timeout(8000),
                headers: {
                    Authorization: `Bot ${token}`,
                    Accept: "application/json"
                }
            });
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
                    if (!raw || typeof raw !== "object")
                        return null;
                    const value = raw as DiscordMessageApiAttachment;
                    const attachmentId = stringValue(value.id, 200);
                    const url = stringValue(value.url, 3000);
                    if (!attachmentId || !url)
                        return null;
                    return {
                        attachment_id: attachmentId,
                        url,
                        proxy_url: stringValue(value.proxy_url, 3000),
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
                    if (!raw || typeof raw !== "object")
                        return null;
                    const value = raw as DiscordMessageApiEmbed;
                    const title = stringValue(value.title, 500);
                    const description = stringValue(value.description, 2000);
                    const url = stringValue(value.url, 3000);
                    const providerName = nestedString(value.provider, "name", 200);
                    const authorName = nestedString(value.author, "name", 200);
                    if (!title && !description && !url && !providerName && !authorName)
                        return null;
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
        }
        catch {
            return { attachments: [], embeds: [], reply_to_message_id: "" };
        }
    }
    private async request<T>(path: string, init?: RequestInit, retryable = init?.method === "GET", timeoutMs = 45000): Promise<T> {
        const url = `${this.baseUrl}${path}`;
        let response: Response | undefined;
        let lastNetworkError: unknown;
        const attempts = retryable ? RETRY_DELAYS_MS.length : 1;
        for (let attempt = 0; attempt < attempts; attempt += 1) {
            const wait = RETRY_DELAYS_MS[attempt];
            if (wait)
                await delay(wait);
            try {
                if (init?.signal?.aborted) {
                    throw new Error("Character Relay request was canceled during connector shutdown.");
                }
                const timeoutSignal = AbortSignal.timeout(timeoutMs);
                const signal = init?.signal
                    ? AbortSignal.any([init.signal, timeoutSignal])
                    : timeoutSignal;
                response = await fetch(url, {
                    ...init,
                    signal,
                    headers: {
                        Authorization: `Bearer ${this.token}`,
                        "Content-Type": "application/json",
                        ...(init?.headers ?? {})
                    }
                });
            }
            catch (error) {
                lastNetworkError = error;
                if (init?.signal?.aborted) {
                    throw new Error(`Character Relay request was canceled at ${url}.`, { cause: error });
                }
                if (attempt < attempts - 1)
                    continue;
                throw new Error(`Unable to reach Character Relay at ${url}: ${errorDetail(error)}`, { cause: error });
            }
            if (TRANSIENT_STATUS_CODES.has(response.status) &&
                attempt < attempts - 1) {
                continue;
            }
            break;
        }
        if (!response) {
            throw new Error(`Unable to reach Character Relay at ${url}: ${errorDetail(lastNetworkError)}`, { cause: lastNetworkError });
        }
        if (!response.ok) {
            const body = await response.text();
            let detail = body;
            try {
                const parsed = JSON.parse(body) as {
                    detail?: unknown;
                };
                if (typeof parsed.detail === "string")
                    detail = parsed.detail;
            }
            catch {
                // Preserve the raw body.
            }
            throw new Error(`Character Relay returned HTTP ${response.status} from ${url}: ${detail}`);
        }
        if (response.status === 204)
            return undefined as T;
        return response.json() as Promise<T>;
    }
}
