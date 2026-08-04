import { createServer } from "node:http";

import {
  ChannelType,
  Client,
  Events,
  GatewayIntentBits,
  Partials,
  type Message
} from "discord.js";

import { loadConfig } from "./config.js";
import { ContextBuffer } from "./contextBuffer.js";
import { RelayClient } from "./relayClient.js";
import {
  buildDeploymentIndex,
  deploymentsFor,
  destinationKey,
  flattenDeployments,
  resolveAudience,
  resolveBotTagAudience,
  shouldSubmitMessage,
  splitDiscordMessage,
  type DeploymentIndex
} from "./routing.js";
import type {
  DiscordCatalogServer,
  DiscordContextMessage,
  DiscordDeployment
} from "./types.js";
import { DiscordWebhookManager } from "./webhookManager.js";

const config = loadConfig();
const relay = new RelayClient(
  config.relayApiUrl,
  config.relayConnectorToken,
  config.relayConnectionId
);
const webhookManager = new DiscordWebhookManager(config.discordBotToken, relay);
const intents = [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages];
if (config.messageContentIntent) intents.push(GatewayIntentBits.MessageContent);
const client = new Client({
  intents,
  partials: [Partials.Channel, Partials.Message]
});
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
let refreshTimer: NodeJS.Timeout | undefined;
let heartbeatTimer: NodeJS.Timeout | undefined;
let dedupeTimer: NodeJS.Timeout | undefined;

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
    servers.push({
      guild_id: guild.id,
      guild_name: guild.name,
      channels
    });
  }
  await relay.syncServerCatalog({ servers });
  lastCatalogSyncAt = new Date().toISOString();
  log("Discord server catalog synchronized.", {
    servers: servers.length,
    channels: servers.reduce((total, server) => total + server.channels.length, 0)
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
    last_error: error
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

function normalizedText(message: Message<true>, botUserId: string): string {
  return message.content
    .trim()
    .replaceAll(new RegExp(`<@!?${botUserId}>`, "g"), "")
    .trim();
}

function deploymentDisplayName(deployment: DiscordDeployment): string {
  return deployment.identity_display_name || deployment.character_display_name;
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

async function sendBotFallback(
  source: Message<true>,
  characterName: string,
  replyText: string
): Promise<string[]> {
  const safeName = characterName.replaceAll(/([\\*_`~|>])/g, "\\$1");
  const [firstChunk, ...remainingChunks] = splitDiscordMessage(
    `**${safeName}**\n${replyText}`
  );
  if (!firstChunk) return [];
  const messageIds: string[] = [];
  const first = await source.reply({
    content: firstChunk,
    allowedMentions: { parse: [], repliedUser: false }
  });
  messageIds.push(first.id);
  for (const chunk of remainingChunks) {
    const sent = await source.channel.send({
      content: chunk,
      allowedMentions: { parse: [] }
    });
    messageIds.push(sent.id);
  }
  return messageIds;
}

async function sendCharacterReply(
  source: Message<true>,
  deployment: DiscordDeployment,
  replyText: string,
  botUserId: string
): Promise<string[]> {
  if (deployment.identity_mode === "webhook") {
    try {
      const ids = await webhookManager.send(
        deployment,
        splitDiscordMessage(replyText),
        botUserId
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
    replyText
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
  budget: BotConversationBudget
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

  const eligible = audience.deployments.filter((deployment) =>
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
    budget.remainingResponses -= 1;
    const deployment = resolveDeploymentLocation(baseDeployment, location);
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
      available_characters: candidates
        .filter((item) => item.deployment_id !== deployment.deployment_id)
        .map(deploymentDisplayName),
      recent_messages: context.get(key)
    });
    if (reply.action !== "reply" || !reply.text) continue;

    const sentMessageIds = await sendCharacterReply(
      sourceMessage,
      deployment,
      reply.text,
      botUserId
    );
    await rememberSentMessages(deployment, sentMessageIds, sourceMessage.guildId);
    context.push(key, {
      message_id: sentMessageIds[0] ?? `relay-bot-tag-${Date.now()}`,
      author_id: `character:${deployment.character_card_id}`,
      author_display_name: deploymentDisplayName(deployment),
      text: reply.text,
      created_at: new Date().toISOString(),
      is_bot: true
    });
    nextTurns.push({ deployment, text: reply.text, sentMessageIds });
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
      budget
    );
  }
}

async function processMessage(message: Message): Promise<void> {
  const botUser = client.user;
  if (!message.inGuild() || message.author.bot || !botUser) return;
  if (processedMessages.has(message.id)) return;
  processedMessages.set(message.id, Date.now());

  const guildMessage = message;
  const location = channelLocation(guildMessage);
  if (!location.channelId) return;
  const candidates = deploymentsFor(
    deployments,
    location.channelId,
    location.threadId,
    guildMessage.guildId,
    location.categoryId
  );
  if (!candidates.length) return;

  const originalText = normalizedText(guildMessage, botUser.id);
  const mentionedBot = guildMessage.mentions.users.has(botUser.id);
  const key = destinationKey(location.channelId, location.threadId);
  const authorDisplayName =
    guildMessage.member?.displayName ??
    guildMessage.author.globalName ??
    guildMessage.author.username;
  const contextMessage: DiscordContextMessage = {
    message_id: guildMessage.id,
    author_id: guildMessage.author.id,
    author_display_name: authorDisplayName,
    text: originalText,
    created_at: guildMessage.createdAt.toISOString(),
    is_bot: false
  };

  enqueue(key, async () => {
    context.push(key, contextMessage);

    const replyTarget = await resolveReplyTarget(
      guildMessage,
      candidates,
      botUser.id,
      location.channelId,
      location.threadId
    );
    const audience = resolveAudience(
      candidates,
      originalText,
      replyTarget.deploymentId,
      config.groupAddressAliases
    );
    if (!audience.deployments.length) {
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
          hasReadableText: Boolean(audience.text || originalText)
        },
        config.smartParticipationEnabled
      )
    );
    if (!eligibleDeployments.length) return;

    const addressedToMultiple = audience.deployments.length > 1;
    const botConversationBudget: BotConversationBudget = {
      remainingResponses: config.botTagMaxResponses
    };
    for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {
      const deployment = resolveDeploymentLocation(baseDeployment, location);
      await guildMessage.channel.sendTyping();
      const reply = await relay.processMessage({
        deployment_id: deployment.deployment_id,
        message_id: guildMessage.id,
        guild_id: guildMessage.guildId,
        guild_name: guildMessage.guild.name,
        channel_id: location.channelId,
        channel_name: location.channelName,
        category_id: location.categoryId,
        thread_id: location.threadId,
        thread_name: location.threadName,
        author_id: guildMessage.author.id,
        author_display_name: authorDisplayName,
        text:
          (addressedToMultiple ? originalText : audience.text) ||
          "The user addressed the character without additional readable text.",
        mentioned_bot: mentionedBot,
        replied_to_bot: isReplyToCharacter,
        smart_candidate:
          deployment.participation_mode === "smart" &&
          config.smartParticipationEnabled,
        author_is_bot: false,
        available_characters: candidates
          .filter((item) => item.deployment_id !== deployment.deployment_id)
          .map(deploymentDisplayName),
        recent_messages: context.get(key)
      });
      if (reply.action !== "reply" || !reply.text) continue;

      const sentMessageIds = await sendCharacterReply(
        guildMessage,
        deployment,
        reply.text,
        botUser.id
      );
      await rememberSentMessages(
        deployment,
        sentMessageIds,
        guildMessage.guildId
      );
      context.push(key, {
        message_id: sentMessageIds[0] ?? `relay-${Date.now()}`,
        author_id: `character:${deployment.character_card_id}`,
        author_display_name: deploymentDisplayName(deployment),
        text: reply.text,
        created_at: new Date().toISOString(),
        is_bot: true
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
      await continueBotTagConversation(
        guildMessage,
        deployment,
        reply.text,
        sentMessageIds,
        candidates,
        location,
        key,
        botUser.id,
        0,
        botConversationBudget
      );
    }
  });
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
      status: ready ? "ready" : "starting",
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
      bot_tag_conversations_enabled: config.botTagConversationsEnabled,
      bot_tag_max_depth: config.botTagMaxDepth,
      bot_tag_max_responses: config.botTagMaxResponses,
      custom_group_address_aliases: config.groupAddressAliases.length,
      last_catalog_sync_at: lastCatalogSyncAt,
      last_deployment_sync_at: lastDeploymentSyncAt,
      last_error: lastError
    })
  );
});

client.once(Events.ClientReady, async (readyClient) => {
  try {
    await refreshConnectorState();
    await sendHeartbeat("connected");
    ready = true;
    lastError = null;
    log("Discord connector ready.", {
      discordUser: readyClient.user.tag,
      connectionId: config.relayConnectionId,
      activeDeployments: flattenDeployments(deployments).length,
      activeDestinations: deployments.size
    });
    refreshTimer = setInterval(() => {
      void refreshConnectorState().catch((error: unknown) => {
        lastError = error instanceof Error ? error.message : String(error);
        log("Connector state refresh failed.", { error: lastError });
      });
    }, config.deploymentRefreshSeconds * 1000);
    heartbeatTimer = setInterval(() => {
      void sendHeartbeat("connected").catch((error: unknown) => {
        lastError = error instanceof Error ? error.message : String(error);
        log("Connector heartbeat failed.", { error: lastError });
      });
    }, config.heartbeatSeconds * 1000);
  } catch (error) {
    lastError = error instanceof Error ? error.message : String(error);
    log("Discord connector failed during startup.", { error: lastError });
    await sendHeartbeat("error", lastError).catch(() => undefined);
  }
});

client.on(Events.MessageCreate, (message) => {
  void processMessage(message).catch((error: unknown) => {
    lastError = error instanceof Error ? error.message : String(error);
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
  if (refreshTimer) clearInterval(refreshTimer);
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
