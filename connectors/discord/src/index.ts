import { WebRoomBridge, type WebClaim } from "./webRoomBridge.js";
import { Client,Events,GatewayIntentBits,Partials,type Message } from "discord.js";
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { resolveExplicitAudiencePreflight } from "./audiencePreflight.js";
import { loadConfig } from "./config.js";
import { ContextBuffer } from "./contextBuffer.js";
import { canFallbackDelivery,deliverWithFallback,deliveryFailure,sendChunks } from "./delivery.js";
import { preflightDiscordDraft,type DraftPreflightResult } from "./draftPreflight.js";
import { socialOperationId,type DiscordSocialOperationClaim,type DiscordSocialOperationClaimRequest } from "./durableRuntime.js";
import { DiscordEventReporter } from "./eventReporter.js";
import { parseCustomEmojiTokens,stripCustomEmojiTokens } from "./expressionFlow.js";
import { detectBotMention,stripBotMentionTokens } from "./mentionDetection.js";
import { RecoveryLoop } from "./recoveryLoop.js";
import { RelayClient,} from "./relayClient.js";
import { RoomEventPublisher } from "./roomEventPublisher.js";
import { checkRoomAccess,discordEvidence,rawRoomSource,roomLocation,sourceContext,type RoomRoutingResult } from "./roomEvidence.js";
import { RoomPublicationLock,RoomWorkQueue } from "./roomWorkQueue.js";
import { buildDeploymentIndex,deploymentsFor,destinationKey,flattenDeployments,normalizeBotTagReply,resolveAudience,resolveBotTagAudience,shouldSubmitMessage,splitDiscordMessage,type DeploymentIndex } from "./routing.js";
import { formatSafeDiagnosticError,safeDiagnosticError } from "./safeDiagnosticError.js";
import { collectDiscordServerCatalog,refreshCatalogThenDeployments } from "./serverCatalog.js";
import { buildMentionableParticipants,compileSmartMessage,smartOutputResourceCandidate } from "./smartOutput.js";
import type { ConversationBurst } from "./turnCollector.js";
import { parseTurnControl } from "./turnControl.js";
import { TurnIngressCoordinator,buildConversationBurstText,decideTurnCollection,summarizeConversationBurst } from "./turnIngress.js";
import { TurnJobTerminalError } from "./turnJobs.js";
import type { DiscordActionParticipant,DiscordContextMessage,DiscordContextTrace,DiscordDeployment,DiscordExpressionCandidate,DiscordExpressionContent,DiscordExpressionDecision,DiscordReply,DiscordSmartOutput,DiscordSocialPendingTurn,DiscordSocialTurnCursor,DiscordSocialTurnStepReply,DiscordStickerContent,DiscordTurnJobDescriptor } from "./types.js";
import { DiscordWebhookManager } from "./webhookManager.js";
const config = loadConfig();
const relay = new RelayClient(config.relayApiUrl, config.relayConnectorToken, config.relayConnectionId, config.turnJobMaxWaitMs);
const webhookManager = new DiscordWebhookManager(config.discordBotToken, relay);
const eventReporter = new DiscordEventReporter(async (events) => {
    const eventTypes = [...new Set(events.map((item) => item.event_type))];
    const guildIds = [...new Set(events.map((item) => item.guild_id).filter(Boolean))];
    log("Uploading Discord event batch to Portal.", {
        level: "info",
        connectionId: config.relayConnectionId,
        eventCount: events.length,
        eventTypes,
        guildIds,
        firstOccurredAt: events[0]?.occurred_at ?? null,
        lastOccurredAt: events.at(-1)?.occurred_at ?? null
    });
    try {
        await relay.reportEvents(events);
        log("Discord event batch uploaded to Portal.", {
            level: "info",
            connectionId: config.relayConnectionId,
            eventCount: events.length,
            eventTypes,
            guildIds
        });
    }
    catch (error) {
        log("Discord event batch upload failed.", {
            level: "error",
            connectionId: config.relayConnectionId,
            eventCount: events.length,
            eventTypes,
            guildIds,
            ...safeDiagnosticError(error)
        });
        throw error;
    }
});
eventReporter.start();
log("Discord event reporter started.", {
    level: "info",
    connectionId: config.relayConnectionId,
    portalEventsEndpoint: `${config.relayApiUrl}/api/connectors/discord/events`,
    railwayReplicaRegion: process.env.RAILWAY_REPLICA_REGION ?? null,
    railwayReplicaId: process.env.RAILWAY_REPLICA_ID ?? null,
    railwayCommitSha: process.env.RAILWAY_GIT_COMMIT_SHA ?? null
});
const intents = [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMessageReactions,
    GatewayIntentBits.GuildMessagePolls,
    GatewayIntentBits.GuildExpressions
];
if (config.messageContentIntent)
    intents.push(GatewayIntentBits.MessageContent);
