import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

import {
  ChannelType,
  Client,
  Events,
  GatewayIntentBits,
  Partials,
  type Message
} from "discord.js";

import { resolveExplicitAudiencePreflight } from "./audiencePreflight.js";
import { loadConfig } from "./config.js";
import { ContextBuffer } from "./contextBuffer.js";
import {
  socialOperationId,
  type DiscordSocialOperationClaim,
  type DiscordSocialOperationClaimRequest
} from "./durableRuntime.js";
import { detectBotMention, stripBotMentionTokens } from "./mentionDetection.js";
import {
  expressionCandidate,
  expressionQuery,
  fallbackExpressionCandidate,
  parseCustomEmojiTokens,
  renderCustomEmoji,
  stripCustomEmojiTokens
} from "./expressionFlow.js";
import { DiscordEventReporter } from "./eventReporter.js";
import { RelayClient } from "./relayClient.js";
import { RecoveryLoop } from "./recoveryLoop.js";
import {
  buildDeploymentIndex,
  deploymentsFor,
  destinationKey,
  flattenDeployments,
  normalizeBotTagReply,
  resolveAudience,
  resolveBotTagAudience,
  shouldSubmitMessage,
  splitDiscordMessage,
  type DeploymentIndex
} from "./routing.js";
import { preflightSmartParticipationRuntime } from "./smartParticipation.js";
import {
  buildMentionableParticipants,
  compileSmartMessage,
  reserveUniqueCharacterTurn,
  smartOutputResourceCandidate
} from "./smartOutput.js";
import type {
  DiscordActionParticipant,
  DiscordCatalogServer,
  DiscordContextMessage,
  DiscordContextTrace,
  DiscordDeployment,
  DiscordExpressionCandidate,
  DiscordExpressionContent,
  DiscordExpressionDecision,
  DiscordExpressionRetrieval,
  DiscordInteractionClaim,
  DiscordSmartOutput,
  DiscordSocialPendingTurn,
  DiscordSocialTurnCursor,
  DiscordSocialTurnStepReply,
  DiscordStickerContent
} from "./types.js";
import type { ConversationBurst } from "./turnCollector.js";
import {
  TurnIngressCoordinator,
  buildConversationBurstId,
  buildConversationBurstText,
  decideTurnCollection,
  summarizeConversationBurst
} from "./turnIngress.js";
import { DiscordWebhookManager } from "./webhookManager.js";

const config = loadConfig();
const relay = new RelayClient(
  config.relayApiUrl,
  config.relayConnectorToken,
  config.relayConnectionId
);
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
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log("Discord event batch upload failed.", {
      level: "error",
      connectionId: config.relayConnectionId,
      eventCount: events.length,
      eventTypes,
      guildIds,
      error: message
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
  GatewayIntentBits.GuildExpressions
];
if (config.messageContentIntent) intents.push(GatewayIntentBits.MessageContent);
const client = new Client({
  intents,
  partials: [Partials.Channel, Partials.Message]
});
interface CollectedDiscordTurn {
  source: Message<true>;
  originalText: string;
  authorDisplayName: string;
}

const context = new ContextBuffer(config.maxContextMessages);
const queues = new Map<string, Promise<void>>();
const processedMessages = new Map<string, number>();
const sentCharacterRoutes = new Map<
  string,
  { deploymentId: string; seenAt: number }
>();
const observedWebhookIds = new Set<string>();
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
const turnIngress = new TurnIngressCoordinator<CollectedDiscordTurn>(
  {
    enabled: config.smartParticipationTurnCollectorEnabled,
    quietWindowMs: config.smartParticipationTurnCollectorQuietMs,
    maxWaitMs: config.smartParticipationTurnCollectorMaxWaitMs,
    maxMessages: config.smartParticipationTurnCollectorMaxMessages,
    maxCharacters: config.smartParticipationTurnCollectorMaxCharacters
  },
  enqueue,
  (error, scopeKey) => {
    lastError = error instanceof Error ? error.message : String(error);
    log("Discord Turn Collector ingress failed.", { scopeKey, error: lastError });
  }
);

const catalogChannelTypes = new Set<ChannelType>([
  ChannelType.GuildText,
  ChannelType.GuildAnnouncement,
  ChannelType.GuildForum,
  ChannelType.GuildMedia
]);

function log(message: string, metadata?: Record<string, unknown>): void {
  console.log(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      message,
      ...(metadata ?? {})
    })
  );
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
  if (!trace) return;
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
    message:
      trace.rag_status === "completed"
        ? "RAG retrieval completed for this character turn."
        : trace.rag_status === "failed"
          ? "RAG retrieval failed; Character Runtime continued without knowledge context."
          : "RAG retrieval was skipped for this character turn.",
    ...common,
    details
  });
}

