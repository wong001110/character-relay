from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Connector shared types.
replace_once(
    "connectors/discord/src/types.ts",
    '''export interface DiscordCatalogSticker {''',
    '''export interface DiscordCatalogEmoji {
  emoji_id: string;
  name: string;
  animated: boolean;
  available: boolean;
  asset_url: string;
}

export interface DiscordCatalogSticker {''',
)
replace_once(
    "connectors/discord/src/types.ts",
    '''  channels: DiscordCatalogChannel[];
  stickers: DiscordCatalogSticker[];''',
    '''  channels: DiscordCatalogChannel[];
  emojis: DiscordCatalogEmoji[];
  stickers: DiscordCatalogSticker[];''',
)
replace_once(
    "connectors/discord/src/types.ts",
    '''export interface DiscordStickerObservation {''',
    '''export type DiscordExpressionAction = "none" | "inline" | "reaction" | "sticker";

export interface DiscordExpressionContent {
  resource_key: string;
  resource_type: "emoji" | "sticker";
  resource_id: string;
  name: string;
  animated: boolean;
  available: boolean;
  enabled: boolean;
  allowed_actions: Array<"inline" | "reaction" | "sticker">;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
  asset_url: string;
  format_type: string;
}

export interface DiscordExpressionCandidate extends DiscordExpressionContent {
  score: number;
  signals: Record<string, number>;
}

export interface DiscordExpressionDecision {
  action: DiscordExpressionAction;
  resource_key?: string | null;
  reason: string;
}

export interface DiscordExpressionResolveRequest {
  guild_id: string;
  resource_type: "emoji" | "sticker";
  resource_id: string;
  name: string;
  animated: boolean;
  available: boolean;
  asset_url: string;
}

export interface DiscordExpressionRetrieveRequest {
  guild_id: string;
  channel_id: string;
  source_message_id: string;
  deployment_id: string;
  query: string;
  allowed_actions: Array<"inline" | "reaction" | "sticker">;
  excluded_resource_keys: string[];
  top_k: number;
  run_id?: string | null;
}

export interface DiscordExpressionRetrieval {
  run_id: string;
  attempt: number;
  retrieval_backend: "hybrid_sparse_v1";
  candidates: DiscordExpressionCandidate[];
}

export interface DiscordExpressionNodeReport {
  node_name: string;
  status: "running" | "completed" | "failed" | "skipped";
  input_summary: Record<string, unknown>;
  output_summary: Record<string, unknown>;
  error: string;
  selected_action?: DiscordExpressionAction | null;
  selected_resource_key?: string | null;
  final_status?: "running" | "completed" | "failed" | "skipped" | null;
}

export interface DiscordStickerObservation {''',
)
replace_once(
    "connectors/discord/src/types.ts",
    '''  text: string;
  stickers: DiscordStickerContent[];''',
    '''  text: string;
  emojis: DiscordExpressionContent[];
  stickers: DiscordStickerContent[];''',
)
# Add incoming emoji field to inbound payload after text.
replace_once(
    "connectors/discord/src/types.ts",
    '''  text: string;
  mentioned_bot: boolean;''',
    '''  text: string;
  emojis: DiscordExpressionContent[];
  mentioned_bot: boolean;''',
)
replace_once(
    "connectors/discord/src/types.ts",
    '''  interaction_target_display_name: string;
}''',
    '''  interaction_target_display_name: string;
  expression_run_id: string;
  expression_candidates: DiscordExpressionCandidate[];
}''',
)
replace_once(
    "connectors/discord/src/types.ts",
    '''export interface DiscordReply {
  action: "silent" | "reply";''',
    '''export interface DiscordReply {
  action: "silent" | "reply" | "expression";''',
)
replace_once(
    "connectors/discord/src/types.ts",
    '''  output_tokens?: number | null;
}''',
    '''  output_tokens?: number | null;
  expression: DiscordExpressionDecision;
}''',
)

# Relay API client.
replace_once(
    "connectors/discord/src/relayClient.ts",
    '''  DiscordDeployment,
  DiscordInboundMessage,''',
    '''  DiscordDeployment,
  DiscordExpressionContent,
  DiscordExpressionNodeReport,
  DiscordExpressionResolveRequest,
  DiscordExpressionRetrieval,
  DiscordExpressionRetrieveRequest,
  DiscordInboundMessage,''',
)
replace_once(
    "connectors/discord/src/relayClient.ts",
    '''  async resolveSticker(
    payload: DiscordStickerObservation
  ): Promise<DiscordStickerContent> {''',
    '''  async resolveExpression(
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
  ): Promise<DiscordStickerContent> {''',
)