const client = new Client({
    intents,
    partials: [Partials.Channel, Partials.Message, Partials.Reaction]
});
interface CollectedDiscordTurn {
    source: Message<true>;
    originalText: string;
    authorDisplayName: string;
}
const context = new ContextBuffer(config.maxContextMessages);
const roomEvents = new RoomEventPublisher(evidence => relay.observeRoom(evidence), (error, room) => log("Raw room evidence update failed; publication still requires a fresh read.", {
    room, ...safeDiagnosticError(error)
}));
const roomPublications = new RoomPublicationLock();
const workQueue = new RoomWorkQueue({
    maximumPending: config.turnIngressMaxPending,
    maximumPerRoom: config.turnIngressMaxPendingPerDestination,
    concurrency: 4,
    concurrencyPerRoom: 2
}, (error, destination) => {
    lastError = formatSafeDiagnosticError(error);
    log("Discord message task failed.", { destination, ...safeDiagnosticError(error) });
});
const latestHumanTurnByDestination = new Map<string, {
    epoch: number;
    messageId: string;
}>();
const processedMessages = new Map<string, number>();
const sentCharacterRoutes = new Map<string, {
    deploymentId: string;
    seenAt: number;
}>();
const observedWebhookIds = new Set<string>();
const recoveringTurnJobIds = new Set<string>();
const turnJobRecoveryTasks = new Set<Promise<void>>();
const pendingTurnJobRecoveries = new Map<string, DiscordTurnJobDescriptor>();
let shuttingDown = false;
let turnJobRecoveryScan: Promise<void> | null = null;
let deployments: DeploymentIndex = new Map();
let lastDeploymentSyncAt: string | null = null;
let lastCatalogSyncAt: string | null = null;
let lastError: string | null = null;
let ready = false;
let stateSynchronized = false;
let recoveryLoop: RecoveryLoop | undefined;
let heartbeatTimer: NodeJS.Timeout | undefined;
let dedupeTimer: NodeJS.Timeout | undefined;
let lastGatewayMessageAt: string | null = null;
let lastGatewayMessageId: string | null = null;
let lastGatewayMentionedBot = false;
let turnCollectorCandidateMessageCount = 0;
let turnCollectorBypassMessageCount = 0;
let turnCollectorBurstCount = 0;
let turnCollectorCollectedMessageCount = 0;
let turnCollectorCollapsedMessageCount = 0;
let turnCollectorInteractionBypassCount = 0;
let turnCollectorLastBurstAt: string | null = null;
let turnCollectorLastBurstId: string | null = null;
let turnCollectorLastFlushReason: string | null = null;
const turnCollectorBypassReasons: Record<string, number> = {};
const turnIngress = new TurnIngressCoordinator<CollectedDiscordTurn>({
    enabled: config.roomBufferEnabled,
    quietWindowMs: config.roomBufferQuietMs,
    maxWaitMs: config.roomBufferMaxWaitMs,
    maxMessages: config.roomBufferMaxMessages,
    maxCharacters: config.roomBufferMaxCharacters
}, enqueue, (error, scopeKey) => {
    lastError = formatSafeDiagnosticError(error);
    log("Discord Turn Collector ingress failed.", {
        scopeKey,
        ...safeDiagnosticError(error)
    });
}, {
    maxPending: config.turnIngressMaxPending,
    maxPendingPerScope: config.turnIngressMaxPendingPerDestination,
    maxPreflightAgeMs: config.turnIngressMaxPreflightAgeMs
}, (scopeKey, reason) => {
    log("Discord turn ingress rejected before Runtime submission.", {
        scopeKey,
        reason,
        pending: workQueue.pending,
        destinationPending: workQueue.pendingFor(scopeKey)
    });
});
function isVisibleImageAttachment(attachment: {
    contentType?: string | null;
    name?: string | null;
}): boolean {
    const contentType = attachment.contentType?.trim().toLowerCase() ?? "";
    if (contentType.startsWith("image/"))
        return true;
    const name = attachment.name?.trim().toLowerCase() ?? "";
    return /\.(?:png|jpe?g|webp|gif|avif)$/u.test(name);
}
function visibleImageAttachmentCount(message: Message<true>): number {
    return [...message.attachments.values()].filter(isVisibleImageAttachment).length;
}
function log(message: string, metadata?: Record<string, unknown>): void {
    console.log(JSON.stringify({
        timestamp: new Date().toISOString(),
        message,
        ...(metadata ?? {})
    }));
}
function reportDiscordEvent(input: {
    level: "info" | "warning" | "error";
    eventType: string;
    message: string;
    guildId?: string;
    guildName?: string;
    channelId?: string;
    channelName?: string;
    threadId?: string;
    threadName?: string;
    sourceMessageId?: string;
    deploymentId?: string;
    characterName?: string;
    details?: Record<string, unknown>;
}): void {
    eventReporter.record({
        level: input.level,
        event_type: input.eventType,
        message: input.message,
        guild_id: input.guildId ?? "",
        guild_name: input.guildName ?? "",
        channel_id: input.channelId ?? "",
        channel_name: input.channelName ?? "",
        thread_id: input.threadId ?? "",
        thread_name: input.threadName ?? "",
        source_message_id: input.sourceMessageId ?? "",
        deployment_id: input.deploymentId ?? "",
        character_name: input.characterName ?? "",
        details: input.details ?? {}
    });
    log("Discord event queued for Portal.", {
        level: input.level,
        eventType: input.eventType,
        connectionId: config.relayConnectionId,
        guildId: input.guildId ?? null,
        channelId: input.channelId ?? null,
        threadId: input.threadId || null,
        sourceMessageId: input.sourceMessageId ?? null,
        deploymentId: input.deploymentId || null,
        pendingPortalLogs: eventReporter.pendingCount
    });
}
function reportCharacterContext(input: {
    trace: DiscordContextTrace | null | undefined;
    source: Message<true>;
    deployment: DiscordDeployment;
}): void {
    const trace = input.trace;
    if (!trace)
        return;
    const common = {
        guildId: input.source.guildId,
        guildName: input.source.guild.name,
        channelId: input.deployment.channel_id,
        channelName: input.deployment.channel_name,
        threadId: input.deployment.thread_id,
        threadName: input.deployment.thread_name,
        sourceMessageId: input.source.id,
        deploymentId: input.deployment.deployment_id,
        characterName: input.deployment.identity_display_name || input.deployment.character_display_name
    };
    const details = {
        rag_status: trace.rag_status,
        rag_reason: trace.rag_reason,
        retrieval_mode: trace.retrieval_mode,
        carryover_message_count: trace.carryover_message_count,
        initial_hit_count: trace.initial_hit_count,
        fallback_hit_count: trace.fallback_hit_count,
        query_chars: trace.query_chars,
        eligible_base_count: trace.eligible_base_count,
        candidate_chunk_count: trace.candidate_chunk_count,
        selected_chunk_count: trace.selected_chunk_count,
        selected_knowledge_tokens: trace.selected_knowledge_tokens,
        knowledge_token_budget: trace.knowledge_token_budget,
        selected: trace.selected
    };
    reportDiscordEvent({
        level: trace.rag_status === "failed" ? "warning" : "info",
        eventType: "context_built",
        message: "Character Turn Context was assembled before Smart Output.",
        ...common,
        details
    });
    reportDiscordEvent({
        level: trace.rag_status === "failed" ? "warning" : "info",
        eventType: `rag_retrieval_${trace.rag_status}`,
        message: trace.rag_status === "completed"
            ? "RAG retrieval completed for this character turn."
            : trace.rag_status === "failed"
                ? "RAG retrieval failed; Character Runtime continued without knowledge context."
                : "RAG retrieval was skipped for this character turn.",
        ...common,
        details
    });
}
async function syncServerCatalog(): Promise<void> {
    const payload = await collectDiscordServerCatalog(client.guilds.cache.values(), log);
    await relay.syncServerCatalog(payload);
    lastCatalogSyncAt = new Date().toISOString();
    log("Discord server catalog synchronized.", {
        visibleGuilds: payload.visible_guild_ids.length,
        successfulGuilds: payload.servers.length,
        failedGuilds: payload.failed_guild_ids.length,
        channels: payload.servers.reduce((total, server) => total + server.channels.length, 0),
        emojis: payload.servers.reduce((total, server) => total + (server.emojis?.length ?? 0), 0),
        stickers: payload.servers.reduce((total, server) => total + (server.stickers?.length ?? 0), 0)
    });
}
async function prepareWebhookIdentity(deployment: DiscordDeployment, botUserId: string): Promise<void> {
    if (deployment.identity_mode !== "webhook" ||
        deployment.channel_scope_mode === "all_except") {
        return;
    }
    try {
        await webhookManager.ensure(deployment, botUserId);
        if (deployment.webhook_id)
            observedWebhookIds.add(deployment.webhook_id);
    }
    catch (error) {
        const message = formatSafeDiagnosticError(error);
        deployment.webhook_status = "error";
        await relay
            .reportWebhookStatus({
            deployment_id: deployment.deployment_id,
            status: "error",
            last_error: message
        })
            .catch(() => undefined);
        log("Discord webhook preparation failed.", {
            deploymentId: deployment.deployment_id,
            channelId: deployment.channel_id,
            error: message
        });
    }
}
async function refreshDeployments(): Promise<void> {
    const [next, runtimeConfig] = await Promise.all([
        relay.listDeployments(),
        relay.getRoomBufferConfig().catch((error) => {
            log("Unable to refresh dynamic Turn Collector config; keeping the last effective value.", {
                ...safeDiagnosticError(error)
            });
            return null;
        })
    ]);
    if (runtimeConfig) {
        turnIngress.reconfigure({
            enabled: runtimeConfig.enabled,
            quietWindowMs: runtimeConfig.quiet_window_ms,
            maxWaitMs: runtimeConfig.max_wait_ms,
            maxMessages: runtimeConfig.max_messages,
            maxCharacters: runtimeConfig.max_characters
        });
    }
    const botUserId = client.user?.id;
    if (botUserId) {
        // Exact-channel webhooks are prepared sequentially. Server-wide profiles are
        // provisioned lazily for the concrete channel that receives a message.
        for (const item of next) {
            await prepareWebhookIdentity(item, botUserId);
        }
    }
    deployments = buildDeploymentIndex(next);
    lastDeploymentSyncAt = new Date().toISOString();
    log("Discord deployments refreshed.", {
        count: next.length,
        destinations: deployments.size,
        serverWide: next.filter((item) => item.channel_scope_mode === "all_except").length,
        multiCharacterDestinations: [...deployments.values()].filter((items) => items.length > 1).length,
        webhookReady: next.filter((item) => item.identity_mode === "webhook" && item.webhook_status === "active").length,
        turnCollector: turnIngress.currentConfig
    });
}
async function refreshConnectorState(): Promise<void> {
    await refreshCatalogThenDeployments(syncServerCatalog, refreshDeployments, (error) => {
        lastError = formatSafeDiagnosticError(error);
        log("Server catalog refresh failed; deployment refresh continues.", safeDiagnosticError(error));
    });
}
async function sendHeartbeat(status: "connected" | "offline" | "error", error = ""): Promise<void> {
    const user = client.user;
    if (!user)
        return;
    const turnCollectorConfig = turnIngress.currentConfig;
    await relay.heartbeat({
        bot_user_id: user.id,
        bot_display_name: user.tag,
        status,
        last_error: error,
        replica_region: process.env.RAILWAY_REPLICA_REGION ?? "",
        replica_id: process.env.RAILWAY_REPLICA_ID ?? "",
        gateway_ready: ready,
        state_synchronized: stateSynchronized,
        visible_server_count: client.guilds.cache.size,
        event_log_pending_count: eventReporter.pendingCount,
        event_log_last_error: eventReporter.lastError ?? "",
        event_log_last_success_at: eventReporter.lastSuccessAt ?? "",
        event_log_last_recorded_at: eventReporter.lastRecordedAt ?? "",
        event_log_last_recorded_type: eventReporter.lastRecordedType ?? "",
        event_log_sent_count: eventReporter.sentCount,
        last_gateway_message_at: lastGatewayMessageAt ?? "",
        last_gateway_message_id: lastGatewayMessageId ?? "",
        last_gateway_mentioned_bot: lastGatewayMentionedBot,
        turn_collector_enabled: turnCollectorConfig.enabled,
        turn_collector_quiet_window_ms: turnCollectorConfig.quietWindowMs,
        turn_collector_max_wait_ms: turnCollectorConfig.maxWaitMs,
        turn_collector_max_messages: turnCollectorConfig.maxMessages,
        turn_collector_max_characters: turnCollectorConfig.maxCharacters,
        turn_collector_pending_burst_scope_count: turnIngress.pendingBurstScopeCount,
        turn_collector_pending_preflight_scope_count: turnIngress.pendingPreflightScopeCount,
        turn_collector_candidate_messages: turnCollectorCandidateMessageCount,
        turn_collector_bypass_messages: turnCollectorBypassMessageCount,
        turn_collector_bursts: turnCollectorBurstCount,
        turn_collector_collected_messages: turnCollectorCollectedMessageCount,
        turn_collector_collapsed_messages: turnCollectorCollapsedMessageCount,
        turn_collector_interaction_bypasses: turnCollectorInteractionBypassCount,
        turn_collector_bypass_reasons: { ...turnCollectorBypassReasons },
        turn_collector_last_burst_at: turnCollectorLastBurstAt ?? "",
        turn_collector_last_burst_id: turnCollectorLastBurstId ?? "",
        turn_collector_last_flush_reason: turnCollectorLastFlushReason ?? ""
    });
}
function channelLocation(message: Pick<Message<true>, "channel">): {
    channelId: string;
    channelName: string;
    categoryId: string;
    threadId: string;
    threadName: string;
} {
    if (message.channel.isThread()) {
        return {
            channelId: message.channel.parentId ?? "",
            channelName: message.channel.parent?.name ??
                message.channel.parentId ??
                "unknown-channel",
            categoryId: message.channel.parent?.parentId ?? "",
            threadId: message.channel.id,
            threadName: message.channel.name
        };
    }
    return {
        channelId: message.channel.id,
        channelName: message.channel.name,
        categoryId: "parentId" in message.channel ? (message.channel.parentId ?? "") : "",
        threadId: "",
        threadName: ""
    };
}
function normalizedText(message: Message<true>, botUserId: string, managedBotRoleIds: string[]): string {
    return stripCustomEmojiTokens(stripBotMentionTokens(message.content, botUserId, managedBotRoleIds));
}
async function resolveMessageEmojis(message: Message<true>): Promise<DiscordExpressionContent[]> {
    const resolved: DiscordExpressionContent[] = [];
    for (const emoji of parseCustomEmojiTokens(message.content)) {
        try {
            resolved.push(await relay.resolveExpression({
                guild_id: message.guildId,
                resource_type: "emoji",
                resource_id: emoji.resource_id,
                name: emoji.name,
                animated: emoji.animated,
                available: true,
                asset_url: `https://cdn.discordapp.com/emojis/${emoji.resource_id}.${emoji.animated ? "gif" : "png"}`
            }));
        }
        catch (error) {
            log("Unable to resolve Discord custom Emoji semantics.", {
                emojiId: emoji.resource_id,
                ...safeDiagnosticError(error)
            });
        }
    }
    return resolved;
}
async function resolveMessageStickers(message: Message<true>): Promise<DiscordStickerContent[]> {
    const resolved: DiscordStickerContent[] = [];
    for (const sticker of message.stickers.values()) {
        const observation = {
            guild_id: message.guildId,
            sticker_id: sticker.id,
            name: sticker.name || "Sticker",
            description: sticker.description ?? "",
            tags: (sticker.tags ?? "")
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
            format_type: String(sticker.format),
            asset_url: sticker.url
        };
        try {
            resolved.push(await relay.resolveSticker(observation));
        }
        catch (error) {
            log("Unable to resolve Discord Sticker semantics.", {
                stickerId: sticker.id,
                ...safeDiagnosticError(error)
            });
            resolved.push({
                ...observation,
                semantic_intent: "sticker_reaction",
                semantic_emotion: "",
                semantic_description: `Sticker named ${observation.name}; meaning is not configured.`,
                semantic_source: "unknown",
                semantic_confidence: 0
            });
        }
    }
    return resolved;
}
function deploymentDisplayName(deployment: DiscordDeployment): string {
    return deployment.identity_display_name || deployment.character_display_name;
}
function deploymentAddressAlias(deployment: DiscordDeployment): string {
    return deployment.address_aliases?.[0] ?? deploymentDisplayName(deployment);
}
function knownWebhookIds(): Set<string> {
    return new Set([
        ...observedWebhookIds,
        ...flattenDeployments(deployments)
            .map((item) => item.webhook_id)
            .filter((item): item is string => Boolean(item))
    ]);
}
interface ReplyTarget {
    deploymentId: string | null;
    characterMessage: boolean;
}
async function resolveReplyTarget(message: Message<true>, candidates: DiscordDeployment[], botUserId: string, channelId: string, threadId: string, webReplyId?: string): Promise<ReplyTarget> {
    const referencedId = webReplyId || message.reference?.messageId;
    if (!referencedId) {
        return { deploymentId: null, characterMessage: false };
    }
    const cached = sentCharacterRoutes.get(referencedId);
    if (cached &&
        candidates.some((item) => item.deployment_id === cached.deploymentId)) {
        return { deploymentId: cached.deploymentId, characterMessage: true };
    }
    try {
        const route = await relay.resolveMessageRoute(referencedId);
        if (route &&
            route.channel_id === channelId &&
            route.thread_id === threadId &&
            candidates.some((item) => item.deployment_id === route.deployment_id)) {
            sentCharacterRoutes.set(referencedId, {
                deploymentId: route.deployment_id,
                seenAt: Date.now()
            });
            return { deploymentId: route.deployment_id, characterMessage: true };
        }
        const referenced = webReplyId ? await message.channel.messages.fetch({message: webReplyId, force: true, cache: false}) : await message.fetchReference();
        const characterMessage = referenced.author.id === botUserId ||
            (Boolean(referenced.webhookId) && knownWebhookIds().has(referenced.webhookId!));
        if (!characterMessage) {
            return { deploymentId: null, characterMessage: false };
        }
        // Messages sent before persistent routing existed remain unambiguous when only
        // one character is deployed to the destination.
        if (candidates.length === 1) {
            return {
                deploymentId: candidates[0]?.deployment_id ?? null,
                characterMessage: true
            };
        }
        return { deploymentId: null, characterMessage: true };
    }
    catch (error) {
        log("Unable to resolve referenced Discord message.", {
            messageId: message.id,
            referencedId,
            ...safeDiagnosticError(error)
        });
        return { deploymentId: null, characterMessage: false };
    }
}
function enqueue(destination: string, task: () => Promise<void>): boolean {
    return workQueue.enqueue(destination, task);
}
async function sendSelectionHelp(source: Message<true>, options: string[]): Promise<void> {
    const names = options.map((item) => `**${item}**`).join("、");
    const botName = client.user?.username ?? "CharacterRelayBot";
    await source.reply({
        content: `这个位置有多个角色：${names}。` +
            `可以使用 \`@${botName} 角色名 消息\`、` +
            `\`@${botName} 角色名 和 角色名 消息\`、` +
            `\`@${botName} 你们 消息\`，或直接回复目标角色发出的消息。`,
        allowedMentions: { parse: [], repliedUser: false }
    });
}
interface CharacterDeliveryOptions {
    replyToMessageId?: string | null;
    allowedUserIds?: string[];
}
async function sendBotFallback(source: Message<true>, characterName: string, replyText: string, options: CharacterDeliveryOptions): Promise<string[]> {
    const safeName = characterName.replaceAll(/([\\*_`~|>])/g, "\\$1");
    const [firstChunk, ...remainingChunks] = splitDiscordMessage(`**${safeName}**\n${replyText}`);
    if (!firstChunk)
        return [];
    const allowedMentions = {
        parse: [] as [
        ], users: options.allowedUserIds ?? [], repliedUser: false
    };
    // Resolve the target before any visible send; failures later are never whole-message retries.
    const target = options.replyToMessageId
        ? await resolveSmartOutputTargetMessage(source, options.replyToMessageId) : null;
    if (options.replyToMessageId && !target)
        throw new Error("Smart Output reply target is unavailable.");
    return sendChunks([firstChunk, ...remainingChunks], async (content, index) => {
        const sent = index === 0 && target
            ? await target.reply({ content, allowedMentions })
            : await source.channel.send({ content, allowedMentions });
        return sent.id;
    });
}
async function sendCharacterReply(source: Message<true>, deployment: DiscordDeployment, replyText: string, botUserId: string, options?: CharacterDeliveryOptions): Promise<string[]> {
    const delivery = options ?? { replyToMessageId: source.id, allowedUserIds: [] };
    const fallback = () => sendBotFallback(source, deployment.identity_display_name || deployment.character_display_name, replyText, delivery);
    if (deployment.identity_mode !== "webhook")
        return fallback();
    try {
        return await deliverWithFallback(async () => {
            const ids = await webhookManager.send(deployment, splitDiscordMessage(replyText), botUserId, delivery.allowedUserIds ?? []);
            if (deployment.webhook_id)
                observedWebhookIds.add(deployment.webhook_id);
            return ids;
        }, async () => {
            log("Webhook was definitely unsent; using the shared Bot identity.", {
                deploymentId: deployment.deployment_id
            });
            return fallback();
        });
    }
    catch (error) {
        const failure = deliveryFailure(error);
        if (failure.sentMessageIds.length) {
            await rememberSentMessages(deployment, [...failure.sentMessageIds], source.guildId);
        }
        throw failure;
    }
}
async function deliverCharacterTurnProgress(source: Message<true>, deployment: DiscordDeployment, text: string, botUserId: string, contextKey: string): Promise<void> {
    const visibleText = text.trim().slice(0, 500);
    if (!visibleText)
        return;
    const sentMessageIds = await sendCharacterReply(source, deployment, visibleText, botUserId);
    await rememberSentMessages(deployment, sentMessageIds, source.guildId);
    if (sentMessageIds.length) {
        context.push(contextKey, {
            message_id: sentMessageIds[0]!,
            author_id: `character:${deployment.character_card_id}`,
            author_deployment_id: deployment.deployment_id,
            author_display_name: deploymentDisplayName(deployment),
            text: visibleText,
            emojis: [],
            stickers: [],
            created_at: new Date().toISOString(),
            is_bot: true
        });
    }
}
async function deliverCharacterTurnFailure(source: Message<true>, deployment: DiscordDeployment, botUserId: string, contextKey: string): Promise<void> {
    await deliverCharacterTurnProgress(source, deployment, "I’m sorry, I couldn’t finish that response. Please try again in a moment.", botUserId, contextKey);
}
async function claimTerminalTurnFailure(error: TurnJobTerminalError): Promise<boolean> {
    if (error.errorCode === "connector_poll_budget_exhausted" ||
        error.status === "cancelled")
        return false;
    try {
        await relay.consumeTerminalTurnJob(error.jobId);
        return true;
    }
    catch (claimError) {
        if (claimError instanceof Error &&
            claimError.message.includes("HTTP 409")) {
            return false;
        }
        throw claimError;
    }
}
async function rememberSentMessages(deployment: DiscordDeployment, messageIds: string[], guildId: string): Promise<void> {
    if (!messageIds.length)
        return;
    const now = Date.now();
    for (const messageId of messageIds) {
        sentCharacterRoutes.set(messageId, {
            deploymentId: deployment.deployment_id,
            seenAt: now
        });
    }
    await relay
        .registerMessageRoutes({
        deployment_id: deployment.deployment_id,
        guild_id: guildId,
        channel_id: deployment.channel_id,
        thread_id: deployment.thread_id,
        webhook_id: deployment.webhook_id ?? "",
        message_ids: messageIds
    })
        .catch((error: unknown) => {
        log("Unable to persist Discord message routes.", {
            deploymentId: deployment.deployment_id,
            messageIds,
            ...safeDiagnosticError(error)
        });
    });
}
function resolveDeploymentLocation(deployment: DiscordDeployment, location: ReturnType<typeof channelLocation>): DiscordDeployment {
    if (deployment.channel_scope_mode !== "all_except") {
        return { ...deployment, category_id: location.categoryId };
    }
    return {
        ...deployment,
        channel_id: location.channelId,
        channel_name: location.channelName,
        category_id: location.categoryId,
        thread_id: location.threadId,
        thread_name: location.threadName,
        webhook_id: null,
        webhook_token: null,
        webhook_status: deployment.identity_mode === "webhook" ? "pending" : "not_required"
    };
}
interface ExpressionExecutionResult {
    sentMessageIds: string[];
    outgoingText: string;
    action: DiscordExpressionDecision["action"];
    resourceKey: string;
    applied: boolean;
    fallback: string;
}
async function resolveExpressionSourceMessage(fallback: Message<true>, messageId: string): Promise<Message<true>> {
    if (!messageId || messageId === fallback.id)
        return fallback;
    try {
        const fetched = await fallback.channel.messages.fetch(messageId);
        return fetched.inGuild() ? fetched : fallback;
    }
    catch (error) {
        log("Unable to fetch the character message used as an Expression source.", {
            messageId,
            fallbackMessageId: fallback.id,
            ...safeDiagnosticError(error)
        });
        return fallback;
    }
}
async function resolveSmartOutputTargetMessage(source: Message<true>, messageId: string): Promise<Message<true> | null> {
    if (!messageId)
        return null;
    if (messageId === source.id)
        return source;
    try {
        const fetched = await source.channel.messages.fetch(messageId);
        return fetched.inGuild() ? fetched : null;
    }
    catch {
        return null;
    }
}
async function validateExpressionResource(source: Message<true>, candidate: DiscordExpressionCandidate): Promise<boolean> {
    try {
        if (candidate.resource_type === "emoji") {
            const emoji = await source.guild.emojis.fetch(candidate.resource_id);
            return Boolean(emoji && emoji.available !== false);
        }
        const sticker = await source.guild.stickers.fetch(candidate.resource_id);
        return Boolean(sticker);
    }
    catch {
        return false;
    }
}
async function executeCharacterOutput(source: Message<true>, deployment: DiscordDeployment, visibleText: string, botUserId: string): Promise<ExpressionExecutionResult> {
    const sentMessageIds = visibleText ? await sendCharacterReply(source, deployment, visibleText, botUserId) : [];
    return { sentMessageIds, outgoingText: visibleText, action: "none", resourceKey: "", applied: false, fallback: "none" };
}
interface SmartOutputExecutionResult extends ExpressionExecutionResult {
    smartAction: DiscordSmartOutput["action"];
    mentionedDeploymentIds: string[];
}
function skippedSmartOutput(action: DiscordSmartOutput["action"], fallback: string): SmartOutputExecutionResult {
    return {
        sentMessageIds: [],
        outgoingText: "",
        action: "none",
        resourceKey: "",
        applied: false,
        fallback,
        smartAction: action,
        mentionedDeploymentIds: []
    };
}
async function executeSmartOutput(source: Message<true>, deployment: DiscordDeployment, output: DiscordSmartOutput, botUserId: string, candidates: DiscordDeployment[], mentionableParticipants: DiscordActionParticipant[]): Promise<SmartOutputExecutionResult> {
    if (output.action === "ignore") {
        return skippedSmartOutput("ignore", "ignore");
    }
    const expressionCandidates = output.expression_resource ? [output.expression_resource] : [];
    if (output.action === "message") {
        const usableExpressions: typeof expressionCandidates = [];
        for (const candidate of expressionCandidates) {
            if (await validateExpressionResource(source, candidate))
                usableExpressions.push(candidate);
        }
        const messageOutput = {
            ...output,
            content: output.content.filter((part) => !("emoji" in part) ||
                usableExpressions.some((candidate) => candidate.resource_key === part.emoji))
        };
        const compiled = compileSmartMessage(messageOutput, candidates, deployment, usableExpressions, mentionableParticipants);
        if (!compiled.ok) {
            return skippedSmartOutput("message", compiled.error);
        }
        if (output.reply_to_message_id) {
            const target = await resolveSmartOutputTargetMessage(source, output.reply_to_message_id);
            if (!target)
                return skippedSmartOutput("message", "reply_target_unavailable");
        }
        const sentMessageIds = await sendCharacterReply(source, deployment, compiled.content, botUserId, {
            replyToMessageId: output.reply_to_message_id,
            allowedUserIds: compiled.allowedUserIds
        });
        const resourceKey = compiled.customEmojiResourceKeys[0] ?? "";
        return {
            sentMessageIds,
            outgoingText: compiled.content,
            action: resourceKey ? "inline" : "none",
            resourceKey,
            applied: Boolean(resourceKey),
            fallback: deployment.identity_mode === "webhook" && output.reply_to_message_id
                ? "webhook_reply_to_direct"
                : "none",
            smartAction: "message",
            mentionedDeploymentIds: compiled.mentionedDeploymentIds
        };
    }
    const candidate = smartOutputResourceCandidate(output, expressionCandidates);
    if (!candidate || !await validateExpressionResource(source, candidate)) {
        if (output.fallback_text?.trim()) {
            const ids = await sendCharacterReply(source, deployment, output.fallback_text, botUserId, {
                replyToMessageId: output.reply_to_message_id ?? output.target_message_id
            });
            return { sentMessageIds: ids, outgoingText: output.fallback_text, action: "none",
                resourceKey: "", applied: false, fallback: "resource_unavailable_text",
                smartAction: "message", mentionedDeploymentIds: [] };
        }
        return skippedSmartOutput(output.action, "resource_unavailable");
    }
    if (output.action === "react") {
        const targetId = output.target_message_id;
        if (!targetId)
            return skippedSmartOutput("react", "reaction_target_missing");
        const target = await resolveSmartOutputTargetMessage(source, targetId);
        if (!target)
            return skippedSmartOutput("react", "reaction_target_unavailable");
        try {
            await target.react(`${candidate.name}:${candidate.resource_id}`);
        }
        catch (error) {
            throw deliveryFailure(error);
        }
        return {
            sentMessageIds: [],
            outgoingText: "",
            action: "reaction",
            resourceKey: candidate.resource_key,
            applied: true,
            fallback: "none",
            smartAction: "react",
            mentionedDeploymentIds: []
        };
    }
    const replyTarget = output.reply_to_message_id
        ? await resolveSmartOutputTargetMessage(source, output.reply_to_message_id)
        : null;
    if (output.reply_to_message_id && !replyTarget) {
        return skippedSmartOutput("sticker", "reply_target_unavailable");
    }
    let sentMessageIds: string[] = [];
    let fallback = "none";
    const normalizedFormat = candidate.format_type.toLowerCase();
    const webhookRenderable = !["3", "lottie"].includes(normalizedFormat);
    if (deployment.identity_mode === "webhook" && candidate.asset_url && webhookRenderable) {
        try {
            const extension = ["4", "gif"].includes(normalizedFormat) ? "gif" : "png";
            sentMessageIds = await webhookManager.sendAsset(deployment, "", candidate.asset_url, `${candidate.name || "expression"}.${extension}`, botUserId);
            fallback = output.reply_to_message_id
                ? "webhook_reply_to_direct"
                : "webhook_attachment";
        }
        catch (error) {
            if (!canFallbackDelivery(error))
                throw error;
            fallback = "webhook_attachment_to_native_sticker";
        }
    }
    if (!sentMessageIds.length) {
        try {
            const options = {
                stickers: [candidate.resource_id],
                allowedMentions: { parse: [] as [
                    ], repliedUser: false }
            };
            const sent = replyTarget
                ? await replyTarget.reply(options)
                : await source.channel.send(options);
            sentMessageIds = [sent.id];
            if (fallback === "none")
                fallback = "native_bot_sticker";
        }
        catch (error) {
            throw deliveryFailure(error);
        }
    }
    return {
        sentMessageIds,
        outgoingText: "",
        action: "sticker",
        resourceKey: candidate.resource_key,
        applied: true,
        fallback,
        smartAction: "sticker",
        mentionedDeploymentIds: []
    };
}
type CharacterDeliveryClaim = {
    operationId: string;
    stepId: string;
    claimNonce: string;
};
async function preflightReply(source: Message<true>, reply: DiscordReply, operationId: string, stepId: string): Promise<DraftPreflightResult> {
    const result = await preflightDiscordDraft({ source, reply, transport: relay,
        operationId, stepId, contentIntent: config.messageContentIntent });
    if (result.disposition === "in_progress")
        throw new Error("draft_preflight_in_progress");
    if (result.reply)
        Object.assign(reply, result.reply);
    reportDiscordEvent({
        level: result.disposition === "blocked" ? "warning" : "info",
        eventType: `draft_${result.disposition}`,
        message: "Runtime evaluated the unpublished draft against current source evidence.",
        guildId: source.guildId, channelId: roomLocation(source).channel_id,
        threadId: roomLocation(source).thread_id, sourceMessageId: source.id,
        deploymentId: reply.deployment_id ?? "",
        details: { operation_id: operationId, step_id: stepId, reason: result.reason,
            target_message_id: reply.context_trace?.source_target_message_id ?? "" }
    });
    return result;
}
async function claimCharacterTurnDelivery(reply: DiscordReply, source: Message<true>): Promise<CharacterDeliveryClaim | "already_delivered" | "suppressed" | null> {
    if (!reply.delivery_required)
        return null;
    if (!reply.operation_id || !reply.step_id) {
        throw new Error("Durable Character Turn response is missing a server-derived delivery identity.");
    }
    const check = await preflightReply(source, reply, reply.operation_id, reply.step_id);
    if (check.disposition === "drop" || check.disposition === "blocked")
        return "suppressed";
    const claimNonce = randomUUID();
    const claim = await relay.claimCharacterTurnDelivery({
        operation_id: reply.operation_id,
        step_id: reply.step_id,
        claim_nonce: claimNonce
    });
    if (claim.claim_status === "uncertain") {
        throw new Error("Durable Discord delivery is uncertain; refusing to resend.");
    }
    if (claim.claim_status === "already_delivered")
        return "already_delivered";
    return {
        operationId: reply.operation_id,
        stepId: reply.step_id,
        claimNonce
    };
}
async function acknowledgeCharacterTurnDelivery(claim: CharacterDeliveryClaim | null, sentMessageIds: string[], applied = false): Promise<void> {
    if (!claim)
        return;
    await relay.acknowledgeCharacterTurnDelivery({
        operation_id: claim.operationId,
        step_id: claim.stepId,
        claim_nonce: claim.claimNonce,
        sent_message_ids: sentMessageIds,
        applied
    });
}
async function markCharacterTurnDeliveryUncertain(claim: CharacterDeliveryClaim | null, error: unknown): Promise<void> {
    if (!claim)
        return;
    await relay
        .markCharacterTurnDeliveryUncertain({
        operation_id: claim.operationId,
        step_id: claim.stepId,
        claim_nonce: claim.claimNonce,
        sent_message_ids: [...deliveryFailure(error).sentMessageIds],
        error: formatSafeDiagnosticError(error)
    })
        .catch(() => undefined);
}
async function processMessage(message: Message, options?: {
    recovery?: boolean;
    webActor?: WebClaim;
}): Promise<void> {
    const botUser = client.user;
    const webActor = options?.webActor;
    if (!message.inGuild() || (message.author.bot && !webActor) || !botUser)
        return;
    if (processedMessages.has(message.id) && !options?.recovery)
        return;
    processedMessages.set(message.id, Date.now());
    const guildMessage = message;
    if (webActor && (webActor.discord_message_id !== message.id || webActor.webhook_id !== message.webhookId ||
        webActor.guild_id !== message.guildId || (webActor.thread_id || webActor.channel_id) !== message.channelId)) {
        throw new Error("web_actor_receipt_mismatch");
    }
    const location = channelLocation(guildMessage);
    if (!location.channelId)
        return;
    const mentionedUserIds = [...guildMessage.mentions.users.keys()];
    const mentionedRoleIds = [...guildMessage.mentions.roles.keys()];
    const managedBotRoleIds = [...guildMessage.mentions.roles.values()]
        .filter((role) => role.tags?.botId === botUser.id)
        .map((role) => role.id);
    const mentionDetection = detectBotMention({
        content: guildMessage.content,
        botUserId: botUser.id,
        structuredUserMention: guildMessage.mentions.users.has(botUser.id),
        mentionedUserIds,
        mentionedRoleIds,
        managedBotRoleIds
    });
    const mentionedBot = mentionDetection.mentionedBot;
    let originalText = webActor?.text ?? normalizedText(guildMessage, botUser.id, mentionDetection.managedBotRoleIds);
    lastGatewayMessageAt = new Date().toISOString();
    lastGatewayMessageId = guildMessage.id;
    lastGatewayMentionedBot = mentionedBot;
    const candidates = deploymentsFor(deployments, location.channelId, location.threadId, guildMessage.guildId, location.categoryId);
    log("Discord Gateway message received.", {
        level: "info",
        connectionId: config.relayConnectionId,
        guildId: guildMessage.guildId,
        guildName: guildMessage.guild.name,
        channelId: location.channelId,
        channelName: location.channelName,
        threadId: location.threadId || null,
        sourceMessageId: guildMessage.id,
        authorId: guildMessage.author.id,
        mentionedBot,
        mentionSource: mentionDetection.source,
        structuredUserMention: mentionDetection.structuredUserMention,
        rawUserMention: mentionDetection.rawUserMention,
        managedBotRoleMention: mentionDetection.managedBotRoleMention,
        mentionedUserIds: mentionDetection.mentionedUserIds,
        mentionedRoleIds: mentionDetection.mentionedRoleIds,
        managedBotRoleIds: mentionDetection.managedBotRoleIds,
        candidateCount: candidates.length,
        hasReadableText: Boolean(originalText || parseCustomEmojiTokens(guildMessage.content).length),
        customEmojiCount: parseCustomEmojiTokens(guildMessage.content).length,
        stickerCount: guildMessage.stickers.size,
        railwayReplicaRegion: process.env.RAILWAY_REPLICA_REGION ?? null,
        railwayReplicaId: process.env.RAILWAY_REPLICA_ID ?? null
    });
    reportDiscordEvent({
        level: "info",
        eventType: "message_received",
        message: "A Discord message reached the Gateway message handler.",
        guildId: guildMessage.guildId,
        guildName: guildMessage.guild.name,
        channelId: location.channelId,
        channelName: location.channelName,
        threadId: location.threadId,
        threadName: location.threadName,
        sourceMessageId: guildMessage.id,
        details: {
            mentioned_bot: mentionedBot,
            candidate_count: candidates.length,
            has_readable_text: Boolean(originalText || parseCustomEmojiTokens(guildMessage.content).length),
            custom_emoji_count: parseCustomEmojiTokens(guildMessage.content).length,
            sticker_count: guildMessage.stickers.size
        }
    });
    if (mentionedBot) {
        reportDiscordEvent({
            level: "info",
            eventType: "mention_received",
            message: "Bot mention reached the Discord Gateway.",
            guildId: guildMessage.guildId,
            guildName: guildMessage.guild.name,
            channelId: location.channelId,
            channelName: location.channelName,
            threadId: location.threadId,
            threadName: location.threadName,
            sourceMessageId: guildMessage.id,
            details: {
                candidate_count: candidates.length,
                state_synchronized: stateSynchronized,
                has_readable_text: Boolean(originalText),
                sticker_count: guildMessage.stickers.size
            }
        });
    }
    if (!candidates.length) {
        if (mentionedBot) {
            reportDiscordEvent({
                level: "warning",
                eventType: "ignored_no_deployment",
                message: "The Tag was ignored because no active deployment matched this Server and Channel.",
                guildId: guildMessage.guildId,
                guildName: guildMessage.guild.name,
                channelId: location.channelId,
                channelName: location.channelName,
                threadId: location.threadId,
                threadName: location.threadName,
                sourceMessageId: guildMessage.id,
                details: { state_synchronized: stateSynchronized }
            });
        }
        return;
    }
    // Cancellation is deliberately a narrow, reply-based control.  It must name one
    // deployment, be addressed to this Bot, and reply to the same human's original
    // request.  New unrelated messages never cancel a turn.
    if (!options?.recovery && mentionedBot && guildMessage.reference?.messageId) {
        const control = parseTurnControl(originalText);
        if (control) {
            const audience = resolveAudience(candidates, control.audienceText, null, config.groupAddressAliases);
            const deployment = audience.deployments.length === 1 ? audience.deployments[0] : null;
            if (deployment) {
                try {
                    const referenced = await guildMessage.fetchReference();
                    if (!referenced.author.bot && referenced.author.id === guildMessage.author.id) {
                        const resolvedDeployment = resolveDeploymentLocation(deployment, location);
                        const cancelled = await relay.cancelTurnJobs({
                            deployment_id: resolvedDeployment.deployment_id,
                            guild_id: guildMessage.guildId,
                            channel_id: location.channelId,
                            thread_id: location.threadId,
                            category_id: location.categoryId,
                            source_message_id: referenced.id,
                            source_author_id: guildMessage.author.id,
                            reason: control.kind === "replace" ? "user_replaced" : "user_cancelled"
                        });
                        reportDiscordEvent({
                            level: "info",
                            eventType: control.kind === "replace" ? "turn_replaced" : "turn_cancelled",
                            message: "A user explicitly controlled their matching Character turn.",
                            guildId: guildMessage.guildId,
                            guildName: guildMessage.guild.name,
                            channelId: location.channelId,
                            channelName: location.channelName,
                            threadId: location.threadId,
                            threadName: location.threadName,
                            sourceMessageId: guildMessage.id,
                            deploymentId: resolvedDeployment.deployment_id,
                            characterName: deploymentDisplayName(resolvedDeployment),
                            details: {
                                target_message_id: referenced.id,
                                cancelled_job_ids: cancelled,
                                command: control.kind
                            }
                        });
                        if (control.kind === "cancel") {
                            await guildMessage.reply({
                                content: cancelled.length
                                    ? "Okay, I cancelled that request. Any work already sent to an external tool may still finish, but it will not be delivered as this reply."
                                    : "That request is no longer active.",
                                allowedMentions: { parse: [], repliedUser: false }
                            });
                            return;
                        }
                        originalText = control.replacementText;
                    }
                }
                catch (error) {
                    log("Explicit Discord turn control could not be applied.", {
                        sourceMessageId: guildMessage.id,
                        deploymentId: deployment.deployment_id,
                        ...safeDiagnosticError(error)
                    });
                }
            }
        }
    }
    const key = destinationKey(location.channelId, location.threadId);
    const previousHumanTurn = latestHumanTurnByDestination.get(key);
    const currentHumanTurn = options?.recovery
        ? previousHumanTurn ?? { epoch: 0, messageId: guildMessage.id }
        : {
            epoch: (previousHumanTurn?.epoch ?? 0) + 1,
            messageId: guildMessage.id
        };
    if (!options?.recovery) {
        latestHumanTurnByDestination.set(key, currentHumanTurn);
    }
    const turnEpoch = currentHumanTurn.epoch;
    const supersedingHumanTurn = (): {
        epoch: number;
        messageId: string;
    } | null => {
        const latest = latestHumanTurnByDestination.get(key);
        if (!latest || latest.epoch === turnEpoch)
            return null;
        return latest;
    };
    const authorDisplayName = webActor?.display_name ?? guildMessage.member?.displayName ??
        guildMessage.author.globalName ??
        guildMessage.author.username;
    const collectedTurn: CollectedDiscordTurn = {
        source: guildMessage,
        originalText,
        authorDisplayName
    };
    const executeQueued = async (burst: ConversationBurst<CollectedDiscordTurn> | null): Promise<void> => {
        const burstTelemetry = burst
            ? summarizeConversationBurst(burst, burst.items.map((item) => item.source.author.id))
            : null;
        if (burstTelemetry) {
            turnCollectorBurstCount += 1;
            turnCollectorCollectedMessageCount += burstTelemetry.messageCount;
            turnCollectorCollapsedMessageCount += burstTelemetry.collapsedMessageCount;
            turnCollectorLastBurstAt = new Date(burstTelemetry.flushedAt).toISOString();
            turnCollectorLastBurstId = burstTelemetry.burstId;
            turnCollectorLastFlushReason = burstTelemetry.flushReason;
            reportDiscordEvent({
                level: "info",
                eventType: "smart_participation_burst_flushed",
                message: "Turn Collector flushed a bounded Conversation Burst for Smart Participation.",
                guildId: guildMessage.guildId,
                guildName: guildMessage.guild.name,
                channelId: location.channelId,
                channelName: location.channelName,
                threadId: location.threadId,
                threadName: location.threadName,
                sourceMessageId: guildMessage.id,
                details: {
                    burst_id: burstTelemetry.burstId,
                    flush_reason: burstTelemetry.flushReason,
                    message_count: burstTelemetry.messageCount,
                    author_count: burstTelemetry.authorCount,
                    total_characters: burstTelemetry.totalCharacters,
                    opened_at: new Date(burstTelemetry.openedAt).toISOString(),
                    flushed_at: new Date(burstTelemetry.flushedAt).toISOString(),
                    collection_latency_ms: burstTelemetry.collectionLatencyMs,
                    collapsed_message_count: burstTelemetry.collapsedMessageCount,
                    source_message_ids: burstTelemetry.sourceMessageIds
                }
            });
        }
        if (burst) {
            for (const item of burst.items.slice(0, -1)) {
                context.push(key, {
                    channel_id: location.channelId, thread_id: location.threadId,
                    message_id: item.source.id,
                    reply_to_message_id: item.source.reference?.messageId ?? "",
                    ...(item.source.editedAt ? { edited_at: item.source.editedAt.toISOString() } : {}),
                    author_id: item.source.author.id,
                    author_display_name: item.authorDisplayName,
                    text: item.originalText,
                    emojis: [],
                    stickers: [],
                    created_at: item.source.createdAt.toISOString(),
                    is_bot: false
                });
            }
        }
        const [emojis, stickers] = await Promise.all([
            resolveMessageEmojis(guildMessage),
            resolveMessageStickers(guildMessage)
        ]);
        const contextMessage: DiscordContextMessage = {
            channel_id: location.channelId, thread_id: location.threadId,
            message_id: guildMessage.id,
            reply_to_message_id: webActor?.reply_to_message_id ?? guildMessage.reference?.messageId ?? "",
            ...(guildMessage.editedAt ? { edited_at: guildMessage.editedAt.toISOString() } : {}),
            author_id: webActor?.actor_id ?? guildMessage.author.id,
            author_display_name: authorDisplayName,
            text: originalText,
            emojis,
            stickers,
            created_at: guildMessage.createdAt.toISOString(),
            is_bot: Boolean(webActor)
        };
        context.push(key, contextMessage);
        const participationText = burst
            ? buildConversationBurstText(burst.items.map((item) => ({ text: item.originalText })), 4000)
            : originalText;
        const participationBurstId = burstTelemetry?.burstId ?? "";
        const burstMediaMessageIds = burst
            ? [
                ...new Set(burst.items
                    .slice(0, -1)
                    .filter((item) => {
                    const imageCount = visibleImageAttachmentCount(item.source);
                    return (imageCount > 0 &&
                        imageCount === item.source.attachments.size &&
                        item.source.embeds.length === 0 &&
                        !/https?:\/\//iu.test(item.source.content));
                })
                    .map((item) => item.source.id))
            ].slice(-2)
            : [];
        const replyAuthorByMessageId = new Map<string, {
            id: string;
            displayName: string;
        }>();
        {
            const burstAuthorByMessageId = new Map((burst?.items ?? [collectedTurn]).map((item) => [
                item.source.id,
                { id: item.source.author.id, displayName: item.authorDisplayName }
            ]));
            await Promise.all((burst?.items ?? [collectedTurn]).map(async (item) => {
                const replyToMessageId = item.source.reference?.messageId;
                if (!replyToMessageId)
                    return;
                const inBurst = burstAuthorByMessageId.get(replyToMessageId);
                if (inBurst) {
                    replyAuthorByMessageId.set(item.source.id, inBurst);
                    return;
                }
                try {
                    const referenced = await item.source.fetchReference();
                    replyAuthorByMessageId.set(item.source.id, {
                        id: referenced.author.id,
                        displayName: referenced.member?.displayName ??
                            referenced.author.globalName ??
                            referenced.author.username
                    });
                }
                catch {
                    // The relation stays valid by message ID when Discord no longer exposes its parent.
                }
            }));
        }
        const participationBurstMessages = burst
            ? burst.items.map((item) => {
                const replyAuthor = replyAuthorByMessageId.get(item.source.id);
                return {
                    message_id: item.source.id,
                    author_id: item.source.author.id,
                    author_display_name: item.authorDisplayName,
                    text: item.originalText,
                    created_at: item.source.createdAt.toISOString(),
                    reply_to_message_id: item.source.reference?.messageId ?? "",
                    reply_to_author_id: replyAuthor?.id ?? "",
                    reply_to_author_display_name: replyAuthor?.displayName ?? ""
                };
            })
            : [];
        const replyTarget = await resolveReplyTarget(guildMessage, candidates, botUser.id, location.channelId, location.threadId, webActor?.reply_to_message_id);
        if (replyTarget.characterMessage) {
            reportDiscordEvent({
                level: "info",
                eventType: "reply_received",
                message: "A reply to a Character Relay message reached the Discord Gateway.",
                guildId: guildMessage.guildId,
                guildName: guildMessage.guild.name,
                channelId: location.channelId,
                channelName: location.channelName,
                threadId: location.threadId,
                threadName: location.threadName,
                sourceMessageId: guildMessage.id,
                deploymentId: replyTarget.deploymentId ?? "",
                details: { candidate_count: candidates.length }
            });
        }
        let audience = resolveAudience(candidates, participationText, replyTarget.deploymentId, config.groupAddressAliases);
        const explicitAudience = audience.deployments.length > 0;
        let roomRouting: RoomRoutingResult;
        try {
            const evidence = await discordEvidence(guildMessage, config.messageContentIntent);
            for (const raw of evidence.messages)
                context.push(key, sourceContext(raw), true);
            roomRouting = await relay.resolveRoom({
                ...evidence,
                request_id: guildMessage.id,
                trigger_message_id: guildMessage.id,
                deployment_ids: candidates.map(item => item.deployment_id),
                // A Reply is resolved from the canonical raw parent by Runtime, not forged as a mention.
                explicit_deployment_ids: audience.reason === "selected_reply" ? [] :
                    audience.deployments.map(item => item.deployment_id),
                ambient_requested: config.ambientParticipationEnabled
            });
        }
        catch (error) {
            reportDiscordEvent({
                level: "warning", eventType: "room_routing_failed",
                message: "Room routing failed; no legacy selector or random speaker will run.",
                guildId: guildMessage.guildId, channelId: location.channelId,
                threadId: location.threadId, sourceMessageId: guildMessage.id,
                details: safeDiagnosticError(error)
            });
            if (explicitAudience || mentionedBot || replyTarget.characterMessage) {
                await guildMessage.reply({ content: "I could not resolve this request safely. Please try again.",
                    allowedMentions: { parse: [], repliedUser: false } });
            }
            return;
        }
        reportDiscordEvent({
            level: ["direct", "decision", "none"].includes(roomRouting.outcome) ? "info" : "warning",
            eventType: "room_routing_resolved", message: "Room routing completed.",
            guildId: guildMessage.guildId, channelId: location.channelId,
            threadId: location.threadId, sourceMessageId: guildMessage.id,
            details: {
                route_id: roomRouting.route_id, outcome: roomRouting.outcome, reason: roomRouting.reason,
                snapshot_revision: roomRouting.snapshot_revision, attempts: roomRouting.attempts,
                prompt_version: roomRouting.prompt_version,
                choices: roomRouting.choices.map(item => ({ deployment_id: item.deployment_id,
                    target_message_id: item.target_message_id }))
            }
        });
        const roomChoices = new Map(roomRouting.choices.map(item => [item.deployment_id, item]));
        const selected = candidates.filter(item => roomChoices.has(item.deployment_id));
        if (!selected.length && roomRouting.outcome !== "none" &&
            (explicitAudience || mentionedBot || replyTarget.characterMessage)) {
            await guildMessage.reply({ content: roomRouting.reason === "capacity"
                    ? "Too many characters were requested at once. Please address up to three."
                    : "This request is unavailable or blocked; it was not treated as deliberate silence.",
                allowedMentions: { parse: [], repliedUser: false } });
        }
        audience = { ...audience, deployments: selected,
            reason: roomRouting.outcome === "decision" ? (selected.length > 1
                ? "selected_smart_multiple" : "selected_smart") : audience.reason };
        if (!audience.deployments.length) {
            if (mentionedBot || replyTarget.characterMessage) {
                reportDiscordEvent({
                    level: "warning",
                    eventType: audience.reason === "ambiguous" ? "audience_ambiguous" : "audience_not_found",
                    message: audience.reason === "ambiguous"
                        ? "The Tag reached the Connector, but multiple characters require explicit selection."
                        : "The Tag reached the Connector, but no addressed character was found.",
                    guildId: guildMessage.guildId,
                    guildName: guildMessage.guild.name,
                    channelId: location.channelId,
                    channelName: location.channelName,
                    threadId: location.threadId,
                    threadName: location.threadName,
                    sourceMessageId: guildMessage.id,
                    details: {
                        audience_reason: audience.reason,
                        candidate_count: candidates.length,
                        options: audience.options
                    }
                });
            }
            if (audience.reason === "ambiguous" &&
                (mentionedBot || replyTarget.characterMessage)) {
                await sendSelectionHelp(guildMessage, audience.options);
            }
            return;
        }
        const isReplyToCharacter = audience.reason === "selected_reply";
        const eligibleDeployments = audience.deployments;
        if (!eligibleDeployments.length) {
            if (mentionedBot || isReplyToCharacter) {
                reportDiscordEvent({
                    level: "warning",
                    eventType: "ignored_participation_mode",
                    message: "The Tag matched a character, but its participation mode did not allow this trigger.",
                    guildId: guildMessage.guildId,
                    guildName: guildMessage.guild.name,
                    channelId: location.channelId,
                    channelName: location.channelName,
                    threadId: location.threadId,
                    threadName: location.threadName,
                    sourceMessageId: guildMessage.id,
                    details: {
                        mentioned_bot: mentionedBot,
                        replied_to_character: isReplyToCharacter,
                        participation_modes: audience.deployments.map((deployment) => deployment.participation_mode)
                    }
                });
            }
            return;
        }
        const addressedToMultiple = audience.deployments.length > 1;
        const socialInitialDeploymentIds = eligibleDeployments.map((item) => item.deployment_id);
        const socialContinuationDeploymentIds = candidates
            .filter((item) => shouldSubmitMessage(item, { mentionedBot: true, repliedToBot: false, hasReadableText: true }))
            .map((item) => item.deployment_id);
        const socialAvailableDeploymentIds = [
            ...new Set([
                ...socialInitialDeploymentIds,
                ...socialContinuationDeploymentIds
            ])
        ];
        let socialCursor: DiscordSocialTurnCursor | null = null;
        let socialNextTurn: DiscordSocialPendingTurn | null = null;
        let socialOperation: DiscordSocialOperationClaim | null = null;
        let durableOperationId = "";
        let socialClaimRequest: DiscordSocialOperationClaimRequest | null = null;
        const socialSources = new Map<string, {
            text: string;
            sentMessageIds: string[];
        }>();
        const applyDurableOperation = (operation: DiscordSocialOperationClaim): void => {
            socialOperation = operation;
            socialCursor = operation.cursor;
            socialNextTurn = operation.next_turn ?? null;
            socialSources.clear();
            for (const source of operation.sources) {
                socialSources.set(source.deployment_id, {
                    text: source.text,
                    sentMessageIds: source.sent_message_ids
                });
            }
        };
        {
            durableOperationId = socialOperationId({
                connectionId: config.relayConnectionId,
                guildId: guildMessage.guildId,
                channelId: location.channelId,
                threadId: location.threadId,
                sourceMessageId: guildMessage.id
            });
            socialClaimRequest = {
                operation_id: durableOperationId,
                guild_id: guildMessage.guildId,
                channel_id: location.channelId,
                thread_id: location.threadId,
                source_message_id: guildMessage.id,
                initial_deployment_ids: socialInitialDeploymentIds,
                available_deployment_ids: socialAvailableDeploymentIds,
                continuation_budget: config.botContinuationEnabled ? config.botContinuationMaxResponses : 0,
                max_depth: config.botContinuationMaxDepth
            };
            const claimed = await relay.claimSocialTurnOperation(socialClaimRequest);
            applyDurableOperation(claimed);
            if (claimed.status === "uncertain" || claimed.status === "failed") {
                reportDiscordEvent({
                    level: "warning",
                    eventType: "durable_social_turn_blocked",
                    message: "Durable Social Turn requires reconciliation before another Discord side effect.",
                    guildId: guildMessage.guildId,
                    guildName: guildMessage.guild.name,
                    channelId: location.channelId,
                    channelName: location.channelName,
                    threadId: location.threadId,
                    threadName: location.threadName,
                    sourceMessageId: guildMessage.id,
                    details: {
                        operation_id: durableOperationId,
                        status: claimed.status,
                        last_error: claimed.last_error
                    }
                });
                return;
            }
            if (claimed.status === "completed")
                return;
        }
        let processedResponses = 0;
        while (socialNextTurn) {
            const supersedingTurn = supersedingHumanTurn();
            if (supersedingTurn && socialNextTurn?.origin !== "selected") {
                if (durableOperationId) {
                    try {
                        await relay.cancelSocialTurnOperation({
                            operation_id: durableOperationId,
                            guild_id: guildMessage.guildId,
                            channel_id: location.channelId,
                            thread_id: location.threadId,
                            superseding_message_id: supersedingTurn.messageId,
                            reason: "new_human_input"
                        });
                    }
                    catch (error) {
                        reportDiscordEvent({
                            level: "warning",
                            eventType: "social_turn_interrupt_failed",
                            message: "A newer human turn arrived, but durable Social Turn cancellation failed.",
                            guildId: guildMessage.guildId,
                            guildName: guildMessage.guild.name,
                            channelId: location.channelId,
                            channelName: location.channelName,
                            threadId: location.threadId,
                            threadName: location.threadName,
                            sourceMessageId: guildMessage.id,
                            details: {
                                operation_id: durableOperationId,
                                superseding_message_id: supersedingTurn.messageId,
                                ...safeDiagnosticError(error)
                            }
                        });
                    }
                }
                reportDiscordEvent({
                    level: "info",
                    eventType: "participation_plan_interrupted",
                    message: "New human input paused optional bot continuation; direct requests remain tracked.",
                    guildId: guildMessage.guildId,
                    guildName: guildMessage.guild.name,
                    channelId: location.channelId,
                    channelName: location.channelName,
                    threadId: location.threadId,
                    threadName: location.threadName,
                    sourceMessageId: guildMessage.id,
                    details: {
                        completed_character_responses: processedResponses,
                        superseding_message_id: supersedingTurn.messageId,
                        durable_operation_id: durableOperationId || null
                    }
                });
                break;
            }
            const pendingTurn: DiscordSocialPendingTurn = (socialNextTurn as DiscordSocialPendingTurn);
            socialNextTurn = null;
            const baseDeployment = candidates.find((item) => item.deployment_id === pendingTurn.deployment_id);
            if (!baseDeployment) {
                break;
                continue;
            }
            const responseIndex = processedResponses;
            processedResponses += 1;
            const deployment = resolveDeploymentLocation(baseDeployment, location);
            reportDiscordEvent({
                level: "info",
                eventType: "runtime_started",
                message: "The Discord trigger matched a deployment and is entering Character Runtime.",
                guildId: guildMessage.guildId,
                guildName: guildMessage.guild.name,
                channelId: location.channelId,
                channelName: location.channelName,
                threadId: location.threadId,
                threadName: location.threadName,
                sourceMessageId: guildMessage.id,
                deploymentId: deployment.deployment_id,
                characterName: deploymentDisplayName(deployment),
                details: {
                    audience_reason: audience.reason,
                    response_index: responseIndex + 1,
                    response_count: eligibleDeployments.length,
                    route_id: roomRouting.route_id,
                    selection_id: roomChoices.get(deployment.deployment_id)?.selection_id ?? "",
                    target_message_id: roomChoices.get(deployment.deployment_id)?.target_message_id ?? ""
                }
            });
            const recentMessages = context.get(key);
            const socialSource = pendingTurn.origin !== "selected"
                ? socialSources.get(pendingTurn.source_deployment_id)
                : undefined;
            const sourceDeployment = socialSource
                ? candidates.find((item) => item.deployment_id === pendingTurn.source_deployment_id)
                : undefined;
            const sourceDiscordMessageId = socialSource?.sentMessageIds[0] ?? guildMessage.id;
            const expressionSource = socialSource
                ? await resolveExpressionSourceMessage(guildMessage, sourceDiscordMessageId)
                : guildMessage;
            const continuationAudience = socialSource && sourceDeployment
                ? resolveBotTagAudience(candidates, socialSource.text, sourceDeployment.deployment_id, config.groupAddressAliases)
                : null;
            const sourceDisplayName = sourceDeployment
                ? deploymentDisplayName(sourceDeployment)
                : authorDisplayName;
            const smartParticipationAudience = audience.reason === "selected_smart" ||
                audience.reason === "selected_smart_multiple";
            const turnText = socialSource
                ? continuationAudience?.text ||
                    socialSource.text ||
                    `${sourceDisplayName} tagged this character without additional readable text.`
                : (smartParticipationAudience
                    ? originalText
                    : addressedToMultiple
                        ? originalText
                        : audience.text) ||
                    originalText ||
                    (emojis.length || stickers.length
                        ? "The user addressed the character with interpreted Discord expression content and no text."
                        : "The user addressed the character without additional readable text.");
            const mentionableParticipants = buildMentionableParticipants(candidates, recentMessages, deployment);
            await expressionSource.channel.sendTyping();
            const inboundPayload = {
                deployment_id: deployment.deployment_id,
                message_id: sourceDiscordMessageId,
                guild_id: guildMessage.guildId,
                guild_name: guildMessage.guild.name,
                channel_id: location.channelId,
                channel_name: location.channelName,
                category_id: location.categoryId,
                thread_id: location.threadId,
                thread_name: location.threadName,
                author_id: sourceDeployment
                    ? `character:${sourceDeployment.character_card_id}`
                    : (webActor?.actor_id ?? guildMessage.author.id),
                author_display_name: sourceDisplayName,
                text: turnText,
                source_selection_id: socialSource ? "" :
                    roomChoices.get(deployment.deployment_id)?.selection_id ?? "",
                source_created_at: expressionSource.createdAt.toISOString(),
                ...(expressionSource.editedAt ? { source_edited_at: expressionSource.editedAt.toISOString() } : {}),
                mentioned_bot: socialSource ? true : mentionedBot,
                replied_to_bot: socialSource ? false : isReplyToCharacter,
                reply_to_message_id: socialSource ? "" : (webActor?.reply_to_message_id ?? guildMessage.reference?.messageId ?? ""),
                smart_candidate: socialSource
                    ? false
                    : deployment.participation_mode === "smart" &&
                        config.ambientParticipationEnabled,
                author_is_bot: Boolean(sourceDeployment || webActor),
                emojis: socialSource ? [] : emojis,
                stickers: socialSource ? [] : stickers,
                media_descriptors: [],
                burst_media_message_ids: socialSource ? [] : burstMediaMessageIds,
                conversation_burst_id: socialSource ? "" : participationBurstId,
                burst_source_message_ids: socialSource
                    ? []
                    : participationBurstMessages.map((item) => item.message_id),
                available_characters: candidates
                    .filter((item) => item.deployment_id !== deployment.deployment_id)
                    .map(deploymentAddressAlias),
                mentionable_participants: mentionableParticipants,
                recent_messages: recentMessages
            };
            let socialStep: DiscordSocialTurnStepReply | null = null;
            let reply: DiscordReply;
            try {
                reply =
                    ((socialStep = await relay.processSocialTurnStep({
                        payload: inboundPayload,
                        initial_deployment_ids: socialInitialDeploymentIds,
                        available_deployment_ids: socialAvailableDeploymentIds,
                        continuation_budget: config.botContinuationEnabled ? config.botContinuationMaxResponses : 0,
                        max_depth: config.botContinuationMaxDepth,
                        cursor: socialCursor,
                        operation_id: durableOperationId
                    }, {
                        onProgress: (text) => deliverCharacterTurnProgress(guildMessage, deployment, text, botUser.id, key),
                        onProgressDeliveryError: (error) => {
                            log("Character turn progress delivery is uncertain; waiting for the final reply.", {
                                deploymentId: deployment.deployment_id,
                                sourceMessageId: guildMessage.id,
                                ...safeDiagnosticError(error)
                            });
                        }
                    })),
                        socialStep.reply);
            }
            catch (error) {
                if (error instanceof TurnJobTerminalError) {
                    if (!(await claimTerminalTurnFailure(error)))
                        continue;
                    await deliverCharacterTurnFailure(guildMessage, deployment, botUser.id, key);
                    reportDiscordEvent({
                        level: "warning",
                        eventType: "turn_job_terminal",
                        message: "Character Runtime could not complete the asynchronous turn.",
                        guildId: guildMessage.guildId,
                        guildName: guildMessage.guild.name,
                        channelId: location.channelId,
                        channelName: location.channelName,
                        threadId: location.threadId,
                        threadName: location.threadName,
                        sourceMessageId: guildMessage.id,
                        deploymentId: deployment.deployment_id,
                        characterName: deploymentDisplayName(deployment),
                        details: {
                            status: error.status,
                            error_code: error.errorCode
                        }
                    });
                    continue;
                }
                throw error;
            }
            if (socialStep && !socialStep.delivery_required) {
                socialCursor = socialStep.cursor;
                socialNextTurn = socialStep.next_turn ?? null;
            }
            reportCharacterContext({
                trace: reply.context_trace,
                source: guildMessage,
                deployment
            });
            if (reply.action === "silent" ||
                reply.smart_output?.action === "ignore" ||
                (!reply.smart_output && !reply.text && reply.expression.action === "none")) {
                reportDiscordEvent({
                    level: "info",
                    eventType: "runtime_silent",
                    message: "Character Runtime intentionally returned no Discord reply.",
                    guildId: guildMessage.guildId,
                    guildName: guildMessage.guild.name,
                    channelId: location.channelId,
                    channelName: location.channelName,
                    threadId: location.threadId,
                    threadName: location.threadName,
                    sourceMessageId: guildMessage.id,
                    deploymentId: deployment.deployment_id,
                    characterName: deploymentDisplayName(deployment),
                    details: {
                        reason: reply.reason,
                        latency_ms: reply.latency_ms ?? null,
                        input_tokens: reply.input_tokens ?? null,
                        output_tokens: reply.output_tokens ?? null
                    }
                });
                continue;
            }
            let execution: ExpressionExecutionResult | SmartOutputExecutionResult;
            let deliveryClaimNonce = "";
            let deliveryClaimed = false;
            const releasePublication = await roomPublications.acquire(key);
            try {
                if (socialStep?.delivery_required &&
                    socialStep.step_id &&
                    socialClaimRequest) {
                    const check = await preflightReply(guildMessage, reply, durableOperationId, socialStep.step_id);
                    if (check.cursor)
                        socialStep.cursor = check.cursor;
                    if (check.disposition === "drop" || check.disposition === "blocked") {
                        applyDurableOperation(await relay.claimSocialTurnOperation(socialClaimRequest));
                        continue;
                    }
                    deliveryClaimNonce = randomUUID();
                    const deliveryClaim = await relay.claimSocialTurnDelivery({
                        operation_id: durableOperationId,
                        step_id: socialStep.step_id,
                        claim_nonce: deliveryClaimNonce
                    });
                    if (deliveryClaim.claim_status === "uncertain") {
                        throw new Error("Durable Discord delivery is uncertain; refusing to resend.");
                    }
                    if (deliveryClaim.claim_status === "already_delivered") {
                        applyDurableOperation(await relay.claimSocialTurnOperation(socialClaimRequest));
                        continue;
                    }
                    deliveryClaimed = true;
                }
                execution = reply.smart_output
                    ? await executeSmartOutput(guildMessage, deployment, reply.smart_output, botUser.id, candidates, mentionableParticipants)
                    : await executeCharacterOutput(guildMessage, deployment, reply.text
                        ? normalizeBotTagReply(candidates, reply.text, deployment.deployment_id, config.groupAddressAliases).displayText.trim()
                        : "", botUser.id);
                if (deliveryClaimed &&
                    socialStep?.step_id &&
                    socialCursor) {
                    const acknowledged = await relay.acknowledgeSocialTurnDelivery({
                        operation_id: durableOperationId,
                        step_id: socialStep.step_id,
                        claim_nonce: deliveryClaimNonce,
                        deployment_id: deployment.deployment_id,
                        cursor: socialStep.cursor,
                        sent_message_ids: execution.sentMessageIds,
                        outgoing_text: execution.outgoingText,
                        applied: execution.applied
                    });
                    applyDurableOperation(acknowledged);
                }
            }
            catch (error) {
                if (deliveryClaimed && socialStep?.step_id) {
                    await relay
                        .markSocialTurnDeliveryUncertain({
                        operation_id: durableOperationId,
                        step_id: socialStep.step_id,
                        claim_nonce: deliveryClaimNonce,
                        sent_message_ids: [...deliveryFailure(error).sentMessageIds],
                        error: formatSafeDiagnosticError(error)
                    })
                        .catch(() => undefined);
                }
                reportDiscordEvent({
                    level: "error",
                    eventType: "delivery_error",
                    message: "Character Runtime replied, but Discord delivery failed.",
                    guildId: guildMessage.guildId,
                    guildName: guildMessage.guild.name,
                    channelId: location.channelId,
                    channelName: location.channelName,
                    threadId: location.threadId,
                    threadName: location.threadName,
                    sourceMessageId: guildMessage.id,
                    deploymentId: deployment.deployment_id,
                    characterName: deploymentDisplayName(deployment),
                    details: safeDiagnosticError(error)
                });
                throw error;
            }
            finally {
                releasePublication();
            }
            const sentMessageIds = execution.sentMessageIds;
            const outgoingText = execution.outgoingText;
            await rememberSentMessages(deployment, sentMessageIds, guildMessage.guildId);
            if (sentMessageIds.length) {
                context.push(key, {
                    message_id: sentMessageIds[0] ?? `relay-expression-${Date.now()}`,
                    author_id: `character:${deployment.character_card_id}`,
                    author_deployment_id: deployment.deployment_id,
                    author_display_name: deploymentDisplayName(deployment),
                    text: outgoingText,
                    emojis: [],
                    stickers: [],
                    created_at: new Date().toISOString(),
                    is_bot: true
                });
            }
            reportDiscordEvent({
                level: execution.applied ? "info" : "warning",
                eventType: execution.applied ? "expression_execution_success" : "expression_skipped",
                message: execution.applied
                    ? "A retrieved Server expression was applied to the character response."
                    : "The character response completed without a Server expression.",
                guildId: guildMessage.guildId,
                guildName: guildMessage.guild.name,
                channelId: location.channelId,
                channelName: location.channelName,
                threadId: location.threadId,
                threadName: location.threadName,
                sourceMessageId: guildMessage.id,
                deploymentId: deployment.deployment_id,
                characterName: deploymentDisplayName(deployment),
                details: {
                    action: execution.action,
                    resource_key: execution.resourceKey || null,
                    fallback: execution.fallback
                }
            });
            reportDiscordEvent({
                level: "info",
                eventType: sentMessageIds.length || execution.applied ? "delivery_success" : "delivery_not_applied",
                message: sentMessageIds.length || execution.applied
                    ? "Character output was delivered to Discord."
                    : "No Discord output was applied; the draft did not become dialogue history.",
                guildId: guildMessage.guildId,
                guildName: guildMessage.guild.name,
                channelId: location.channelId,
                channelName: location.channelName,
                threadId: location.threadId,
                threadName: location.threadName,
                sourceMessageId: guildMessage.id,
                deploymentId: deployment.deployment_id,
                characterName: deploymentDisplayName(deployment),
                details: {
                    sent_message_ids: sentMessageIds,
                    expression_action: execution.action,
                    expression_resource_key: execution.resourceKey || null,
                    expression_fallback: execution.fallback,
                    latency_ms: reply.latency_ms ?? null,
                    input_tokens: reply.input_tokens ?? null,
                    output_tokens: reply.output_tokens ?? null,
                    route_id: roomRouting.route_id,
                    participation_reason: roomRouting.reason,
                    identity_mode: deployment.identity_mode,
                    webhook_status: deployment.webhook_status
                }
            });
            log("Character reply sent to Discord.", {
                deploymentId: reply.deployment_id,
                characterId: deployment.character_card_id,
                audienceReason: audience.reason,
                audienceSize: audience.deployments.length,
                responseIndex: responseIndex + 1,
                responseCount: eligibleDeployments.length,
                identityMode: deployment.identity_mode,
                webhookStatus: deployment.webhook_status,
                serverProfileId: deployment.server_profile_id || null,
                guildId: guildMessage.guildId,
                channelId: location.channelId,
                categoryId: location.categoryId || null,
                threadId: location.threadId || null,
                sourceMessageId: guildMessage.id,
                sentMessageIds,
                latencyMs: reply.latency_ms ?? null
            });
            {
                if (!durableOperationId) {
                    if (sentMessageIds.length) {
                        socialSources.set(deployment.deployment_id, {
                            text: outgoingText,
                            sentMessageIds
                        });
                    }
                    else if (socialCursor) {
                        socialCursor.pending_turns = socialCursor.pending_turns.filter((item) => item.source_deployment_id !== deployment.deployment_id);
                        socialNextTurn = socialCursor.pending_turns[0] ?? null;
                    }
                }
            }
        }
    };
    const explicitAudience = resolveExplicitAudiencePreflight(candidates, originalText, null, config.groupAddressAliases);
    const customEmojiCount = parseCustomEmojiTokens(guildMessage.content).length;
    const smartCandidateCount = candidates.filter((item) => item.participation_mode === "smart").length;
    const visibleImageCount = visibleImageAttachmentCount(guildMessage);
    const collectionDecision = decideTurnCollection({
        collectorEnabled: turnIngress.enabled,
        ambientParticipationEnabled: config.ambientParticipationEnabled,
        recovery: Boolean(options?.recovery),
        mentionedBot,
        hasReplyReference: Boolean(guildMessage.reference?.messageId),
        explicitAudience: Boolean(explicitAudience),
        hasReadableText: Boolean(originalText.trim()),
        customEmojiCount,
        stickerCount: guildMessage.stickers.size,
        attachmentCount: guildMessage.attachments.size,
        visibleImageAttachmentCount: visibleImageCount,
        embedCount: guildMessage.embeds.length,
        hasUrl: /https?:\/\//iu.test(guildMessage.content),
        smartCandidateCount
    });
    if (collectionDecision.collect) {
        turnCollectorCandidateMessageCount += 1;
        log("Smart Participation message entered the Turn Collector.", {
            guildId: guildMessage.guildId,
            channelId: location.channelId,
            threadId: location.threadId || null,
            sourceMessageId: guildMessage.id,
            pendingBurstScopes: turnIngress.pendingBurstScopeCount,
            quietWindowMs: config.roomBufferQuietMs
        });
    }
    else {
        turnCollectorBypassMessageCount += 1;
        turnCollectorBypassReasons[collectionDecision.reason] =
            (turnCollectorBypassReasons[collectionDecision.reason] ?? 0) + 1;
    }
    let webComplete: (() => void) | undefined;
    let webFailed: ((error: unknown) => void) | undefined;
    const webCompletion = webActor ? new Promise<void>((resolve, reject) => { webComplete = resolve; webFailed = reject; }) : null;
    // Install a rejection handler before a synchronous queue-capacity callback can reject.
    void webCompletion?.catch(() => undefined);
    turnIngress.submit(key, {
        id: guildMessage.id,
        value: collectedTurn,
        characters: originalText.length,
        receivedAt: guildMessage.createdTimestamp,
        collect: collectionDecision.collect,
        execute: async (burst) => {
            try { await executeQueued(burst); webComplete?.(); }
            catch (error) { webFailed?.(error); throw error; }
        },
        onRejected: (reason) => {
            webFailed?.(new Error(`web_turn_${reason}`));
            if (collectionDecision.collect || !mentionedBot && !explicitAudience)
                return;
            const text = reason === "expired"
                ? "That request waited too long before it could start. Please send it again."
                : "I’m handling the maximum number of requests for this conversation. Please try again shortly.";
            void guildMessage.reply({
                content: text,
                allowedMentions: { parse: [], repliedUser: false }
            }).catch((error: unknown) => {
                log("Unable to show explicit Discord turn ingress status.", {
                    sourceMessageId: guildMessage.id,
                    reason,
                    ...safeDiagnosticError(error)
                });
            });
        }
    });
    if (webCompletion) await webCompletion;
}
async function resumePendingSocialTurns(): Promise<void> {
    const pending = await relay.listPendingSocialTurnOperations();
    for (const operation of pending) {
        try {
            const guild = client.guilds.cache.get(operation.guild_id) ??
                (await client.guilds.fetch(operation.guild_id));
            const sourceChannelId = operation.thread_id || operation.channel_id;
            const channel = await guild.channels.fetch(sourceChannelId);
            if (!channel || !channel.isTextBased() || !("messages" in channel)) {
                throw new Error("Durable Social Turn source channel is unavailable.");
            }
            const source = await channel.messages.fetch(operation.source_message_id);
            if (!source.inGuild()) {
                throw new Error("Durable Social Turn source message is not a Guild message.");
            }
            const recoveredWebActor = source.author.bot ? await relay.webSource(source.id) : null;
            if (source.author.bot && !recoveredWebActor) throw new Error("recovery_source_authority_unavailable");
            await processMessage(source, { recovery: true, ...(recoveredWebActor ? {webActor: recoveredWebActor} : {}) });
            reportDiscordEvent({
                level: "info",
                eventType: "durable_social_turn_resume_queued",
                message: "A durable Social Turn was queued for checkpoint resume.",
                guildId: operation.guild_id,
                channelId: operation.channel_id,
                threadId: operation.thread_id,
                sourceMessageId: operation.source_message_id,
                details: {
                    operation_id: operation.operation_id,
                    operation_status: operation.status
                }
            });
        }
        catch (error) {
            log("Unable to resume durable Social Turn.", {
                operationId: operation.operation_id,
                sourceMessageId: operation.source_message_id,
                ...safeDiagnosticError(error)
            });
        }
    }
}
async function resumeRecoverableMessageTurn(job: DiscordTurnJobDescriptor): Promise<void> {
    const botUser = client.user;
    if (!botUser)
        throw new Error("Discord client is unavailable for Turn Job recovery.");
    const guild = client.guilds.cache.get(job.guild_id) ??
        (await client.guilds.fetch(job.guild_id));
    const sourceChannelId = job.thread_id || job.channel_id;
    const channel = await guild.channels.fetch(sourceChannelId);
    if (!channel || !channel.isTextBased() || !("messages" in channel)) {
        throw new Error("Recoverable Character Turn source channel is unavailable.");
    }
    const source = await channel.messages.fetch(job.source_message_id);
    if (!source.inGuild()) {
        throw new Error("Recoverable Character Turn source message is not a Guild message.");
    }
    const location = channelLocation(source);
    const candidates = deploymentsFor(deployments, location.channelId, location.threadId, source.guildId, location.categoryId);
    const baseDeployment = candidates.find((item) => item.deployment_id === job.deployment_id);
    if (!baseDeployment) {
        throw new Error("Recoverable Character Turn deployment is no longer active at its destination.");
    }
    const deployment = resolveDeploymentLocation(baseDeployment, location);
    const key = destinationKey(location.channelId, location.threadId);
    const recentMessages = context.get(key);
    const mentionableParticipants = buildMentionableParticipants(candidates, recentMessages, deployment);
    let reply: DiscordReply;
    try {
        reply = await relay.resumeMessageTurnJob(job.job_id, {
            onProgress: (text) => deliverCharacterTurnProgress(source, deployment, text, botUser.id, key),
            onProgressDeliveryError: (error) => {
                log("Recovered Character Turn progress delivery is uncertain; waiting for the final reply.", {
                    jobId: job.job_id,
                    deploymentId: deployment.deployment_id,
                    sourceMessageId: source.id,
                    ...safeDiagnosticError(error)
                });
            }
        });
    }
    catch (error) {
        if (error instanceof TurnJobTerminalError) {
            if (!await claimTerminalTurnFailure(error))
                return;
            await deliverCharacterTurnFailure(source, deployment, botUser.id, key);
            reportDiscordEvent({
                level: "warning",
                eventType: "turn_job_recovery_terminal",
                message: "A recovered Character Turn could not complete.",
                guildId: job.guild_id,
                guildName: guild.name,
                channelId: job.channel_id,
                channelName: location.channelName,
                threadId: job.thread_id,
                threadName: location.threadName,
                sourceMessageId: job.source_message_id,
                deploymentId: job.deployment_id,
                characterName: deploymentDisplayName(deployment),
                details: { status: error.status, error_code: error.errorCode, job_id: job.job_id }
            });
            return;
        }
        throw error;
    }
    if (reply.action === "silent" ||
        reply.smart_output?.action === "ignore" ||
        !reply.smart_output && !reply.text && reply.expression.action === "none") {
        return;
    }
    const durableDelivery = await claimCharacterTurnDelivery(reply, source);
    if (durableDelivery === "already_delivered" || durableDelivery === "suppressed")
        return;
    let execution: ExpressionExecutionResult | SmartOutputExecutionResult;
    try {
        execution = reply.smart_output
            ? await executeSmartOutput(source, deployment, reply.smart_output, botUser.id, candidates, mentionableParticipants)
            : await executeCharacterOutput(source, deployment, reply.text
                ? normalizeBotTagReply(candidates, reply.text, deployment.deployment_id, config.groupAddressAliases).displayText.trim()
                : "", botUser.id);
        await acknowledgeCharacterTurnDelivery(durableDelivery, execution.sentMessageIds, execution.applied);
    }
    catch (error) {
        await markCharacterTurnDeliveryUncertain(durableDelivery, error);
        throw error;
    }
    await rememberSentMessages(deployment, execution.sentMessageIds, source.guildId);
    if (execution.outgoingText || execution.sentMessageIds.length) {
        context.push(key, {
            message_id: execution.sentMessageIds[0] ?? `relay-recovered-${Date.now()}`,
            author_id: `character:${deployment.character_card_id}`,
            author_deployment_id: deployment.deployment_id,
            author_display_name: deploymentDisplayName(deployment),
            text: execution.outgoingText,
            emojis: [],
            stickers: [],
            created_at: new Date().toISOString(),
            is_bot: true
        });
    }
    reportDiscordEvent({
        level: "info",
        eventType: "turn_job_recovery_delivered",
        message: "A recovered Character Turn reply was delivered to Discord.",
        guildId: job.guild_id,
        guildName: guild.name,
        channelId: job.channel_id,
        channelName: location.channelName,
        threadId: job.thread_id,
        threadName: location.threadName,
        sourceMessageId: job.source_message_id,
        deploymentId: job.deployment_id,
        characterName: deploymentDisplayName(deployment),
        details: { job_id: job.job_id, sent_message_ids: execution.sentMessageIds }
    });
}
function scheduleRecoverableTurnJobs(): Promise<void> {
    if (turnJobRecoveryScan)
        return turnJobRecoveryScan;
    turnJobRecoveryScan = scanRecoverableTurnJobs().finally(() => {
        turnJobRecoveryScan = null;
    });
    return turnJobRecoveryScan;
}
async function scanRecoverableTurnJobs(): Promise<void> {
    const maximumQueued = config.turnJobRecoveryMaxConcurrent * 4;
    const availableQueueCapacity = maximumQueued - pendingTurnJobRecoveries.size;
    if (availableQueueCapacity <= 0 || shuttingDown)
        return;
    const jobs = await relay.listRecoverableTurnJobs(availableQueueCapacity);
    for (const job of jobs) {
        if (job.kind !== "message" ||
            recoveringTurnJobIds.has(job.job_id) ||
            pendingTurnJobRecoveries.has(job.job_id))
            continue;
        pendingTurnJobRecoveries.set(job.job_id, job);
    }
    startPendingTurnJobRecoveries();
}
function startPendingTurnJobRecoveries(): void {
    while (!shuttingDown &&
        turnJobRecoveryTasks.size < config.turnJobRecoveryMaxConcurrent) {
        const next = pendingTurnJobRecoveries.entries().next();
        if (next.done)
            return;
        const [jobId, job] = next.value;
        pendingTurnJobRecoveries.delete(jobId);
        if (recoveringTurnJobIds.has(jobId))
            continue;
        recoveringTurnJobIds.add(job.job_id);
        let task: Promise<void>;
        task = resumeRecoverableMessageTurn(job)
            .catch((error: unknown) => {
            log("Unable to resume recoverable Character Turn.", {
                jobId: job.job_id,
                sourceMessageId: job.source_message_id,
                ...safeDiagnosticError(error)
            });
        })
            .finally(() => {
            recoveringTurnJobIds.delete(job.job_id);
            turnJobRecoveryTasks.delete(task);
            startPendingTurnJobRecoveries();
        });
        turnJobRecoveryTasks.add(task);
    }
}
const healthServer = createServer((request, response) => {
    if (request.url !== "/health") {
        response.writeHead(404, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ detail: "Not found" }));
        return;
    }
    const activeDeployments = flattenDeployments(deployments);
    const webhookDeployments = activeDeployments.filter((item) => item.identity_mode === "webhook");
    response.writeHead(ready ? 200 : 503, { "Content-Type": "application/json" });
    response.end(JSON.stringify({
        name: "Character Relay Discord Connector",
        status: ready ? (stateSynchronized ? "ready" : "degraded") : "starting",
        gateway_ready: ready,
        state_synchronized: stateSynchronized,
        railway_replica_region: process.env.RAILWAY_REPLICA_REGION ?? null,
        discord_user: client.user?.tag ?? null,
        connection_id: config.relayConnectionId,
        active_deployments: activeDeployments.length,
        server_wide_deployments: activeDeployments.filter((item) => item.channel_scope_mode === "all_except").length,
        active_destinations: deployments.size,
        multi_character_destinations: [...deployments.values()].filter((items) => items.length > 1).length,
        cached_message_routes: sentCharacterRoutes.size,
        observed_webhooks: observedWebhookIds.size,
        webhook_deployments: webhookDeployments.length,
        webhook_ready: webhookDeployments.filter((item) => item.webhook_status === "active").length,
        webhook_errors: webhookDeployments.filter((item) => item.webhook_status === "error").length,
        message_content_intent: config.messageContentIntent,
        smart_participation_enabled: config.ambientParticipationEnabled,
        smart_participation_v3_resolver_enabled: config.ambientParticipationEnabled,
        smart_participation_turn_collector_enabled: turnIngress.enabled,
        smart_participation_turn_collector_quiet_ms: turnIngress.currentConfig.quietWindowMs,
        smart_participation_turn_collector_max_wait_ms: turnIngress.currentConfig.maxWaitMs,
        smart_participation_turn_collector_max_messages: turnIngress.currentConfig.maxMessages,
        smart_participation_turn_collector_max_characters: turnIngress.currentConfig.maxCharacters,
        smart_participation_turn_collector_pending_scopes: turnIngress.pendingBurstScopeCount,
        smart_participation_ingress_pending_scopes: turnIngress.pendingPreflightScopeCount,
        smart_participation_turn_collector_candidate_messages: turnCollectorCandidateMessageCount,
        smart_participation_turn_collector_bypass_messages: turnCollectorBypassMessageCount,
        smart_participation_turn_collector_bypass_reasons: turnCollectorBypassReasons,
        smart_participation_turn_collector_interaction_bypasses: turnCollectorInteractionBypassCount,
        smart_participation_turn_collector_bursts: turnCollectorBurstCount,
        smart_participation_turn_collector_collected_messages: turnCollectorCollectedMessageCount,
        smart_participation_turn_collector_collapsed_messages: turnCollectorCollapsedMessageCount,
        smart_participation_turn_collector_last_burst_at: turnCollectorLastBurstAt,
        smart_participation_turn_collector_last_burst_id: turnCollectorLastBurstId,
        smart_participation_turn_collector_last_flush_reason: turnCollectorLastFlushReason,
        bot_tag_conversations_enabled: config.botContinuationEnabled,
        bot_tag_max_depth: config.botContinuationMaxDepth,
        bot_tag_max_responses: config.botContinuationMaxResponses,
        custom_group_address_aliases: config.groupAddressAliases.length,
        interaction_sessions_enabled: true,
        sticker_understanding_enabled: true,
        expression_retrieval_enabled: true,
        expression_retrieval_backend: "hybrid_sparse_v1",
        smart_output_v1_enabled: true,
        expression_max_candidates: 6,
        expression_max_per_character_reply: 1,
        last_catalog_sync_at: lastCatalogSyncAt,
        last_deployment_sync_at: lastDeploymentSyncAt,
        last_error: lastError,
        pending_portal_logs: eventReporter.pendingCount,
        portal_log_last_error: eventReporter.lastError
    }));
});
const webRoomBridge = new WebRoomBridge(client, relay, config.messageContentIntent,
    (message, claim) => processMessage(message, {recovery: true, webActor: claim}), log);
client.once(Events.ClientReady, (readyClient) => {
    ready = true;
    log("Discord Gateway connected.", {
        discordUser: readyClient.user.tag,
        connectionId: config.relayConnectionId,
        railwayReplicaRegion: process.env.RAILWAY_REPLICA_REGION ?? null
    });
    recoveryLoop = new RecoveryLoop(config.deploymentRefreshSeconds * 1000, {
        execute: refreshConnectorState,
        succeeded: async () => {
            const recovered = !stateSynchronized || Boolean(lastError);
            stateSynchronized = true;
            webRoomBridge.start();
            lastError = null;
            await sendHeartbeat("connected").catch((error: unknown) => {
                lastError = formatSafeDiagnosticError(error);
                log("Connector heartbeat failed after state synchronization.", {
                    ...safeDiagnosticError(error)
                });
            });
            if (recovered) {
                log("Discord connector state synchronized.", {
                    discordUser: readyClient.user.tag,
                    connectionId: config.relayConnectionId,
                    activeDeployments: flattenDeployments(deployments).length,
                    activeDestinations: deployments.size
                });
                await resumePendingSocialTurns().catch((error: unknown) => {
                    lastError = formatSafeDiagnosticError(error);
                    log("Durable Social Turn recovery scan failed.", safeDiagnosticError(error));
                });
            }
            void scheduleRecoverableTurnJobs().catch((error: unknown) => {
                lastError = formatSafeDiagnosticError(error);
                log("Recoverable Character Turn scan failed.", safeDiagnosticError(error));
            });
        },
        failed: async (error: unknown) => {
            lastError = formatSafeDiagnosticError(error);
            log("Connector state synchronization failed; retry scheduled.", {
                ...safeDiagnosticError(error),
                retrySeconds: config.deploymentRefreshSeconds
            });
            await sendHeartbeat("error", lastError).catch(() => undefined);
        }
    });
    recoveryLoop.start();
    heartbeatTimer = setInterval(() => {
        const status = stateSynchronized ? "connected" : "error";
        const error = stateSynchronized
            ? ""
            : (lastError ?? "Waiting for initial Character Relay synchronization.");
        void sendHeartbeat(status, error).catch((reason: unknown) => {
            lastError = formatSafeDiagnosticError(reason);
            log("Connector heartbeat failed.", safeDiagnosticError(reason));
        });
    }, config.heartbeatSeconds * 1000);
});
function observeIncomingMessage(message: Message): void {
    if (!client.user || !message.inGuild())
        return;
    const location = channelLocation(message);
    if (!location.channelId || (!deploymentsFor(deployments, location.channelId, location.threadId, message.guildId, location.categoryId).length && !webRoomBridge.hasRoom(message.guildId, location.channelId, location.threadId)))
        return;
    const source = rawRoomSource(message, config.messageContentIntent);
    context.push(destinationKey(location.channelId, location.threadId), sourceContext(source), true);
    roomEvents.publish(roomLocation(message), source, () => checkRoomAccess(message));
}
client.on(Events.MessageUpdate, (_previous, current) => {
    // Partial events cannot supply trustworthy replacement text. Remove stale buffered content;
    // a future authorized history read can rehydrate it. Do not regenerate a reply on every edit.
    if (!current.inGuild())
        return;
    const location = channelLocation(current);
    const key = destinationKey(location.channelId, location.threadId);
    if (current.partial) {
        context.invalidate(key, current.id);
        // Never manufacture replacement text from a partial Gateway update.
        void current.fetch().then(fresh => observeIncomingMessage(fresh)).catch(error => {
            log("Partial source edit needs a fresh read before publication.", {
                messageId: current.id, ...safeDiagnosticError(error)
            });
        });
        return;
    }
    observeIncomingMessage(current);
});
function observeDeletedMessage(message: Message | import("discord.js").PartialMessage): void {
    if (!message.inGuild())
        return;
    const location = channelLocation(message);
    context.remove(destinationKey(location.channelId, location.threadId), message.id);
    if (!deploymentsFor(deployments, location.channelId, location.threadId, message.guildId, location.categoryId).length && !webRoomBridge.hasRoom(message.guildId, location.channelId, location.threadId))
        return;
    roomEvents.publish({ guild_id: message.guildId, channel_id: location.channelId,
        thread_id: location.threadId, category_id: location.categoryId }, {
        message_id: message.id, channel_id: location.channelId, thread_id: location.threadId,
        author_id: "", author_display_name: "", author_is_bot: false, author_deployment_id: "",
        text: "", reply_to_message_id: "", created_at: message.createdAt.toISOString(),
        edited_at: null, deleted: true, content_available: false, has_unseen_media: false
    }, () => checkRoomAccess(message));
}
async function observeReactionMessage(message: Message | import("discord.js").PartialMessage): Promise<void> {
    try {
        // Reaction deltas can arrive against an otherwise complete cached Message. Always fetch
        // the exact message so Web Room receives authoritative aggregate counts, not cache timing.
        const fresh = await message.fetch();
        if (fresh.inGuild()) observeIncomingMessage(fresh);
    }
    catch (error) {
        log("Reaction state needs a fresh message read before Web Room publication.", {
            messageId: message.id, ...safeDiagnosticError(error)
        });
    }
}
client.on(Events.MessageReactionAdd, reaction => { void observeReactionMessage(reaction.message); });
client.on(Events.MessageReactionRemove, reaction => { void observeReactionMessage(reaction.message); });
client.on(Events.MessageReactionRemoveAll, message => { void observeReactionMessage(message); });
client.on(Events.MessageReactionRemoveEmoji, reaction => { void observeReactionMessage(reaction.message); });
client.on(Events.MessagePollVoteAdd, answer => { void observeReactionMessage(answer.poll.message); });
client.on(Events.MessagePollVoteRemove, answer => { void observeReactionMessage(answer.poll.message); });
client.on(Events.MessageDelete, observeDeletedMessage);
client.on(Events.MessageBulkDelete, messages => {
    for (const message of messages.values())
        observeDeletedMessage(message);
});
client.on(Events.MessageCreate, (message) => {
    observeIncomingMessage(message);
    void processMessage(message).catch((error: unknown) => {
        lastError = formatSafeDiagnosticError(error);
        if (message.inGuild()) {
            const location = channelLocation(message);
            reportDiscordEvent({
                level: "error",
                eventType: "handler_error",
                message: "Discord message processing failed before a reply could be delivered.",
                guildId: message.guildId,
                guildName: message.guild.name,
                channelId: location.channelId,
                channelName: location.channelName,
                threadId: location.threadId,
                threadName: location.threadName,
                sourceMessageId: message.id,
                details: safeDiagnosticError(error)
            });
        }
        log("Discord message handler failed.", {
            messageId: message.id,
            ...safeDiagnosticError(error)
        });
    });
});
client.on(Events.GuildCreate, () => {
    void syncServerCatalog().catch((error: unknown) => {
        lastError = formatSafeDiagnosticError(error);
        log("Server catalog refresh failed after guild create.", safeDiagnosticError(error));
    });
});
client.on(Events.GuildDelete, () => {
    void syncServerCatalog().catch((error: unknown) => {
        lastError = formatSafeDiagnosticError(error);
        log("Server catalog refresh failed after guild delete.", safeDiagnosticError(error));
    });
});
client.on(Events.Error, (error) => {
    lastError = formatSafeDiagnosticError(error);
    log("Discord client error.", safeDiagnosticError(error));
});
dedupeTimer = setInterval(() => {
    const cutoff = Date.now() - 60 * 60 * 1000;
    for (const [messageId, seenAt] of processedMessages) {
        if (seenAt < cutoff)
            processedMessages.delete(messageId);
    }
    for (const [messageId, route] of sentCharacterRoutes) {
        if (route.seenAt < cutoff)
            sentCharacterRoutes.delete(messageId);
    }
}, 10 * 60 * 1000);
async function shutdown(signal: string): Promise<void> {
    shuttingDown = true;
    pendingTurnJobRecoveries.clear();
    ready = false;
    stateSynchronized = false;
    recoveryLoop?.stop();
    await webRoomBridge.stop();
    client.removeAllListeners(Events.MessageCreate);
    client.removeAllListeners(Events.MessageUpdate);
    client.removeAllListeners(Events.MessageDelete);
    client.removeAllListeners(Events.MessageReactionAdd);
    client.removeAllListeners(Events.MessageReactionRemove);
    client.removeAllListeners(Events.MessageReactionRemoveAll);
    client.removeAllListeners(Events.MessageReactionRemoveEmoji);
    client.removeAllListeners(Events.MessagePollVoteAdd);
    client.removeAllListeners(Events.MessagePollVoteRemove);
    client.removeAllListeners(Events.MessageBulkDelete);
    relay.stopTurnJobs();
    await turnIngress.shutdown(true);
    await Promise.all([...turnJobRecoveryTasks].map((task) => task.catch(() => undefined)));
    await workQueue.drain();
    await roomEvents.stop();
    await eventReporter.stop();
    if (heartbeatTimer)
        clearInterval(heartbeatTimer);
    if (dedupeTimer)
        clearInterval(dedupeTimer);
    await sendHeartbeat("offline", `Connector stopped by ${signal}.`).catch(() => undefined);
    client.destroy();
    healthServer.close();
    log("Discord connector stopped.", { signal });
}
process.once("SIGTERM", () => {
    void shutdown("SIGTERM").finally(() => process.exit(0));
});
process.once("SIGINT", () => {
    void shutdown("SIGINT").finally(() => process.exit(0));
});
healthServer.listen(config.port, "0.0.0.0", () => {
    log("Discord connector health server listening.", { port: config.port });
});
await client.login(config.discordBotToken);
