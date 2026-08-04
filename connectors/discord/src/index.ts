import { createServer } from "node:http";

import {
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
  selectDeployment,
  shouldSubmitMessage,
  splitDiscordMessage,
  type DeploymentIndex
} from "./routing.js";
import type { DiscordContextMessage, DiscordDeployment } from "./types.js";
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
let deployments: DeploymentIndex = new Map();
let lastDeploymentSyncAt: string | null = null;
let lastError: string | null = null;
let ready = false;
let refreshTimer: NodeJS.Timeout | undefined;
let heartbeatTimer: NodeJS.Timeout | undefined;
let dedupeTimer: NodeJS.Timeout | undefined;

function log(message: string, metadata?: Record<string, unknown>): void {
  console.log(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      message,
      ...(metadata ?? {})
    })
  );
}

async function prepareWebhookIdentity(
  deployment: DiscordDeployment,
  botUserId: string
): Promise<void> {
  if (deployment.identity_mode !== "webhook") return;
  try {
    await webhookManager.ensure(deployment, botUserId);
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
    // Keep webhook provisioning sequential so two characters in one channel do not
    // race to create duplicate incoming webhooks during a cold start.
    for (const item of next) {
      await prepareWebhookIdentity(item, botUserId);
    }
  }
  deployments = buildDeploymentIndex(next);
  lastDeploymentSyncAt = new Date().toISOString();
  log("Discord deployments refreshed.", {
    count: next.length,
    destinations: deployments.size,
    multiCharacterDestinations: [...deployments.values()].filter(
      (items) => items.length > 1
    ).length,
    webhookReady: next.filter(
      (item) => item.identity_mode === "webhook" && item.webhook_status === "active"
    ).length
  });
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
      threadId: message.channel.id,
      threadName: message.channel.name
    };
  }
  return {
    channelId: message.channel.id,
    channelName: message.channel.name,
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

function knownWebhookIds(): Set<string> {
  return new Set(
    flattenDeployments(deployments)
      .map((item) => item.webhook_id)
      .filter((item): item is string => Boolean(item))
  );
}

interface ReplyTarget {
  deploymentId: string | null;
  characterMessage: boolean;
}

async function resolveReplyTarget(
  message: Message<true>,
  candidates: DiscordDeployment[],
  botUserId: string
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
    const referenced = await message.fetchReference();
    const characterMessage =
      referenced.author.id === botUserId ||
      (Boolean(referenced.webhookId) && knownWebhookIds().has(referenced.webhookId!));
    if (!characterMessage) {
      return { deploymentId: null, characterMessage: false };
    }

    const route = await relay.resolveMessageRoute(referencedId);
    if (
      route &&
      route.channel_id === candidates[0]?.channel_id &&
      route.thread_id === (candidates[0]?.thread_id ?? "") &&
      candidates.some((item) => item.deployment_id === route.deployment_id)
    ) {
      sentCharacterRoutes.set(referencedId, {
        deploymentId: route.deployment_id,
        seenAt: Date.now()
      });
      return { deploymentId: route.deployment_id, characterMessage: true };
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
  await source.reply({
    content:
      `这个位置有多个角色：${names}。` +
      `请使用 \`@${client.user?.username ?? "CharacterRelayBot"} 角色名 消息\`，` +
      "或直接回复目标角色发出的消息。",
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
      return await webhookManager.send(
        deployment,
        splitDiscordMessage(replyText),
        botUserId
      );
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

async function processMessage(message: Message): Promise<void> {
  const botUser = client.user;
  if (!message.inGuild() || message.author.bot || !botUser) return;
  if (processedMessages.has(message.id)) return;
  processedMessages.set(message.id, Date.now());

  const location = channelLocation(message);
  if (!location.channelId) return;
  const candidates = deploymentsFor(
    deployments,
    location.channelId,
    location.threadId
  );
  if (!candidates.length) return;

  const originalText = normalizedText(message, botUser.id);
  const mentionedBot = message.mentions.users.has(botUser.id);
  const replyTarget = await resolveReplyTarget(message, candidates, botUser.id);
  const selection = selectDeployment(
    candidates,
    originalText,
    replyTarget.deploymentId
  );
  if (!selection.deployment) {
    if (
      selection.reason === "ambiguous" &&
      (mentionedBot || replyTarget.characterMessage)
    ) {
      await sendSelectionHelp(message, selection.options);
    }
    return;
  }
  const deployment = selection.deployment;
  const isReplyToCharacter = selection.reason === "selected_reply";
  const shouldSubmit = shouldSubmitMessage(
    deployment,
    {
      mentionedBot,
      repliedToBot: isReplyToCharacter,
      hasReadableText: Boolean(selection.text)
    },
    config.smartParticipationEnabled
  );

  const key = destinationKey(location.channelId, location.threadId);
  const authorDisplayName =
    message.member?.displayName ??
    message.author.globalName ??
    message.author.username;
  const contextMessage: DiscordContextMessage = {
    message_id: message.id,
    author_id: message.author.id,
    author_display_name: authorDisplayName,
    text: originalText,
    created_at: message.createdAt.toISOString(),
    is_bot: false
  };
  context.push(key, contextMessage);
  if (!shouldSubmit) return;

  enqueue(key, async () => {
    await message.channel.sendTyping();
    const reply = await relay.processMessage({
      deployment_id: deployment.deployment_id,
      message_id: message.id,
      guild_id: message.guildId,
      guild_name: message.guild.name,
      channel_id: location.channelId,
      channel_name: location.channelName,
      thread_id: location.threadId,
      thread_name: location.threadName,
      author_id: message.author.id,
      author_display_name: authorDisplayName,
      text:
        selection.text ||
        "The user addressed the character without additional readable text.",
      mentioned_bot: mentionedBot,
      replied_to_bot: isReplyToCharacter,
      smart_candidate:
        deployment.participation_mode === "smart" &&
        config.smartParticipationEnabled,
      recent_messages: context.get(key)
    });
    if (reply.action !== "reply" || !reply.text) return;

    const sentMessageIds = await sendCharacterReply(
      message,
      deployment,
      reply.text,
      botUser.id
    );
    await rememberSentMessages(deployment, sentMessageIds, message.guildId);
    context.push(key, {
      message_id: sentMessageIds[0] ?? `relay-${Date.now()}`,
      author_id: botUser.id,
      author_display_name:
        deployment.identity_display_name || deployment.character_display_name,
      text: reply.text,
      created_at: new Date().toISOString(),
      is_bot: true
    });
    log("Character reply sent to Discord.", {
      deploymentId: reply.deployment_id,
      characterId: deployment.character_card_id,
      selectionReason: selection.reason,
      identityMode: deployment.identity_mode,
      webhookStatus: deployment.webhook_status,
      guildId: message.guildId,
      channelId: location.channelId,
      threadId: location.threadId || null,
      sourceMessageId: message.id,
      sentMessageIds,
      latencyMs: reply.latency_ms ?? null
    });
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
      active_destinations: deployments.size,
      multi_character_destinations: [...deployments.values()].filter(
        (items) => items.length > 1
      ).length,
      cached_message_routes: sentCharacterRoutes.size,
      webhook_deployments: webhookDeployments.length,
      webhook_ready: webhookDeployments.filter(
        (item) => item.webhook_status === "active"
      ).length,
      webhook_errors: webhookDeployments.filter(
        (item) => item.webhook_status === "error"
      ).length,
      message_content_intent: config.messageContentIntent,
      smart_participation_enabled: config.smartParticipationEnabled,
      last_deployment_sync_at: lastDeploymentSyncAt,
      last_error: lastError
    })
  );
});

client.once(Events.ClientReady, async (readyClient) => {
  try {
    await refreshDeployments();
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
      void refreshDeployments().catch((error: unknown) => {
        lastError = error instanceof Error ? error.message : String(error);
        log("Deployment refresh failed.", { error: lastError });
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
