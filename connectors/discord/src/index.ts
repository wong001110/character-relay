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
  destinationKey,
  findDeployment,
  shouldSubmitMessage,
  splitDiscordMessage
} from "./routing.js";
import type { DiscordContextMessage, DiscordDeployment } from "./types.js";

const config = loadConfig();
const relay = new RelayClient(
  config.relayApiUrl,
  config.relayConnectorToken,
  config.relayConnectionId
);
const intents = [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages];
if (config.messageContentIntent) intents.push(GatewayIntentBits.MessageContent);
const client = new Client({
  intents,
  partials: [Partials.Channel, Partials.Message]
});
const context = new ContextBuffer(config.maxContextMessages);
const queues = new Map<string, Promise<void>>();
const processedMessages = new Map<string, number>();
let deployments = new Map<string, DiscordDeployment>();
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

async function refreshDeployments(): Promise<void> {
  const next = await relay.listDeployments();
  deployments = buildDeploymentIndex(next);
  lastDeploymentSyncAt = new Date().toISOString();
  log("Discord deployments refreshed.", { count: next.length });
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
      channelName: message.channel.parent?.name ?? message.channel.parentId ?? "unknown-channel",
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

async function repliedToBot(message: Message<true>, botUserId: string): Promise<boolean> {
  if (!message.reference?.messageId) return false;
  try {
    const referenced = await message.fetchReference();
    return referenced.author.id === botUserId;
  } catch (error) {
    log("Unable to resolve referenced Discord message.", {
      messageId: message.id,
      error: error instanceof Error ? error.message : String(error)
    });
    return false;
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

async function sendCharacterReply(
  source: Message<true>,
  characterName: string,
  replyText: string
): Promise<string | null> {
  const safeName = characterName.replaceAll(/([\\*_`~|>])/g, "\\$1");
  const [firstChunk, ...remainingChunks] = splitDiscordMessage(
    `**${safeName}**\n${replyText}`
  );
  if (!firstChunk) return null;
  const first = await source.reply({
    content: firstChunk,
    allowedMentions: { parse: [], repliedUser: false }
  });
  for (const chunk of remainingChunks) {
    await source.channel.send({
      content: chunk,
      allowedMentions: { parse: [] }
    });
  }
  return first.id;
}

async function processMessage(message: Message): Promise<void> {
  const botUser = client.user;
  if (!message.inGuild() || message.author.bot || !botUser) return;
  if (processedMessages.has(message.id)) return;
  processedMessages.set(message.id, Date.now());

  const location = channelLocation(message);
  if (!location.channelId) return;
  const deployment = findDeployment(
    deployments,
    location.channelId,
    location.threadId
  );
  if (!deployment) return;

  const text = normalizedText(message, botUser.id);
  const mentionedBot = message.mentions.users.has(botUser.id);
  const isReplyToBot = await repliedToBot(message, botUser.id);
  const shouldSubmit = shouldSubmitMessage(
    deployment,
    {
      mentionedBot,
      repliedToBot: isReplyToBot,
      hasReadableText: Boolean(text)
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
    text,
    created_at: message.createdAt.toISOString(),
    is_bot: false
  };
  context.push(key, contextMessage);
  if (!shouldSubmit) return;

  enqueue(key, async () => {
    await message.channel.sendTyping();
    const reply = await relay.processMessage({
      message_id: message.id,
      guild_id: message.guildId,
      guild_name: message.guild.name,
      channel_id: location.channelId,
      channel_name: location.channelName,
      thread_id: location.threadId,
      thread_name: location.threadName,
      author_id: message.author.id,
      author_display_name: authorDisplayName,
      text: text || "The user mentioned the character without readable text.",
      mentioned_bot: mentionedBot,
      replied_to_bot: isReplyToBot,
      smart_candidate:
        deployment.participation_mode === "smart" &&
        config.smartParticipationEnabled,
      recent_messages: context.get(key)
    });
    if (reply.action !== "reply" || !reply.text || !reply.character_display_name) {
      return;
    }
    const sentMessageId = await sendCharacterReply(
      message,
      reply.character_display_name,
      reply.text
    );
    context.push(key, {
      message_id: sentMessageId ?? `relay-${Date.now()}`,
      author_id: botUser.id,
      author_display_name: reply.character_display_name,
      text: reply.text,
      created_at: new Date().toISOString(),
      is_bot: true
    });
    log("Character reply sent to Discord.", {
      deploymentId: reply.deployment_id,
      guildId: message.guildId,
      channelId: location.channelId,
      threadId: location.threadId || null,
      sourceMessageId: message.id,
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
  response.writeHead(ready ? 200 : 503, { "Content-Type": "application/json" });
  response.end(
    JSON.stringify({
      name: "Character Relay Discord Connector",
      status: ready ? "ready" : "starting",
      discord_user: client.user?.tag ?? null,
      connection_id: config.relayConnectionId,
      active_deployments: deployments.size,
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
      activeDeployments: deployments.size
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
}, 10 * 60 * 1000);

async function shutdown(signal: string): Promise<void> {
  ready = false;
  if (refreshTimer) clearInterval(refreshTimer);
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  if (dedupeTimer) clearInterval(dedupeTimer);
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