# Connector imports and catalog Emoji synchronization.
replace_once(
    "connectors/discord/src/index.ts",
    '''import { detectBotMention, stripBotMentionTokens } from "./mentionDetection.js";
import { DiscordEventReporter } from "./eventReporter.js";''',
    '''import { detectBotMention, stripBotMentionTokens } from "./mentionDetection.js";
import {
  expressionCandidate,
  expressionQuery,
  fallbackExpressionCandidate,
  parseCustomEmojiTokens,
  renderCustomEmoji,
  stripCustomEmojiTokens
} from "./expressionFlow.js";
import { DiscordEventReporter } from "./eventReporter.js";''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''  DiscordCatalogServer,
  DiscordContextMessage,
  DiscordDeployment,
  DiscordInteractionClaim,
  DiscordStickerContent''',
    '''  DiscordCatalogServer,
  DiscordContextMessage,
  DiscordDeployment,
  DiscordExpressionCandidate,
  DiscordExpressionContent,
  DiscordExpressionDecision,
  DiscordExpressionRetrieval,
  DiscordInteractionClaim,
  DiscordStickerContent''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    let stickers: DiscordCatalogServer["stickers"] = [];''',
    '''    let emojis: DiscordCatalogServer["emojis"] = [];
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
    let stickers: DiscordCatalogServer["stickers"] = [];''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      guild_name: guild.name,
      channels,
      stickers''',
    '''      guild_name: guild.name,
      channels,
      emojis,
      stickers''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    channels: servers.reduce((total, server) => total + server.channels.length, 0),
    stickers: servers.reduce((total, server) => total + server.stickers.length, 0)''',
    '''    channels: servers.reduce((total, server) => total + server.channels.length, 0),
    emojis: servers.reduce((total, server) => total + server.emojis.length, 0),
    stickers: servers.reduce((total, server) => total + server.stickers.length, 0)''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''  return stripBotMentionTokens(message.content, botUserId, managedBotRoleIds);''',
    '''  return stripCustomEmojiTokens(
    stripBotMentionTokens(message.content, botUserId, managedBotRoleIds)
  );''',
)

# Incoming custom Emoji exact-ID resolution.
replace_once(
    "connectors/discord/src/index.ts",
    '''async function resolveMessageStickers(
  message: Message<true>
): Promise<DiscordStickerContent[]> {''',
    '''async function resolveMessageEmojis(
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
): Promise<DiscordStickerContent[]> {''',
)

# Insert expression retrieval/execution helpers before bot conversation interfaces.
index_file = Path("connectors/discord/src/index.ts")
text = index_file.read_text(encoding="utf-8")
marker = '''interface BotConversationBudget {'''
helpers = r'''
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
      try {
        const sent = await source.reply({
          content: visibleText || undefined,
          stickers: [candidate.resource_id],
          allowedMentions: { parse: [], repliedUser: false }
        });
        sentMessageIds = [sent.id];
      } catch (error) {
        fallback = "sticker_to_text";
        if (!visibleText) throw error;
        sentMessageIds = await sendCharacterReply(source, deployment, visibleText, botUserId);
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
      expression_applied: fallback !== "invalid_action_to_text"
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
    applied: fallback !== "invalid_action_to_text",
    fallback
  };
}

'''
if "interface PreparedExpression" not in text:
    text = text.replace(marker, helpers + marker, 1)
    index_file.write_text(text, encoding="utf-8")

# Resolve incoming Emoji alongside Sticker and add both to context.
replace_once(
    "connectors/discord/src/index.ts",
    '''  enqueue(key, async () => {
    const stickers = await resolveMessageStickers(guildMessage);
    const contextMessage: DiscordContextMessage = {''',
    '''  enqueue(key, async () => {
    const [emojis, stickers] = await Promise.all([
      resolveMessageEmojis(guildMessage),
      resolveMessageStickers(guildMessage)
    ]);
    const contextMessage: DiscordContextMessage = {''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      text: originalText,
      stickers,''',
    '''      text: originalText,
      emojis,
      stickers,''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''          hasReadableText: Boolean(originalText),
          sticker_count: guildMessage.stickers.size''',
    '''          hasReadableText: Boolean(originalText || parseCustomEmojiTokens(guildMessage.content).length),
          custom_emoji_count: parseCustomEmojiTokens(guildMessage.content).length,
          sticker_count: guildMessage.stickers.size''',
)
# Context objects generated by characters do not contain incoming expressions.
text = index_file.read_text(encoding="utf-8")
text = text.replace('''      text: outgoingText,
      stickers: [],''', '''      text: outgoingText,
      emojis: [],
      stickers: [],''')
text = text.replace('''      text: outgoingText,
          stickers: [],''', '''      text: outgoingText,
          emojis: [],
          stickers: [],''')
index_file.write_text(text, encoding="utf-8")

# All existing Runtime payloads receive optional expression fields. Non-human chains stay disabled.
text = index_file.read_text(encoding="utf-8")
text = text.replace('''      author_is_bot: true,
      stickers: [],''', '''      author_is_bot: true,
      emojis: [],
      stickers: [],''')