async function syncServerCatalog(): Promise<void> {
  const servers: DiscordCatalogServer[] = [];
  for (const guild of client.guilds.cache.values()) {
    const fetched = await guild.channels.fetch();
    const categories = new Map(
      [...fetched.values()]
        .filter(
          (channel): channel is NonNullable<typeof channel> =>
            channel !== null && channel.type === ChannelType.GuildCategory
        )
        .map((channel) => [channel.id, channel.name])
    );
    const channels = [...fetched.values()]
      .filter(
        (channel): channel is NonNullable<typeof channel> =>
          channel !== null &&
          catalogChannelTypes.has(channel.type) &&
          channel.viewable
      )
      .map((channel) => ({
        id: channel.id,
        name: channel.name,
        category_id: channel.parentId ?? "",
        category_name: channel.parentId ? (categories.get(channel.parentId) ?? "") : "",
        type:
          channel.type === ChannelType.GuildForum
            ? "forum"
            : channel.type === ChannelType.GuildMedia
              ? "media"
              : channel.type === ChannelType.GuildAnnouncement
                ? "announcement"
                : "text"
      }))
      .sort((left, right) =>
        `${left.category_name}/${left.name}`.localeCompare(
          `${right.category_name}/${right.name}`
        )
      );
    let emojis: DiscordCatalogServer["emojis"] = [];
    try {
      const fetchedEmojis = await guild.emojis.fetch();
      emojis = [...fetchedEmojis.values()]
        .map((emoji) => ({
          emoji_id: emoji.id,
          name: emoji.name || "emoji",
          animated: Boolean(emoji.animated),
          available: emoji.available !== false,
          asset_url: emoji.imageURL({ extension: emoji.animated ? "gif" : "png", size: 128 })
        }))
        .sort((left, right) => left.name.localeCompare(right.name));
    } catch (error) {
      log("Unable to synchronize Discord Guild Emojis.", {
        guildId: guild.id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
    let stickers: DiscordCatalogServer["stickers"] = [];
    try {
      const fetchedStickers = await guild.stickers.fetch();
      stickers = [...fetchedStickers.values()]
        .map((sticker) => ({
          sticker_id: sticker.id,
          name: sticker.name || "Sticker",
          description: sticker.description ?? "",
          tags: (sticker.tags ?? "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          format_type: String(sticker.format),
          asset_url: sticker.url
        }))
        .sort((left, right) => left.name.localeCompare(right.name));
    } catch (error) {
      log("Unable to synchronize Discord Guild Stickers.", {
        guildId: guild.id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
    servers.push({
      guild_id: guild.id,
      guild_name: guild.name,
      channels,
      emojis,
      stickers
    });
  }
  await relay.syncServerCatalog({ servers });
  lastCatalogSyncAt = new Date().toISOString();
  log("Discord server catalog synchronized.", {
    servers: servers.length,
    channels: servers.reduce((total, server) => total + server.channels.length, 0),
    emojis: servers.reduce((total, server) => total + server.emojis.length, 0),
    stickers: servers.reduce((total, server) => total + server.stickers.length, 0)
  });
}

async function prepareWebhookIdentity(
  deployment: DiscordDeployment,
  botUserId: string
): Promise<void> {
  if (
    deployment.identity_mode !== "webhook" ||
    deployment.channel_scope_mode === "all_except"
  ) {
    return;
  }
  try {
    await webhookManager.ensure(deployment, botUserId);
    if (deployment.webhook_id) observedWebhookIds.add(deployment.webhook_id);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
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
  const next = await relay.listDeployments();
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
    multiCharacterDestinations: [...deployments.values()].filter(
      (items) => items.length > 1
    ).length,
    webhookReady: next.filter(
      (item) => item.identity_mode === "webhook" && item.webhook_status === "active"
    ).length
  });
}

async function refreshConnectorState(): Promise<void> {
  await syncServerCatalog();
  await refreshDeployments();
}

async function sendHeartbeat(
  status: "connected" | "offline" | "error",
  error = ""
): Promise<void> {
  const user = client.user;
  if (!user) return;
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
    last_gateway_mentioned_bot: lastGatewayMentionedBot
  });
}

function channelLocation(message: Message<true>): {
  channelId: string;
  channelName: string;
  categoryId: string;
  threadId: string;
  threadName: string;
} {
  if (message.channel.isThread()) {
    return {
      channelId: message.channel.parentId ?? "",
      channelName:
        message.channel.parent?.name ??
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

function normalizedText(
  message: Message<true>,
  botUserId: string,
  managedBotRoleIds: string[]
): string {
  return stripCustomEmojiTokens(
    stripBotMentionTokens(message.content, botUserId, managedBotRoleIds)
  );
}

async function resolveMessageEmojis(
  message: Message<true>
): Promise<DiscordExpressionContent[]> {
  const resolved: DiscordExpressionContent[] = [];
  for (const emoji of parseCustomEmojiTokens(message.content)) {
    try {
      resolved.push(
        await relay.resolveExpression({
          guild_id: message.guildId,
          resource_type: "emoji",
          resource_id: emoji.resource_id,
          name: emoji.name,
          animated: emoji.animated,
          available: true,
          asset_url: `https://cdn.discordapp.com/emojis/${emoji.resource_id}.${
            emoji.animated ? "gif" : "png"
          }`
        })
      );
    } catch (error) {
      log("Unable to resolve Discord custom Emoji semantics.", {
        emojiId: emoji.resource_id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }
  return resolved;
}

async function resolveMessageStickers(
  message: Message<true>
): Promise<DiscordStickerContent[]> {
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
    } catch (error) {
      log("Unable to resolve Discord Sticker semantics.", {
        stickerId: sticker.id,
        error: error instanceof Error ? error.message : String(error)
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

async function resolveReplyTarget(
  message: Message<true>,
  candidates: DiscordDeployment[],
  botUserId: string,
  channelId: string,
  threadId: string
): Promise<ReplyTarget> {
  const referencedId = message.reference?.messageId;
  if (!referencedId) {
    return { deploymentId: null, characterMessage: false };
  }

  const cached = sentCharacterRoutes.get(referencedId);
  if (
    cached &&
    candidates.some((item) => item.deployment_id === cached.deploymentId)
  ) {
    return { deploymentId: cached.deploymentId, characterMessage: true };
  }

  try {
    const route = await relay.resolveMessageRoute(referencedId);
    if (
      route &&
      route.channel_id === channelId &&
      route.thread_id === threadId &&
      candidates.some((item) => item.deployment_id === route.deployment_id)
    ) {
      sentCharacterRoutes.set(referencedId, {
        deploymentId: route.deployment_id,
        seenAt: Date.now()
      });
      return { deploymentId: route.deployment_id, characterMessage: true };
    }

    const referenced = await message.fetchReference();
    const characterMessage =
      referenced.author.id === botUserId ||
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
  } catch (error) {
    log("Unable to resolve referenced Discord message.", {
      messageId: message.id,
      referencedId,
      error: error instanceof Error ? error.message : String(error)
    });
    return { deploymentId: null, characterMessage: false };
  }
}

function enqueue(destination: string, task: () => Promise<void>): void {
  const previous = queues.get(destination) ?? Promise.resolve();
  let next: Promise<void>;
  next = previous
    .catch(() => undefined)
    .then(task)
    .catch((error: unknown) => {
      lastError = error instanceof Error ? error.message : String(error);
      log("Discord message task failed.", { destination, error: lastError });
    })
    .finally(() => {
      if (queues.get(destination) === next) queues.delete(destination);
    });
  queues.set(destination, next);
}

async function sendSelectionHelp(
  source: Message<true>,
  options: string[]
): Promise<void> {
  const names = options.map((item) => `**${item}**`).join("、");
  const botName = client.user?.username ?? "CharacterRelayBot";
  await source.reply({
    content:
      `这个位置有多个角色：${names}。` +
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

async function sendBotFallback(
  source: Message<true>,
  characterName: string,
  replyText: string,
  options: CharacterDeliveryOptions
): Promise<string[]> {
  const safeName = characterName.replaceAll(/([\\*_`~|>])/g, "\\$1");
  const [firstChunk, ...remainingChunks] = splitDiscordMessage(
    `**${safeName}**\n${replyText}`
  );
  if (!firstChunk) return [];
  const messageIds: string[] = [];
  const allowedUserIds = options.allowedUserIds ?? [];
  const allowedMentions = {
    parse: [] as [],
    users: allowedUserIds,
    repliedUser: false
  };
  let first: Message<true>;
  if (options.replyToMessageId) {
    const target = await resolveSmartOutputTargetMessage(
      source,
      options.replyToMessageId
    );
    if (!target) {
      throw new Error("Smart Output reply target is unavailable.");
    }
    first = await target.reply({ content: firstChunk, allowedMentions });
  } else {
    const sent = await source.channel.send({ content: firstChunk, allowedMentions });
    if (!sent.inGuild()) throw new Error("Discord returned a non-guild message.");
    first = sent;
  }
  messageIds.push(first.id);
  for (const chunk of remainingChunks) {
    const sent = await source.channel.send({
      content: chunk,
      allowedMentions: { parse: [], users: allowedUserIds }
    });
    messageIds.push(sent.id);
  }
  return messageIds;
}

async function sendCharacterReply(
  source: Message<true>,
  deployment: DiscordDeployment,
  replyText: string,
  botUserId: string,
  options?: CharacterDeliveryOptions
): Promise<string[]> {
  const delivery = options ?? { replyToMessageId: source.id, allowedUserIds: [] };
  if (deployment.identity_mode === "webhook") {
    try {
      const ids = await webhookManager.send(
        deployment,
        splitDiscordMessage(replyText),
        botUserId,
        delivery.allowedUserIds ?? []
      );
      if (deployment.webhook_id) observedWebhookIds.add(deployment.webhook_id);
      return ids;
    } catch (error) {
      log("Falling back to the shared Bot identity.", {
        deploymentId: deployment.deployment_id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }
  return sendBotFallback(
    source,
    deployment.identity_display_name || deployment.character_display_name,
    replyText,
    delivery
  );
}

async function rememberSentMessages(
  deployment: DiscordDeployment,
  messageIds: string[],
  guildId: string
): Promise<void> {
  if (!messageIds.length) return;
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
        error: error instanceof Error ? error.message : String(error)
      });
    });
}

function resolveDeploymentLocation(
  deployment: DiscordDeployment,
  location: ReturnType<typeof channelLocation>
): DiscordDeployment {
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

interface PreparedExpression {
  retrieval: DiscordExpressionRetrieval | null;
  query: string;
}

interface ExpressionExecutionResult {
  sentMessageIds: string[];
  outgoingText: string;
  action: DiscordExpressionDecision["action"];
  resourceKey: string;
  applied: boolean;
  fallback: string;
}

async function prepareExpression(
  source: Message<true>,
  deployment: DiscordDeployment,
  text: string,
  stickers: DiscordStickerContent[],
  emojis: DiscordExpressionContent[],
  recentMessages: DiscordContextMessage[]
): Promise<PreparedExpression> {
  const query = expressionQuery({
    text,
    stickerMeanings: stickers.map((item) => item.semantic_description),
    emojiMeanings: emojis.map((item) => item.semantic_description),
    recentText: recentMessages.map((item) => item.text)
  });
  try {
    const retrieval = await relay.retrieveExpressions({
      guild_id: source.guildId,
      channel_id: deployment.channel_id,
      source_message_id: source.id,
      deployment_id: deployment.deployment_id,
      query,
      allowed_actions: ["inline", "reaction", "sticker"],
      excluded_resource_keys: [],
      top_k: 6
    });
    reportDiscordEvent({
      level: "info",
      eventType: "expression_candidates",
      message: "Server expressions were retrieved for an optional character expression.",
      guildId: source.guildId,
      guildName: source.guild.name,
      channelId: deployment.channel_id,
      channelName: deployment.channel_name,
      threadId: deployment.thread_id,
      threadName: deployment.thread_name,
      sourceMessageId: source.id,
      deploymentId: deployment.deployment_id,
      characterName: deploymentDisplayName(deployment),
      details: {
        run_id: retrieval.run_id,
        retrieval_backend: retrieval.retrieval_backend,
        candidate_count: retrieval.candidates.length,
        candidate_keys: retrieval.candidates.map((item) => item.resource_key)
      }
    });
    return { retrieval, query };
  } catch (error) {
    log("Expression retrieval failed; continuing without a custom expression.", {
      deploymentId: deployment.deployment_id,
      sourceMessageId: source.id,
      error: error instanceof Error ? error.message : String(error)
    });
    return { retrieval: null, query };
  }
}

async function reportExpressionNode(
  runId: string,
  payload: Parameters<RelayClient["reportExpressionNode"]>[1]
): Promise<void> {
  await relay.reportExpressionNode(runId, payload).catch((error: unknown) => {
    log("Unable to persist Expression workflow node.", {
      runId,
      nodeName: payload.node_name,
      error: error instanceof Error ? error.message : String(error)
    });
  });
}

async function resolveExpressionSourceMessage(
  fallback: Message<true>,
  messageId: string
): Promise<Message<true>> {
  if (!messageId || messageId === fallback.id) return fallback;
  try {
    const fetched = await fallback.channel.messages.fetch(messageId);
    return fetched.inGuild() ? fetched : fallback;
  } catch (error) {
    log("Unable to fetch the character message used as an Expression source.", {
      messageId,
      fallbackMessageId: fallback.id,
      error: error instanceof Error ? error.message : String(error)
    });
    return fallback;
  }
}

async function resolveSmartOutputTargetMessage(
  source: Message<true>,
  messageId: string
): Promise<Message<true> | null> {
  if (!messageId) return null;
  if (messageId === source.id) return source;
  try {
    const fetched = await source.channel.messages.fetch(messageId);
    return fetched.inGuild() ? fetched : null;
  } catch {
    return null;
  }
}

async function validateExpressionResource(
  source: Message<true>,
  candidate: DiscordExpressionCandidate
): Promise<boolean> {
  try {
    if (candidate.resource_type === "emoji") {
      const emoji = await source.guild.emojis.fetch(candidate.resource_id);
      return Boolean(emoji && emoji.available !== false);
    }
    const sticker = await source.guild.stickers.fetch(candidate.resource_id);
    return Boolean(sticker);
  } catch {
    return false;
  }
}

async function executeCharacterOutput(
  source: Message<true>,
  deployment: DiscordDeployment,
  visibleText: string,
  decision: DiscordExpressionDecision,
  prepared: PreparedExpression,
  botUserId: string
): Promise<ExpressionExecutionResult> {
  const retrieval = prepared.retrieval;
  if (!retrieval || decision.action === "none") {
    const sentMessageIds = visibleText
      ? await sendCharacterReply(source, deployment, visibleText, botUserId)
      : [];
    return {
      sentMessageIds,
      outgoingText: visibleText,
      action: "none",
      resourceKey: "",
      applied: false,
      fallback: "none"
    };
  }

  let candidates = retrieval.candidates;
  let candidate = expressionCandidate(candidates, decision.resource_key);
  const excluded = new Set<string>();
  if (candidate && !(await validateExpressionResource(source, candidate))) {
    excluded.add(candidate.resource_key);
    await reportExpressionNode(retrieval.run_id, {
      node_name: "validate_resource",
      status: "failed",
      input_summary: { resource_key: candidate.resource_key },
      output_summary: { available: false },
      error: "The selected Discord expression resource is no longer available."
    });
    try {
      const retried = await relay.retrieveExpressions({
        guild_id: source.guildId,
        channel_id: deployment.channel_id,
        source_message_id: source.id,
        deployment_id: deployment.deployment_id,
        query: prepared.query,
        allowed_actions: ["inline", "reaction", "sticker"],
        excluded_resource_keys: [...excluded],
        top_k: 6,
        run_id: retrieval.run_id
      });
      candidates = retried.candidates;
      candidate = fallbackExpressionCandidate(candidates, decision, excluded);
    } catch (error) {
      candidate = null;
      log("Expression re-retrieval failed.", {
        runId: retrieval.run_id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }

  if (!candidate) {
    const sentMessageIds = visibleText
      ? await sendCharacterReply(source, deployment, visibleText, botUserId)
      : [];
    await reportExpressionNode(retrieval.run_id, {
      node_name: "execute_delivery",
      status: "skipped",
      input_summary: { requested_action: decision.action },
      output_summary: { fallback: "text_only" },
      error: "",
      selected_action: "none",
      selected_resource_key: "",
      final_status: "skipped"
    });
    return {
      sentMessageIds,
      outgoingText: visibleText,
      action: "none",
      resourceKey: "",
      applied: false,
      fallback: "text_only"
    };
  }

  await reportExpressionNode(retrieval.run_id, {
    node_name: "validate_resource",
    status: "completed",
    input_summary: { resource_key: candidate.resource_key },
    output_summary: { available: true, allowed_actions: candidate.allowed_actions },
    error: "",
    selected_action: decision.action,
    selected_resource_key: candidate.resource_key
  });

  let sentMessageIds: string[] = [];
  let outgoingText = visibleText;
  let fallback = "none";
  try {
    if (decision.action === "inline" && candidate.resource_type === "emoji") {
      outgoingText = [visibleText, renderCustomEmoji(candidate)].filter(Boolean).join(" ");
      sentMessageIds = await sendCharacterReply(source, deployment, outgoingText, botUserId);
    } else if (decision.action === "reaction" && candidate.resource_type === "emoji") {
      try {
        await source.react(`${candidate.name}:${candidate.resource_id}`);
        if (visibleText) {
          sentMessageIds = await sendCharacterReply(source, deployment, visibleText, botUserId);
        }
      } catch {
        fallback = "reaction_to_inline";
        outgoingText = [visibleText, renderCustomEmoji(candidate)].filter(Boolean).join(" ");
        if (outgoingText) {
          sentMessageIds = await sendCharacterReply(source, deployment, outgoingText, botUserId);
        } else {
          throw new Error("Reaction failed and no visible text was available for inline fallback.");
        }
      }
    } else if (decision.action === "sticker" && candidate.resource_type === "sticker") {
      let webhookAssetError: unknown = null;
      const normalizedFormat = candidate.format_type.toLowerCase();
      const webhookRenderable = !["3", "lottie"].includes(normalizedFormat);
      if (
        deployment.identity_mode === "webhook" &&
        candidate.asset_url &&
        webhookRenderable
      ) {
        try {
          const extension = ["4", "gif"].includes(normalizedFormat) ? "gif" : "png";
          sentMessageIds = await webhookManager.sendAsset(
            deployment,
            visibleText,
            candidate.asset_url,
            `${candidate.name || "expression"}.${extension}`,
            botUserId
          );
          fallback = "webhook_attachment";
        } catch (error) {
          webhookAssetError = error;
          fallback = "webhook_attachment_to_native_sticker";
          log("Webhook Sticker-like attachment failed; trying native Bot Sticker.", {
            deploymentId: deployment.deployment_id,
            resourceKey: candidate.resource_key,
            error: error instanceof Error ? error.message : String(error)
          });
        }
      }
      if (!sentMessageIds.length) {
        try {
          const sent = await source.reply({
            ...(visibleText ? { content: visibleText } : {}),
            stickers: [candidate.resource_id],
            allowedMentions: { parse: [], repliedUser: false }
          });
          sentMessageIds = [sent.id];
          if (!fallback || fallback === "none") fallback = "native_bot_sticker";
        } catch (nativeStickerError) {
          fallback = "sticker_to_text";
          if (!visibleText) {
            throw webhookAssetError ?? nativeStickerError;
          }
          sentMessageIds = await sendCharacterReply(source, deployment, visibleText, botUserId);
        }
      }
    } else {
      fallback = "invalid_action_to_text";
      sentMessageIds = visibleText
        ? await sendCharacterReply(source, deployment, visibleText, botUserId)
        : [];
    }
  } catch (error) {
    await reportExpressionNode(retrieval.run_id, {
      node_name: "execute_delivery",
      status: "failed",
      input_summary: {
        action: decision.action,
        resource_key: candidate.resource_key
      },
      output_summary: { fallback },
      error: error instanceof Error ? error.message : String(error),
      selected_action: decision.action,
      selected_resource_key: candidate.resource_key,
      final_status: "failed"
    });
    throw error;
  }

  const expressionApplied = ![
    "invalid_action_to_text",
    "sticker_to_text"
  ].includes(fallback);
  await reportExpressionNode(retrieval.run_id, {
    node_name: "execute_delivery",
    status: "completed",
    input_summary: {
      action: decision.action,
      resource_key: candidate.resource_key
    },
    output_summary: {
      sent_message_ids: sentMessageIds,
      fallback,
      expression_applied: expressionApplied
    },
    error: "",
    selected_action: decision.action,
    selected_resource_key: candidate.resource_key,
    final_status: "completed"
  });
  return {
    sentMessageIds,
    outgoingText,
    action: decision.action,
    resourceKey: candidate.resource_key,
    applied: expressionApplied,
    fallback
  };
}

interface SmartOutputExecutionResult extends ExpressionExecutionResult {
  smartAction: DiscordSmartOutput["action"];
  mentionedDeploymentIds: string[];
}

function skippedSmartOutput(
  action: DiscordSmartOutput["action"],
  fallback: string
): SmartOutputExecutionResult {
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

async function executeSmartOutput(
  source: Message<true>,
  deployment: DiscordDeployment,
  output: DiscordSmartOutput,
  prepared: PreparedExpression,
  botUserId: string,
  candidates: DiscordDeployment[],
  mentionableParticipants: DiscordActionParticipant[]
): Promise<SmartOutputExecutionResult> {
  if (output.action === "ignore") {
    return skippedSmartOutput("ignore", "ignore");
  }

  const expressionCandidates = prepared.retrieval?.candidates ?? [];
  if (output.action === "message") {
    const compiled = compileSmartMessage(
      output,
      candidates,
      deployment,
      expressionCandidates,
      mentionableParticipants
    );
    if (!compiled.ok) {
      return skippedSmartOutput("message", compiled.error);
    }
    for (const resourceKey of compiled.customEmojiResourceKeys) {
      const candidate = expressionCandidate(expressionCandidates, resourceKey);
      if (!candidate || !(await validateExpressionResource(source, candidate))) {
        return skippedSmartOutput("message", "inline_emoji_unavailable");
      }
    }
    if (output.reply_to_message_id) {
      const target = await resolveSmartOutputTargetMessage(
        source,
        output.reply_to_message_id
      );
      if (!target) return skippedSmartOutput("message", "reply_target_unavailable");
    }
    const sentMessageIds = await sendCharacterReply(
      source,
      deployment,
      compiled.content,
      botUserId,
      {
        replyToMessageId: output.reply_to_message_id,
        allowedUserIds: compiled.allowedUserIds
      }
    );
    const resourceKey = compiled.customEmojiResourceKeys[0] ?? "";
    return {
      sentMessageIds,
      outgoingText: compiled.content,
      action: resourceKey ? "inline" : "none",
      resourceKey,
      applied: Boolean(resourceKey),
      fallback:
        deployment.identity_mode === "webhook" && output.reply_to_message_id
          ? "webhook_reply_to_direct"
          : "none",
      smartAction: "message",
      mentionedDeploymentIds: compiled.mentionedDeploymentIds
    };
  }

  const candidate = smartOutputResourceCandidate(output, expressionCandidates);
  if (!candidate || !(await validateExpressionResource(source, candidate))) {
    return skippedSmartOutput(output.action, "resource_unavailable");
  }

  if (output.action === "react") {
    const targetId = output.target_message_id;
    if (!targetId) return skippedSmartOutput("react", "reaction_target_missing");
    const target = await resolveSmartOutputTargetMessage(source, targetId);
    if (!target) return skippedSmartOutput("react", "reaction_target_unavailable");
    try {
      await target.react(`${candidate.name}:${candidate.resource_id}`);
    } catch {
      return skippedSmartOutput("react", "reaction_failed");
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
      sentMessageIds = await webhookManager.sendAsset(
        deployment,
        "",
        candidate.asset_url,
        `${candidate.name || "expression"}.${extension}`,
        botUserId
      );
      fallback = output.reply_to_message_id
        ? "webhook_reply_to_direct"
        : "webhook_attachment";
    } catch {
      fallback = "webhook_attachment_to_native_sticker";
    }
  }
  if (!sentMessageIds.length) {
    try {
      const options = {
        stickers: [candidate.resource_id],
        allowedMentions: { parse: [] as [], repliedUser: false }
      };
      const sent = replyTarget
        ? await replyTarget.reply(options)
        : await source.channel.send(options);
      sentMessageIds = [sent.id];
      if (fallback === "none") fallback = "native_bot_sticker";
    } catch {
      return skippedSmartOutput("sticker", "sticker_delivery_failed");
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

interface BotConversationBudget {
  remainingResponses: number;
}

interface BotConversationTurn {
  deployment: DiscordDeployment;
  text: string;
  sentMessageIds: string[];
}

async function continueBotTagConversation(
  sourceMessage: Message<true>,
  sourceDeployment: DiscordDeployment,
  sourceText: string,
  sourceMessageIds: string[],
  candidates: DiscordDeployment[],
  location: ReturnType<typeof channelLocation>,
  key: string,
  botUserId: string,
  depth: number,
  budget: BotConversationBudget,
  participantsSeen: Set<string>
): Promise<void> {
  if (
    !config.botTagConversationsEnabled ||
    depth >= config.botTagMaxDepth ||
    budget.remainingResponses <= 0
  ) {
    return;
  }

  const audience = resolveBotTagAudience(
    candidates,
    sourceText,
    sourceDeployment.deployment_id,
    config.groupAddressAliases
  );
  if (!audience.deployments.length) return;

  const eligible = audience.deployments.filter(
    (deployment) =>
      !participantsSeen.has(deployment.deployment_id) &&
      shouldSubmitMessage(
        deployment,
        {
          mentionedBot: true,
          repliedToBot: false,
          hasReadableText: Boolean(audience.text || sourceText)
        },
        config.smartParticipationEnabled
      )
  );
  if (!eligible.length) return;

  const sourceDisplayName = deploymentDisplayName(sourceDeployment);
  const sourceDiscordMessageId = sourceMessageIds[0] ?? sourceMessage.id;
  const nextTurns: BotConversationTurn[] = [];

  for (const [responseIndex, baseDeployment] of eligible.entries()) {
    if (budget.remainingResponses <= 0) break;
    if (!reserveUniqueCharacterTurn(participantsSeen, baseDeployment.deployment_id)) {
      continue;
    }
    budget.remainingResponses -= 1;
    const deployment = resolveDeploymentLocation(baseDeployment, location);
    const expressionSource = await resolveExpressionSourceMessage(
      sourceMessage,
      sourceDiscordMessageId
    );
    const recentMessages = context.get(key);
    const mentionableParticipants = buildMentionableParticipants(
      candidates,
      recentMessages,
      deployment
    );
    const preparedExpression = await prepareExpression(
      expressionSource,
      deployment,
      audience.text || sourceText,
      [],
      [],
      recentMessages
    );
    await sourceMessage.channel.sendTyping();
    const reply = await relay.processMessage({
      deployment_id: deployment.deployment_id,
      message_id: sourceDiscordMessageId,
      guild_id: sourceMessage.guildId,
      guild_name: sourceMessage.guild.name,
      channel_id: location.channelId,
      channel_name: location.channelName,
      category_id: location.categoryId,
      thread_id: location.threadId,
      thread_name: location.threadName,
      author_id: `character:${sourceDeployment.character_card_id}`,
      author_display_name: sourceDisplayName,
      text:
        audience.text ||
        `${sourceDisplayName} tagged this character without additional readable text.`,
      mentioned_bot: true,
      replied_to_bot: false,
      smart_candidate: false,
      author_is_bot: true,
      emojis: [],
      stickers: [],
      interaction_session_id: "",
      interaction_type: "",
      interaction_intensity: "",
      interaction_round: 0,
      interaction_total_rounds: 0,
      interaction_position: 0,
      interaction_participant_count: 0,
      interaction_target_user_id: "",
      interaction_target_display_name: "",
      expression_run_id: preparedExpression.retrieval?.run_id ?? "",
      expression_candidates: preparedExpression.retrieval?.candidates ?? [],
      available_characters: candidates
        .filter((item) => item.deployment_id !== deployment.deployment_id)
        .map(deploymentAddressAlias),
      mentionable_participants: mentionableParticipants,
      recent_messages: recentMessages
    });
    if (preparedExpression.retrieval) {
      await reportExpressionNode(preparedExpression.retrieval.run_id, {
        node_name: "model_select",
        status: "completed",
        input_summary: {
          candidate_count: preparedExpression.retrieval.candidates.length
        },
        output_summary: {
          action: reply.expression.action,
          resource_key: reply.expression.resource_key ?? "",
          reason: reply.expression.reason
        },
        error: "",
        selected_action: reply.expression.action,
        selected_resource_key: reply.expression.resource_key ?? ""
      });
    }
    if (
      reply.action === "silent" ||
      reply.smart_output?.action === "ignore" ||
      (!reply.smart_output && !reply.text && reply.expression.action === "none")
    ) {
      continue;
    }
    const execution = reply.smart_output
      ? await executeSmartOutput(
          expressionSource,
          deployment,
          reply.smart_output,
          preparedExpression,
          botUserId,
          candidates,
          mentionableParticipants
        )
      : await executeCharacterOutput(
          expressionSource,
          deployment,
          reply.text
            ? normalizeBotTagReply(
                candidates,
                reply.text,
                deployment.deployment_id,
                config.groupAddressAliases
              ).displayText.trim()
            : "",
          reply.expression,
          preparedExpression,
          botUserId
        );
    const sentMessageIds = execution.sentMessageIds;
    const outgoingText = execution.outgoingText;
    if (!outgoingText && !sentMessageIds.length && !execution.applied) continue;
    await rememberSentMessages(deployment, sentMessageIds, sourceMessage.guildId);
    context.push(key, {
      message_id: sentMessageIds[0] ?? `relay-bot-tag-${Date.now()}`,
      author_id: `character:${deployment.character_card_id}`,
      author_display_name: deploymentDisplayName(deployment),
      text: outgoingText,
      emojis: [],
      stickers: [],
      created_at: new Date().toISOString(),
      is_bot: true
    });
    if (outgoingText) {
      nextTurns.push({ deployment, text: outgoingText, sentMessageIds });
    }
    log("Character tag reply sent to Discord.", {
      deploymentId: deployment.deployment_id,
      characterId: deployment.character_card_id,
      sourceDeploymentId: sourceDeployment.deployment_id,
      tagDepth: depth + 1,
      responseIndex: responseIndex + 1,
      responseCount: eligible.length,
      remainingResponseBudget: budget.remainingResponses,
      guildId: sourceMessage.guildId,
      channelId: location.channelId,
      threadId: location.threadId || null,
      sourceMessageId: sourceDiscordMessageId,
      sentMessageIds,
      latencyMs: reply.latency_ms ?? null
    });
  }

  for (const turn of nextTurns) {
    await continueBotTagConversation(
      sourceMessage,
      turn.deployment,
      turn.text,
      turn.sentMessageIds,
      candidates,
      location,
      key,
      botUserId,
      depth + 1,
      budget,
      participantsSeen
    );
  }
}

async function processInteractionSession(
  sourceMessage: Message<true>,
  claim: DiscordInteractionClaim,
  candidates: DiscordDeployment[],
  location: ReturnType<typeof channelLocation>,
  key: string,
  botUserId: string,
  authorDisplayName: string,
  originalText: string,
  emojis: DiscordExpressionContent[],
  stickers: DiscordStickerContent[]
): Promise<boolean> {
  const session = claim.session;
  const runId = claim.run_id;
  if (!claim.claimed || !session || !runId) return false;

  const ordered = session.participant_deployment_ids.map((deploymentId) =>
    candidates.find((item) => item.deployment_id === deploymentId)
  );
  if (ordered.some((item) => !item)) {
    await relay.completeInteractionRun(runId, {
      status: "failed",
      reply_count: 0,
      stop_reason: "One or more Session participants are not active in this channel."
    });
    log("Interaction Session could not resolve all participants.", {
      sessionId: session.id,
      runId,
      participantDeploymentIds: session.participant_deployment_ids
    });
    return true;
  }

  let replyCount = 0;
  try {
    for (let round = 1; round <= session.rounds_per_trigger; round += 1) {
      for (const [participantIndex, baseDeployment] of ordered.entries()) {
        if (!baseDeployment) continue;
        const deployment = resolveDeploymentLocation(baseDeployment, location);
        const recentMessages = context.get(key);
        const mentionableParticipants = buildMentionableParticipants(
          candidates,
          recentMessages,
          deployment
        ).filter((participant) => participant.kind === "human");
        const preparedExpression = await prepareExpression(
          sourceMessage,
          deployment,
          originalText,
          stickers,
          emojis,
          recentMessages
        );
        await sourceMessage.channel.sendTyping();
        const reply = await relay.processMessage({
          deployment_id: deployment.deployment_id,
          message_id: sourceMessage.id,
          guild_id: sourceMessage.guildId,
          guild_name: sourceMessage.guild.name,
          channel_id: location.channelId,
          channel_name: location.channelName,
          category_id: location.categoryId,
          thread_id: location.threadId,
          thread_name: location.threadName,
          author_id: sourceMessage.author.id,
          author_display_name: authorDisplayName,
          text:
            originalText ||
            "The target member sent interpreted Discord expression content without text.",
          mentioned_bot: false,
          replied_to_bot: false,
          smart_candidate: false,
          author_is_bot: false,
          emojis,
          stickers,
          available_characters: [],
          mentionable_participants: mentionableParticipants,
          recent_messages: recentMessages,
          interaction_session_id: session.id,
          interaction_type: "roast",
          interaction_intensity: session.intensity,
          interaction_round: round,
          interaction_total_rounds: session.rounds_per_trigger,
          interaction_position: participantIndex + 1,
          interaction_participant_count: ordered.length,
          interaction_target_user_id: session.target_user_id,
          interaction_target_display_name:
            session.target_display_name || authorDisplayName,
          expression_run_id: preparedExpression.retrieval?.run_id ?? "",
          expression_candidates: preparedExpression.retrieval?.candidates ?? []
        });
        if (preparedExpression.retrieval) {
          await reportExpressionNode(preparedExpression.retrieval.run_id, {
            node_name: "model_select",
            status: "completed",
            input_summary: {
              candidate_count: preparedExpression.retrieval.candidates.length
            },
            output_summary: {
              action: reply.expression.action,
              resource_key: reply.expression.resource_key ?? "",
              reason: reply.expression.reason
            },
            error: "",
            selected_action: reply.expression.action,
            selected_resource_key: reply.expression.resource_key ?? ""
          });
        }
        if (
          reply.action === "silent" ||
          reply.smart_output?.action === "ignore" ||
          (!reply.smart_output && !reply.text && reply.expression.action === "none")
        ) {
          continue;
        }
        const execution = reply.smart_output
          ? await executeSmartOutput(
              sourceMessage,
              deployment,
              reply.smart_output,
              preparedExpression,
              botUserId,
              candidates,
              mentionableParticipants
            )
          : await executeCharacterOutput(
              sourceMessage,
              deployment,
              reply.text
                ? normalizeBotTagReply(
                    candidates,
                    reply.text,
                    deployment.deployment_id,
                    config.groupAddressAliases
                  ).audience.text.trim() || reply.text.trim()
                : "",
              reply.expression,
              preparedExpression,
              botUserId
            );
        const sentMessageIds = execution.sentMessageIds;
        const outgoingText = execution.outgoingText;
        if (!outgoingText && !sentMessageIds.length && !execution.applied) continue;
        await rememberSentMessages(deployment, sentMessageIds, sourceMessage.guildId);
        context.push(key, {
          message_id: sentMessageIds[0] ?? `relay-interaction-${Date.now()}`,
          author_id: `character:${deployment.character_card_id}`,
          author_display_name: deploymentDisplayName(deployment),
          text: outgoingText,
          emojis: [],
          stickers: [],
          created_at: new Date().toISOString(),
          is_bot: true
        });
        replyCount += 1;
        log("Interaction Session character reply sent to Discord.", {
          sessionId: session.id,
          runId,
          deploymentId: deployment.deployment_id,
          round,
          participantPosition: participantIndex + 1,
          replyCount,
          sourceMessageId: sourceMessage.id,
          sentMessageIds,
          latencyMs: reply.latency_ms ?? null
        });
      }
    }
    await relay.completeInteractionRun(runId, {
      status: "completed",
      reply_count: replyCount,
      stop_reason: replyCount ? "rounds_completed" : "no_character_replies"
    });
  } catch (error) {
    await relay
      .completeInteractionRun(runId, {
        status: "failed",
        reply_count: replyCount,
        stop_reason: error instanceof Error ? error.message : String(error)
      })
      .catch(() => undefined);
    throw error;
  }
  return true;
}

async function processMessage(
  message: Message,
  options?: { recovery?: boolean }
): Promise<void> {
  const botUser = client.user;
  if (!message.inGuild() || message.author.bot || !botUser) return;
  if (processedMessages.has(message.id) && !options?.recovery) return;
  processedMessages.set(message.id, Date.now());

  const guildMessage = message;
  const location = channelLocation(guildMessage);
  if (!location.channelId) return;
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
  const originalText = normalizedText(
    guildMessage,
    botUser.id,
    mentionDetection.managedBotRoleIds
  );
  lastGatewayMessageAt = new Date().toISOString();
  lastGatewayMessageId = guildMessage.id;
  lastGatewayMentionedBot = mentionedBot;
  const candidates = deploymentsFor(
    deployments,
    location.channelId,
    location.threadId,
    guildMessage.guildId,
    location.categoryId
  );
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
      has_readable_text: Boolean(
        originalText || parseCustomEmojiTokens(guildMessage.content).length
      ),
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
  const key = destinationKey(location.channelId, location.threadId);
  const authorDisplayName =
    guildMessage.member?.displayName ??
    guildMessage.author.globalName ??
    guildMessage.author.username;
  const collectedTurn: CollectedDiscordTurn = {
    source: guildMessage,
    originalText,
    authorDisplayName
  };
  const executeQueued = async (
    burst: ConversationBurst<CollectedDiscordTurn> | null,
    interactionClaimOverride: DiscordInteractionClaim | null
  ): Promise<void> => {
    const burstTelemetry = burst
      ? summarizeConversationBurst(
          burst,
          burst.items.map((item) => item.source.author.id)
        )
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
          message_id: item.source.id,
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
      message_id: guildMessage.id,
      author_id: guildMessage.author.id,
      author_display_name: authorDisplayName,
      text: originalText,
      emojis,
      stickers,
      created_at: guildMessage.createdAt.toISOString(),
      is_bot: false
    };
    context.push(key, contextMessage);

    const participationText = burst
      ? buildConversationBurstText(
          burst.items.map((item) => ({ text: item.originalText })),
          4_000
        )
      : originalText;
    const participationBurstId = burstTelemetry?.burstId ?? "";
    const participationBurstMessages = burst
      ? burst.items.map((item) => ({
          message_id: item.source.id,
          author_id: item.source.author.id,
          author_display_name: item.authorDisplayName,
          text: item.originalText,
          created_at: item.source.createdAt.toISOString(),
          reply_to_message_id: item.source.reference?.messageId ?? ""
        }))
      : [];

    let interactionClaim: DiscordInteractionClaim = interactionClaimOverride ?? {
      claimed: false,
      run_id: null,
      session: null
    };
    if (!interactionClaimOverride) {
      try {
        interactionClaim = await relay.claimInteraction({
          guild_id: guildMessage.guildId,
          channel_id: location.channelId,
          target_user_id: guildMessage.author.id,
          source_message_id: guildMessage.id
        });
      } catch (error) {
        log("Unable to check Interaction Sessions; continuing normal routing.", {
          guildId: guildMessage.guildId,
          channelId: location.channelId,
          sourceMessageId: guildMessage.id,
          error: error instanceof Error ? error.message : String(error)
        });
      }
    }
    if (
      await processInteractionSession(
        guildMessage,
        interactionClaim,
        candidates,
        location,
        key,
        botUser.id,
        authorDisplayName,
        originalText,
        emojis,
        stickers
      )
    ) {
      return;
    }

    const replyTarget = await resolveReplyTarget(
      guildMessage,
      candidates,
      botUser.id,
      location.channelId,
      location.threadId
    );
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

    const semanticScores: Record<string, number> = {};
    const smartRuntimeScopeKey = [
      config.relayConnectionId,
      guildMessage.guildId,
      location.channelId,
      location.threadId
    ].join(":");
    if (
      config.smartParticipationEnabled &&
      !replyTarget.deploymentId &&
      participationText.trim()
    ) {
      const semanticPreflight = preflightSmartParticipationRuntime(
        candidates,
        participationText,
        Date.now(),
        smartRuntimeScopeKey
      );
      const smartDeploymentIds = semanticPreflight.semanticCandidateDeploymentIds;
      if (!semanticPreflight.skipSemantic && smartDeploymentIds.length) {
        try {
          const semantic = await relay.scoreSmartParticipation({
            message: participationText,
            deployment_ids: smartDeploymentIds,
            guild_id: guildMessage.guildId,
            channel_id: location.channelId,
            thread_id: location.threadId,
            message_id: guildMessage.id,
            author_id: guildMessage.author.id,
            reply_to_message_id: guildMessage.reference?.messageId ?? "",
            burst_id: participationBurstId,
            burst_messages: participationBurstMessages
          });
          if (semantic.available) {
            for (const candidate of semantic.candidates) {
              if (candidate.profile_ready && Number.isFinite(candidate.semantic_relevance)) {
                semanticScores[candidate.deployment_id] = candidate.semantic_relevance;
              }
            }
          }
          reportDiscordEvent({
            level: semantic.available ? "info" : "warning",
            eventType: "smart_participation_semantic_scored",
            message: semantic.available
              ? "Semantic Character Card relevance was scored for Smart Participation."
              : "Semantic Smart Participation was unavailable; deterministic routing continued.",
            guildId: guildMessage.guildId,
            guildName: guildMessage.guild.name,
            channelId: location.channelId,
            channelName: location.channelName,
            threadId: location.threadId,
            threadName: location.threadName,
            sourceMessageId: guildMessage.id,
            details: {
              available: semantic.available,
              reason: semantic.reason,
              model: semantic.model || null,
              dimension: semantic.dimension || null,
              candidate_count: semantic.candidates.length,
              burst_id: burstTelemetry?.burstId ?? null,
              burst_message_count: burstTelemetry?.messageCount ?? 1,
              collapsed_message_count: burstTelemetry?.collapsedMessageCount ?? 0,
              turn_collector_flush_reason: burstTelemetry?.flushReason ?? null,
              semantic_preflight_reason: semanticPreflight.reason,
              scores: semantic.candidates.map((candidate) => ({
                deployment_id: candidate.deployment_id,
                semantic_relevance: candidate.semantic_relevance,
                profile_ready: candidate.profile_ready
              }))
            }
          });
        } catch (error) {
          reportDiscordEvent({
            level: "warning",
            eventType: "smart_participation_semantic_failed",
            message: "Semantic Smart Participation failed; deterministic routing continued.",
            guildId: guildMessage.guildId,
            guildName: guildMessage.guild.name,
            channelId: location.channelId,
            channelName: location.channelName,
            threadId: location.threadId,
            threadName: location.threadName,
            sourceMessageId: guildMessage.id,
            details: {
              error: error instanceof Error ? error.message : String(error),
              candidate_count: smartDeploymentIds.length,
              burst_id: burstTelemetry?.burstId ?? null,
              burst_message_count: burstTelemetry?.messageCount ?? 1,
              turn_collector_flush_reason: burstTelemetry?.flushReason ?? null
            }
          });
        }
      } else if (semanticPreflight.skipSemantic) {
        reportDiscordEvent({
          level: "info",
          eventType: "smart_participation_semantic_skipped",
          message: "Runtime state resolved Smart Participation before E5 was needed.",
          guildId: guildMessage.guildId,
          guildName: guildMessage.guild.name,
          channelId: location.channelId,
          channelName: location.channelName,
          threadId: location.threadId,
          threadName: location.threadName,
          sourceMessageId: guildMessage.id,
          details: {
            reason: semanticPreflight.reason,
            burst_id: burstTelemetry?.burstId ?? null,
            burst_message_count: burstTelemetry?.messageCount ?? 1,
            collapsed_message_count: burstTelemetry?.collapsedMessageCount ?? 0
          }
        });
      }
    }

    const audience = resolveAudience(
      candidates,
      participationText,
      replyTarget.deploymentId,
      config.groupAddressAliases,
      semanticScores,
      smartRuntimeScopeKey
    );
    if (!audience.deployments.length) {
      if (mentionedBot || replyTarget.characterMessage) {
        reportDiscordEvent({
          level: "warning",
          eventType:
            audience.reason === "ambiguous" ? "audience_ambiguous" : "audience_not_found",
          message:
            audience.reason === "ambiguous"
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
      if (
        audience.reason === "ambiguous" &&
        (mentionedBot || replyTarget.characterMessage)
      ) {
        await sendSelectionHelp(guildMessage, audience.options);
      }
      return;
    }

    const isReplyToCharacter = audience.reason === "selected_reply";
    const eligibleDeployments = audience.deployments.filter((deployment) =>
      shouldSubmitMessage(
        deployment,
        {
          mentionedBot,
          repliedToBot: isReplyToCharacter,
          hasReadableText: Boolean(
            audience.text || originalText || emojis.length || stickers.length
          )
        },
        config.smartParticipationEnabled
      )
    );
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
            participation_modes: audience.deployments.map(
              (deployment) => deployment.participation_mode
            )
          }
        });
      }
      return;
    }

    const addressedToMultiple = audience.deployments.length > 1;
    const socialTurnEnabled =
      eligibleDeployments[0]?.orchestration_mode === "social_turn";
    const botConversationBudget: BotConversationBudget = {
      remainingResponses: config.botTagMaxResponses
    };
    const socialInitialDeploymentIds = eligibleDeployments.map(
      (item) => item.deployment_id
    );
    const socialContinuationDeploymentIds = candidates
      .filter((item) =>
        shouldSubmitMessage(
          item,
          { mentionedBot: true, repliedToBot: false, hasReadableText: true },
          config.smartParticipationEnabled
        )
      )
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
    const socialSources = new Map<
      string,
      { text: string; sentMessageIds: string[] }
    >();
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
    if (socialTurnEnabled) {
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
        continuation_budget: config.botTagMaxResponses,
        max_depth: config.botTagMaxDepth
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
      if (claimed.status === "completed") return;
    }
    const legacyQueue = [...eligibleDeployments];
    let processedResponses = 0;
    while (
      (socialTurnEnabled && socialNextTurn) ||
      (!socialTurnEnabled && legacyQueue.length)
    ) {
      const pendingTurn: DiscordSocialPendingTurn = socialTurnEnabled
        ? (socialNextTurn as DiscordSocialPendingTurn)
        : {
            deployment_id: legacyQueue.shift()?.deployment_id ?? "",
            origin: "selected",
            depth: 0,
            source_deployment_id: ""
          };
      socialNextTurn = null;
      const baseDeployment = candidates.find(
        (item) => item.deployment_id === pendingTurn.deployment_id
      );
      if (!baseDeployment) {
        if (socialTurnEnabled) break;
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
          semantic_relevance: semanticScores[deployment.deployment_id] ?? null
        }
      });
      const recentMessages = context.get(key);
      const socialSource =
        socialTurnEnabled && pendingTurn.origin !== "selected"
          ? socialSources.get(pendingTurn.source_deployment_id)
          : undefined;
      const sourceDeployment = socialSource
        ? candidates.find(
            (item) => item.deployment_id === pendingTurn.source_deployment_id
          )
        : undefined;
      const sourceDiscordMessageId =
        socialSource?.sentMessageIds[0] ?? guildMessage.id;
      const expressionSource = socialSource
        ? await resolveExpressionSourceMessage(
            guildMessage,
            sourceDiscordMessageId
          )
        : guildMessage;
      const continuationAudience =
        socialSource && sourceDeployment
          ? resolveBotTagAudience(
              candidates,
              socialSource.text,
              sourceDeployment.deployment_id,
              config.groupAddressAliases
            )
          : null;
      const sourceDisplayName = sourceDeployment
        ? deploymentDisplayName(sourceDeployment)
        : authorDisplayName;
      const smartParticipationAudience =
        audience.reason === "selected_smart" ||
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
      const mentionableParticipants = buildMentionableParticipants(
        candidates,
        recentMessages,
        deployment
      );
      const preparedExpression = await prepareExpression(
        expressionSource,
        deployment,
        turnText,
        socialSource ? [] : stickers,
        socialSource ? [] : emojis,
        recentMessages
      );
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
          : guildMessage.author.id,
        author_display_name: sourceDisplayName,
        text: turnText,
        mentioned_bot: socialSource ? true : mentionedBot,
        replied_to_bot: socialSource ? false : isReplyToCharacter,
        smart_candidate: socialSource
          ? false
          : deployment.participation_mode === "smart" &&
            config.smartParticipationEnabled,
        author_is_bot: Boolean(sourceDeployment),
        emojis: socialSource ? [] : emojis,
        stickers: socialSource ? [] : stickers,
        interaction_session_id: "",
        interaction_type: "",
        interaction_intensity: "",
        interaction_round: 0,
        interaction_total_rounds: 0,
        interaction_position: 0,
        interaction_participant_count: 0,
        interaction_target_user_id: "",
        interaction_target_display_name: "",
        expression_run_id: preparedExpression.retrieval?.run_id ?? "",
        expression_candidates: preparedExpression.retrieval?.candidates ?? [],
        available_characters: candidates
          .filter((item) => item.deployment_id !== deployment.deployment_id)
          .map(deploymentAddressAlias),
        mentionable_participants: mentionableParticipants,
        recent_messages: recentMessages
      };
      let socialStep: DiscordSocialTurnStepReply | null = null;
      const reply = socialTurnEnabled
        ? (
            (socialStep = await relay.processSocialTurnStep({
              payload: inboundPayload,
              initial_deployment_ids: socialInitialDeploymentIds,
              available_deployment_ids: socialAvailableDeploymentIds,
              continuation_budget: config.botTagMaxResponses,
              max_depth: config.botTagMaxDepth,
              cursor: socialCursor,
              operation_id: durableOperationId
            })),
            socialStep.reply
          )
        : await relay.processMessage(inboundPayload);
      if (socialStep && !socialStep.delivery_required) {
        socialCursor = socialStep.cursor;
        socialNextTurn = socialStep.next_turn ?? null;
      }
      reportCharacterContext({
        trace: reply.context_trace,
        source: guildMessage,
        deployment
      });
      if (preparedExpression.retrieval) {
        await reportExpressionNode(preparedExpression.retrieval.run_id, {
          node_name: "model_select",
          status: "completed",
          input_summary: {
            candidate_count: preparedExpression.retrieval.candidates.length
          },
          output_summary: {
            action: reply.expression.action,
            resource_key: reply.expression.resource_key ?? "",
            reason: reply.expression.reason
          },
          error: "",
          selected_action: reply.expression.action,
          selected_resource_key: reply.expression.resource_key ?? ""
        });
      }
      if (
        reply.action === "silent" ||
        reply.smart_output?.action === "ignore" ||
        (!reply.smart_output && !reply.text && reply.expression.action === "none")
      ) {
        if (preparedExpression.retrieval) {
          await reportExpressionNode(preparedExpression.retrieval.run_id, {
            node_name: "execute_delivery",
            status: "skipped",
            input_summary: { action: "none" },
            output_summary: { reason: reply.reason },
            error: "",
            selected_action: "none",
            selected_resource_key: "",
            final_status: "skipped"
          });
        }
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
      try {
        if (
          socialTurnEnabled &&
          socialStep?.delivery_required &&
          socialStep.step_id &&
          socialClaimRequest
        ) {
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
            applyDurableOperation(
              await relay.claimSocialTurnOperation(socialClaimRequest)
            );
            continue;
          }
          deliveryClaimed = true;
        }
        execution = reply.smart_output
          ? await executeSmartOutput(
              guildMessage,
              deployment,
              reply.smart_output,
              preparedExpression,
              botUser.id,
              candidates,
              mentionableParticipants
            )
          : await executeCharacterOutput(
              guildMessage,
              deployment,
              reply.text
                ? normalizeBotTagReply(
                    candidates,
                    reply.text,
                    deployment.deployment_id,
                    config.groupAddressAliases
                  ).displayText.trim()
                : "",
              reply.expression,
              preparedExpression,
              botUser.id
            );
        if (
          deliveryClaimed &&
          socialStep?.step_id &&
          socialCursor
        ) {
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
      } catch (error) {
        if (deliveryClaimed && socialStep?.step_id) {
          await relay
            .markSocialTurnDeliveryUncertain({
              operation_id: durableOperationId,
              step_id: socialStep.step_id,
              claim_nonce: deliveryClaimNonce,
              error: error instanceof Error ? error.message : String(error)
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
          details: { error: error instanceof Error ? error.message : String(error) }
        });
        throw error;
      }
      const sentMessageIds = execution.sentMessageIds;
      const outgoingText = execution.outgoingText;
      await rememberSentMessages(
        deployment,
        sentMessageIds,
        guildMessage.guildId
      );
      if (outgoingText || sentMessageIds.length) {
        context.push(key, {
          message_id: sentMessageIds[0] ?? `relay-expression-${Date.now()}`,
          author_id: `character:${deployment.character_card_id}`,
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
          expression_run_id: preparedExpression.retrieval?.run_id ?? null,
          action: execution.action,
          resource_key: execution.resourceKey || null,
          fallback: execution.fallback
        }
      });
      reportDiscordEvent({
        level: "info",
        eventType: "delivery_success",
        message: "Character reply was delivered to Discord.",
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
      if (socialTurnEnabled) {
        if (!durableOperationId) {
          if (outgoingText || sentMessageIds.length) {
            socialSources.set(deployment.deployment_id, {
              text: outgoingText,
              sentMessageIds
            });
          } else if (socialCursor) {
            socialCursor.pending_turns = socialCursor.pending_turns.filter(
              (item) => item.source_deployment_id !== deployment.deployment_id
            );
            socialNextTurn = socialCursor.pending_turns[0] ?? null;
          }
        }
      } else {
        await continueBotTagConversation(
          guildMessage,
          deployment,
          outgoingText,
          sentMessageIds,
          candidates,
          location,
          key,
          botUser.id,
          0,
          botConversationBudget,
          new Set([deployment.deployment_id])
        );
      }
    }
  };

  const explicitAudience = resolveExplicitAudiencePreflight(
    candidates,
    originalText,
    null,
    config.groupAddressAliases
  );
  const customEmojiCount = parseCustomEmojiTokens(guildMessage.content).length;
  const smartCandidateCount = candidates.filter(
    (item) => item.participation_mode === "smart"
  ).length;
  const collectionDecision = decideTurnCollection({
    collectorEnabled: turnIngress.enabled,
    smartParticipationEnabled: config.smartParticipationEnabled,
    recovery: Boolean(options?.recovery),
    mentionedBot,
    hasReplyReference: Boolean(guildMessage.reference?.messageId),
    explicitAudience: Boolean(explicitAudience),
    hasReadableText: Boolean(originalText.trim()),
    customEmojiCount,
    stickerCount: guildMessage.stickers.size,
    attachmentCount: guildMessage.attachments.size,
    embedCount: guildMessage.embeds.length,
    hasUrl: /https?:\/\//iu.test(guildMessage.content),
    smartCandidateCount
  });
  let preclaimedInteraction: DiscordInteractionClaim | null = null;

  if (collectionDecision.collect) {
    turnCollectorCandidateMessageCount += 1;
    log("Smart Participation message entered the Turn Collector.", {
      guildId: guildMessage.guildId,
      channelId: location.channelId,
      threadId: location.threadId || null,
      sourceMessageId: guildMessage.id,
      pendingBurstScopes: turnIngress.pendingBurstScopeCount,
      quietWindowMs: config.smartParticipationTurnCollectorQuietMs
    });
  } else {
    turnCollectorBypassMessageCount += 1;
    turnCollectorBypassReasons[collectionDecision.reason] =
      (turnCollectorBypassReasons[collectionDecision.reason] ?? 0) + 1;
  }

  turnIngress.submit(key, {
    id: guildMessage.id,
    value: collectedTurn,
    characters: originalText.length,
    receivedAt: guildMessage.createdTimestamp,
    collect: collectionDecision.collect,
    ...(collectionDecision.collect
      ? { prepareCollection: async () => {
          try {
            const claim = await relay.claimInteraction({
              guild_id: guildMessage.guildId,
              channel_id: location.channelId,
              target_user_id: guildMessage.author.id,
              source_message_id: guildMessage.id
            });
            if (claim.claimed) {
              turnCollectorInteractionBypassCount += 1;
              preclaimedInteraction = claim;
              return false;
            }
            return true;
          } catch (error) {
            turnCollectorInteractionBypassCount += 1;
            log("Unable to preflight Interaction Sessions; bypassing Turn Collector.", {
              guildId: guildMessage.guildId,
              channelId: location.channelId,
              sourceMessageId: guildMessage.id,
              error: error instanceof Error ? error.message : String(error)
            });
            return false;
          }
        } }
      : {}),
    execute: async (burst) => {
      await executeQueued(burst, preclaimedInteraction);
    }
  });
}

async function resumePendingSocialTurns(): Promise<void> {
  const pending = await relay.listPendingSocialTurnOperations();
  for (const operation of pending) {
    try {
      const guild =
        client.guilds.cache.get(operation.guild_id) ??
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
      await processMessage(source, { recovery: true });
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
    } catch (error) {
      log("Unable to resume durable Social Turn.", {
        operationId: operation.operation_id,
        sourceMessageId: operation.source_message_id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }
}

const healthServer = createServer((request, response) => {
  if (request.url !== "/health") {
    response.writeHead(404, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ detail: "Not found" }));
    return;
  }
  const activeDeployments = flattenDeployments(deployments);
  const webhookDeployments = activeDeployments.filter(
    (item) => item.identity_mode === "webhook"
  );
  response.writeHead(ready ? 200 : 503, { "Content-Type": "application/json" });
  response.end(
    JSON.stringify({
      name: "Character Relay Discord Connector",
      status: ready ? (stateSynchronized ? "ready" : "degraded") : "starting",
      gateway_ready: ready,
      state_synchronized: stateSynchronized,
      railway_replica_region: process.env.RAILWAY_REPLICA_REGION ?? null,
      discord_user: client.user?.tag ?? null,
      connection_id: config.relayConnectionId,
      active_deployments: activeDeployments.length,
      server_wide_deployments: activeDeployments.filter(
        (item) => item.channel_scope_mode === "all_except"
      ).length,
      active_destinations: deployments.size,
      multi_character_destinations: [...deployments.values()].filter(
        (items) => items.length > 1
      ).length,
      cached_message_routes: sentCharacterRoutes.size,
      observed_webhooks: observedWebhookIds.size,
      webhook_deployments: webhookDeployments.length,
      webhook_ready: webhookDeployments.filter(
        (item) => item.webhook_status === "active"
      ).length,
      webhook_errors: webhookDeployments.filter(
        (item) => item.webhook_status === "error"
      ).length,
      message_content_intent: config.messageContentIntent,
      smart_participation_enabled: config.smartParticipationEnabled,
      smart_participation_max_participants: config.smartParticipationMaxParticipants,
      smart_participation_semantic_enabled: true,
      smart_participation_turn_collector_enabled: turnIngress.enabled,
      smart_participation_turn_collector_pending_scopes:
        turnIngress.pendingBurstScopeCount,
      smart_participation_ingress_pending_scopes:
        turnIngress.pendingPreflightScopeCount,
      smart_participation_turn_collector_candidate_messages:
        turnCollectorCandidateMessageCount,
      smart_participation_turn_collector_bypass_messages:
        turnCollectorBypassMessageCount,
      smart_participation_turn_collector_bypass_reasons:
        turnCollectorBypassReasons,
      smart_participation_turn_collector_interaction_bypasses:
        turnCollectorInteractionBypassCount,
      smart_participation_turn_collector_bursts: turnCollectorBurstCount,
      smart_participation_turn_collector_collected_messages:
        turnCollectorCollectedMessageCount,
      smart_participation_turn_collector_collapsed_messages:
        turnCollectorCollapsedMessageCount,
      smart_participation_turn_collector_last_burst_at: turnCollectorLastBurstAt,
      smart_participation_turn_collector_last_burst_id: turnCollectorLastBurstId,
      smart_participation_turn_collector_last_flush_reason:
        turnCollectorLastFlushReason,
      bot_tag_conversations_enabled: config.botTagConversationsEnabled,
      bot_tag_max_depth: config.botTagMaxDepth,
      bot_tag_max_responses: config.botTagMaxResponses,
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
    })
  );
});

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
      lastError = null;
      await sendHeartbeat("connected").catch((error: unknown) => {
        lastError = error instanceof Error ? error.message : String(error);
        log("Connector heartbeat failed after state synchronization.", {
          error: lastError
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
          lastError = error instanceof Error ? error.message : String(error);
          log("Durable Social Turn recovery scan failed.", { error: lastError });
        });
      }
    },
    failed: async (error: unknown) => {
      lastError = error instanceof Error ? error.message : String(error);
      log("Connector state synchronization failed; retry scheduled.", {
        error: lastError,
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
      lastError = reason instanceof Error ? reason.message : String(reason);
      log("Connector heartbeat failed.", { error: lastError });
    });
  }, config.heartbeatSeconds * 1000);
});

client.on(Events.MessageCreate, (message) => {
  void processMessage(message).catch((error: unknown) => {
    lastError = error instanceof Error ? error.message : String(error);
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
        details: { error: lastError }
      });
    }
    log("Discord message handler failed.", {
      messageId: message.id,
      error: lastError
    });
  });
});

client.on(Events.GuildCreate, () => {
  void syncServerCatalog().catch((error: unknown) => {
    lastError = error instanceof Error ? error.message : String(error);
    log("Server catalog refresh failed after guild create.", { error: lastError });
  });
});

client.on(Events.GuildDelete, () => {
  void syncServerCatalog().catch((error: unknown) => {
    lastError = error instanceof Error ? error.message : String(error);
    log("Server catalog refresh failed after guild delete.", { error: lastError });
  });
});

client.on(Events.Error, (error) => {
  lastError = error.message;
  log("Discord client error.", { error: error.message });
});

dedupeTimer = setInterval(() => {
  const cutoff = Date.now() - 60 * 60 * 1000;
  for (const [messageId, seenAt] of processedMessages) {
    if (seenAt < cutoff) processedMessages.delete(messageId);
  }
  for (const [messageId, route] of sentCharacterRoutes) {
    if (route.seenAt < cutoff) sentCharacterRoutes.delete(messageId);
  }
}, 10 * 60 * 1000);

async function shutdown(signal: string): Promise<void> {
  ready = false;
  stateSynchronized = false;
  recoveryLoop?.stop();
  client.removeAllListeners(Events.MessageCreate);
  await turnIngress.shutdown(true);
  await Promise.all([...queues.values()].map((task) => task.catch(() => undefined)));
  await eventReporter.stop();
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  if (dedupeTimer) clearInterval(dedupeTimer);
  await sendHeartbeat("offline", `Connector stopped by ${signal}.`).catch(
    () => undefined
  );
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