text = text.replace('''          author_is_bot: false,
          stickers,''', '''          author_is_bot: false,
          emojis,
          stickers,''')
text = text.replace('''      interaction_target_display_name: "",
      available_characters:''', '''      interaction_target_display_name: "",
      expression_run_id: "",
      expression_candidates: [],
      available_characters:''')
text = text.replace('''          interaction_target_display_name:
            session.target_display_name || authorDisplayName
        });''', '''          interaction_target_display_name:
            session.target_display_name || authorDisplayName,
          expression_run_id: "",
          expression_candidates: []
        });''')
index_file.write_text(text, encoding="utf-8")

# Normal human-triggered path: retrieve Top-K, let model optionally select, then execute.
replace_once(
    "connectors/discord/src/index.ts",
    '''    const botConversationBudget: BotConversationBudget = {
      remainingResponses: config.botTagMaxResponses
    };
    for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {''',
    '''    const botConversationBudget: BotConversationBudget = {
      remainingResponses: config.botTagMaxResponses
    };
    let expressionBudget = 1;
    for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      await guildMessage.channel.sendTyping();
      const reply = await relay.processMessage({''',
    '''      const preparedExpression = expressionBudget > 0
        ? await prepareExpression(
            guildMessage,
            deployment,
            (addressedToMultiple ? originalText : audience.text) || originalText,
            stickers,
            emojis,
            context.get(key)
          )
        : { retrieval: null, query: "" };
      await guildMessage.channel.sendTyping();
      const reply = await relay.processMessage({''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''        author_is_bot: false,
        stickers,
        interaction_session_id: "",''',
    '''        author_is_bot: false,
        emojis,
        stickers,
        interaction_session_id: "",''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''        interaction_target_user_id: "",
        interaction_target_display_name: "",
        available_characters:''',
    '''        interaction_target_user_id: "",
        interaction_target_display_name: "",
        expression_run_id: preparedExpression.retrieval?.run_id ?? "",
        expression_candidates: preparedExpression.retrieval?.candidates ?? [],
        available_characters:''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      if (reply.action !== "reply" || !reply.text) {
        reportDiscordEvent({''',
    '''      if (preparedExpression.retrieval) {
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
      if (reply.action === "silent" || (!reply.text && reply.expression.action === "none")) {
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
        reportDiscordEvent({''',
)
# Replace normalized visible reply + direct delivery block with expression-aware execution.
old = '''      const normalizedReply = normalizeBotTagReply(
        candidates,
        reply.text,
        deployment.deployment_id,
        config.groupAddressAliases
      );
      const outgoingText = normalizedReply.displayText.trim();
      if (!outgoingText) {
        log("Suppressed an empty character reply after removing a self Tag.", {
          deploymentId: deployment.deployment_id,
          sourceMessageId: guildMessage.id
        });
        continue;
      }

      let sentMessageIds: string[];
      try {
        sentMessageIds = await sendCharacterReply(
          guildMessage,
          deployment,
          outgoingText,
          botUser.id
        );
      } catch (error) {'''
new = '''      const normalizedReply = reply.text
        ? normalizeBotTagReply(
            candidates,
            reply.text,
            deployment.deployment_id,
            config.groupAddressAliases
          )
        : { displayText: "" };
      const visibleText = normalizedReply.displayText.trim();
      let execution: ExpressionExecutionResult;
      try {
        execution = await executeCharacterOutput(
          guildMessage,
          deployment,
          visibleText,
          reply.expression,
          preparedExpression,
          botUser.id
        );
      } catch (error) {'''
replace_once("connectors/discord/src/index.ts", old, new)
replace_once(
    "connectors/discord/src/index.ts",
    '''      await rememberSentMessages(
        deployment,
        sentMessageIds,
        guildMessage.guildId
      );
      context.push(key, {
        message_id: sentMessageIds[0] ?? `relay-${Date.now()}`,
        author_id: `character:${deployment.character_card_id}`,
        author_display_name: deploymentDisplayName(deployment),
        text: outgoingText,
        emojis: [],
        stickers: [],
        created_at: new Date().toISOString(),
        is_bot: true
      });''',
    '''      const sentMessageIds = execution.sentMessageIds;
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
      if (execution.applied) expressionBudget -= 1;
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
      });''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''          sent_message_ids: sentMessageIds,
          latency_ms: reply.latency_ms ?? null,''',
    '''          sent_message_ids: sentMessageIds,
          expression_action: execution.action,
          expression_resource_key: execution.resourceKey || null,
          expression_fallback: execution.fallback,
          latency_ms: reply.latency_ms ?? null,''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      sticker_understanding_enabled: true,''',
    '''      sticker_understanding_enabled: true,
      expression_retrieval_enabled: true,
      expression_retrieval_backend: "hybrid_sparse_v1",
      expression_max_candidates: 6,
      expression_max_per_trigger: 1,''',
)
