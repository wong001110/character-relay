from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"Expected one match in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        raise SystemExit(f"Function boundary missing in {path}: {start!r} -> {end!r}")
    target.write_text(text[:start_index] + replacement + text[end_index:], encoding="utf-8")


# Type contract shared with the Python connector API.
replace_once(
    "connectors/discord/src/types.ts",
    """export interface DiscordExpressionDecision {\n  action: DiscordExpressionAction;\n  resource_key?: string | null;\n  reason: string;\n}\n""",
    """export interface DiscordExpressionDecision {\n  action: DiscordExpressionAction;\n  resource_key?: string | null;\n  reason: string;\n}\n\nexport interface DiscordActionParticipant {\n  ref: string;\n  display_name: string;\n  kind: \"human\" | \"character\";\n}\n\nexport type DiscordSmartOutputPart =\n  | { text: string }\n  | { emoji: string }\n  | { mention: string };\n\nexport interface DiscordSmartOutput {\n  action: \"ignore\" | \"message\" | \"react\" | \"sticker\";\n  content: DiscordSmartOutputPart[];\n  reply_to_message_id: string | null;\n  target_message_id: string | null;\n  emoji_resource_key: string | null;\n  sticker_resource_key: string | null;\n}\n""",
)
replace_once(
    "connectors/discord/src/types.ts",
    """  stickers: DiscordStickerContent[];\n  available_characters: string[];\n  recent_messages: DiscordContextMessage[];\n""",
    """  stickers: DiscordStickerContent[];\n  available_characters: string[];\n  mentionable_participants: DiscordActionParticipant[];\n  recent_messages: DiscordContextMessage[];\n""",
)
replace_once(
    "connectors/discord/src/types.ts",
    """  output_tokens?: number | null;\n  expression: DiscordExpressionDecision;\n}\n""",
    """  output_tokens?: number | null;\n  expression: DiscordExpressionDecision;\n  smart_output?: DiscordSmartOutput | null;\n}\n""",
)

# Incoming webhooks can safely ping only explicitly allowlisted human IDs.
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """    filename: string,\n    botUserId: string\n  ): Promise<string[]> {\n""",
    """    filename: string,\n    botUserId: string,\n    allowedUserIds: string[] = []\n  ): Promise<string[]> {\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """        assetUrl,\n        filename\n      );\n""",
    """        assetUrl,\n        filename,\n        allowedUserIds\n      );\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """          assetUrl,\n          filename\n        );\n""",
    """          assetUrl,\n          filename,\n          allowedUserIds\n        );\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """    chunks: string[],\n    botUserId: string\n  ): Promise<string[]> {\n""",
    """    chunks: string[],\n    botUserId: string,\n    allowedUserIds: string[] = []\n  ): Promise<string[]> {\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    "return await this.sendWithBinding(deployment, chunks, botUserId);",
    "return await this.sendWithBinding(deployment, chunks, botUserId, allowedUserIds);",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """    chunks: string[],\n    botUserId: string\n  ): Promise<string[]> {\n    let binding = await this.ensure(deployment, botUserId);\n""",
    """    chunks: string[],\n    botUserId: string,\n    allowedUserIds: string[]\n  ): Promise<string[]> {\n    let binding = await this.ensure(deployment, botUserId);\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    "let response = await this.executeWebhook(binding, deployment, chunk);",
    "let response = await this.executeWebhook(binding, deployment, chunk, allowedUserIds);",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    "response = await this.executeWebhook(binding, deployment, chunk);",
    "response = await this.executeWebhook(binding, deployment, chunk, allowedUserIds);",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """    assetUrl: string,\n    filename: string\n  ): Promise<Response> {\n""",
    """    assetUrl: string,\n    filename: string,\n    allowedUserIds: string[]\n  ): Promise<Response> {\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """        allowed_mentions: { parse: [] },\n        attachments: [{ id: 0, filename }]\n""",
    """        allowed_mentions: allowedUserIds.length\n          ? { parse: [], users: allowedUserIds }\n          : { parse: [] },\n        attachments: [{ id: 0, filename }]\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """    deployment: DiscordDeployment,\n    content: string\n  ): Promise<Response> {\n""",
    """    deployment: DiscordDeployment,\n    content: string,\n    allowedUserIds: string[]\n  ): Promise<Response> {\n""",
)
replace_once(
    "connectors/discord/src/webhookManager.ts",
    """        allowed_mentions: { parse: [] }\n""",
    """        allowed_mentions: allowedUserIds.length\n          ? { parse: [], users: allowedUserIds }\n          : { parse: [] }\n""",
)

# Discord Connector integration.
replace_once(
    "connectors/discord/src/index.ts",
    """} from \"./routing.js\";\nimport type {\n""",
    """} from \"./routing.js\";\nimport {\n  buildMentionableParticipants,\n  compileSmartMessage,\n  smartOutputResourceCandidate\n} from \"./smartOutput.js\";\nimport type {\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """  DiscordCatalogServer,\n  DiscordContextMessage,\n""",
    """  DiscordActionParticipant,\n  DiscordCatalogServer,\n  DiscordContextMessage,\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """  DiscordInteractionClaim,\n  DiscordStickerContent\n""",
    """  DiscordInteractionClaim,\n  DiscordSmartOutput,\n  DiscordStickerContent\n""",
)

send_functions = '''interface CharacterDeliveryOptions {\n  replyToMessageId?: string | null;\n  allowedUserIds?: string[];\n}\n\nasync function sendBotFallback(\n  source: Message<true>,\n  characterName: string,\n  replyText: string,\n  options: CharacterDeliveryOptions\n): Promise<string[]> {\n  const safeName = characterName.replaceAll(/([\\\\*_`~|>])/g, "\\\\$1");\n  const [firstChunk, ...remainingChunks] = splitDiscordMessage(\n    `**${safeName}**\\n${replyText}`\n  );\n  if (!firstChunk) return [];\n  const messageIds: string[] = [];\n  const allowedUserIds = options.allowedUserIds ?? [];\n  const allowedMentions = {\n    parse: [] as [],\n    users: allowedUserIds,\n    repliedUser: false\n  };\n  let first: Message<true>;\n  if (options.replyToMessageId) {\n    const target = await resolveSmartOutputTargetMessage(\n      source,\n      options.replyToMessageId\n    );\n    if (!target) {\n      throw new Error("Smart Output reply target is unavailable.");\n    }\n    first = await target.reply({ content: firstChunk, allowedMentions });\n  } else {\n    const sent = await source.channel.send({ content: firstChunk, allowedMentions });\n    if (!sent.inGuild()) throw new Error("Discord returned a non-guild message.");\n    first = sent;\n  }\n  messageIds.push(first.id);\n  for (const chunk of remainingChunks) {\n    const sent = await source.channel.send({\n      content: chunk,\n      allowedMentions: { parse: [], users: allowedUserIds }\n    });\n    messageIds.push(sent.id);\n  }\n  return messageIds;\n}\n\nasync function sendCharacterReply(\n  source: Message<true>,\n  deployment: DiscordDeployment,\n  replyText: string,\n  botUserId: string,\n  options?: CharacterDeliveryOptions\n): Promise<string[]> {\n  const delivery = options ?? { replyToMessageId: source.id, allowedUserIds: [] };\n  if (deployment.identity_mode === "webhook") {\n    try {\n      const ids = await webhookManager.send(\n        deployment,\n        splitDiscordMessage(replyText),\n        botUserId,\n        delivery.allowedUserIds ?? []\n      );\n      if (deployment.webhook_id) observedWebhookIds.add(deployment.webhook_id);\n      return ids;\n    } catch (error) {\n      log("Falling back to the shared Bot identity.", {\n        deploymentId: deployment.deployment_id,\n        error: error instanceof Error ? error.message : String(error)\n      });\n    }\n  }\n  return sendBotFallback(\n    source,\n    deployment.identity_display_name || deployment.character_display_name,\n    replyText,\n    delivery\n  );\n}\n\n'''
replace_between(
    "connectors/discord/src/index.ts",
    "async function sendBotFallback(\n",
    "async function rememberSentMessages(\n",
    send_functions,
)

replace_once(
    "connectors/discord/src/index.ts",
    """async function validateExpressionResource(\n""",
    """async function resolveSmartOutputTargetMessage(\n  source: Message<true>,\n  messageId: string\n): Promise<Message<true> | null> {\n  if (!messageId) return null;\n  if (messageId === source.id) return source;\n  try {\n    const fetched = await source.channel.messages.fetch(messageId);\n    return fetched.inGuild() ? fetched : null;\n  } catch {\n    return null;\n  }\n}\n\nasync function validateExpressionResource(\n""",
)

smart_executor = '''interface SmartOutputExecutionResult extends ExpressionExecutionResult {\n  smartAction: DiscordSmartOutput["action"];\n  mentionedDeploymentIds: string[];\n}\n\nfunction skippedSmartOutput(\n  action: DiscordSmartOutput["action"],\n  fallback: string\n): SmartOutputExecutionResult {\n  return {\n    sentMessageIds: [],\n    outgoingText: "",\n    action: "none",\n    resourceKey: "",\n    applied: false,\n    fallback,\n    smartAction: action,\n    mentionedDeploymentIds: []\n  };\n}\n\nasync function executeSmartOutput(\n  source: Message<true>,\n  deployment: DiscordDeployment,\n  output: DiscordSmartOutput,\n  prepared: PreparedExpression,\n  botUserId: string,\n  candidates: DiscordDeployment[],\n  mentionableParticipants: DiscordActionParticipant[]\n): Promise<SmartOutputExecutionResult> {\n  if (output.action === "ignore") {\n    return skippedSmartOutput("ignore", "ignore");\n  }\n\n  const expressionCandidates = prepared.retrieval?.candidates ?? [];\n  if (output.action === "message") {\n    const compiled = compileSmartMessage(\n      output,\n      candidates,\n      deployment,\n      expressionCandidates,\n      mentionableParticipants\n    );\n    if (!compiled.ok) {\n      return skippedSmartOutput("message", compiled.error);\n    }\n    for (const resourceKey of compiled.customEmojiResourceKeys) {\n      const candidate = expressionCandidate(expressionCandidates, resourceKey);\n      if (!candidate || !(await validateExpressionResource(source, candidate))) {\n        return skippedSmartOutput("message", "inline_emoji_unavailable");\n      }\n    }\n    if (output.reply_to_message_id) {\n      const target = await resolveSmartOutputTargetMessage(\n        source,\n        output.reply_to_message_id\n      );\n      if (!target) return skippedSmartOutput("message", "reply_target_unavailable");\n    }\n    const sentMessageIds = await sendCharacterReply(\n      source,\n      deployment,\n      compiled.content,\n      botUserId,\n      {\n        replyToMessageId: output.reply_to_message_id,\n        allowedUserIds: compiled.allowedUserIds\n      }\n    );\n    const resourceKey = compiled.customEmojiResourceKeys[0] ?? "";\n    return {\n      sentMessageIds,\n      outgoingText: compiled.content,\n      action: resourceKey ? "inline" : "none",\n      resourceKey,\n      applied: Boolean(resourceKey),\n      fallback:\n        deployment.identity_mode === "webhook" && output.reply_to_message_id\n          ? "webhook_reply_to_direct"\n          : "none",\n      smartAction: "message",\n      mentionedDeploymentIds: compiled.mentionedDeploymentIds\n    };\n  }\n\n  const candidate = smartOutputResourceCandidate(output, expressionCandidates);\n  if (!candidate || !(await validateExpressionResource(source, candidate))) {\n    return skippedSmartOutput(output.action, "resource_unavailable");\n  }\n\n  if (output.action === "react") {\n    const targetId = output.target_message_id;\n    if (!targetId) return skippedSmartOutput("react", "reaction_target_missing");\n    const target = await resolveSmartOutputTargetMessage(source, targetId);\n    if (!target) return skippedSmartOutput("react", "reaction_target_unavailable");\n    try {\n      await target.react(`${candidate.name}:${candidate.resource_id}`);\n    } catch {\n      return skippedSmartOutput("react", "reaction_failed");\n    }\n    return {\n      sentMessageIds: [],\n      outgoingText: "",\n      action: "reaction",\n      resourceKey: candidate.resource_key,\n      applied: true,\n      fallback: "none",\n      smartAction: "react",\n      mentionedDeploymentIds: []\n    };\n  }\n\n  const replyTarget = output.reply_to_message_id\n    ? await resolveSmartOutputTargetMessage(source, output.reply_to_message_id)\n    : null;\n  if (output.reply_to_message_id && !replyTarget) {\n    return skippedSmartOutput("sticker", "reply_target_unavailable");\n  }\n  let sentMessageIds: string[] = [];\n  let fallback = "none";\n  const normalizedFormat = candidate.format_type.toLowerCase();\n  const webhookRenderable = !["3", "lottie"].includes(normalizedFormat);\n  if (deployment.identity_mode === "webhook" && candidate.asset_url && webhookRenderable) {\n    try {\n      const extension = ["4", "gif"].includes(normalizedFormat) ? "gif" : "png";\n      sentMessageIds = await webhookManager.sendAsset(\n        deployment,\n        "",\n        candidate.asset_url,\n        `${candidate.name || "expression"}.${extension}`,\n        botUserId\n      );\n      fallback = output.reply_to_message_id\n        ? "webhook_reply_to_direct"\n        : "webhook_attachment";\n    } catch {\n      fallback = "webhook_attachment_to_native_sticker";\n    }\n  }\n  if (!sentMessageIds.length) {\n    try {\n      const options = {\n        stickers: [candidate.resource_id],\n        allowedMentions: { parse: [] as [], repliedUser: false }\n      };\n      const sent = replyTarget\n        ? await replyTarget.reply(options)\n        : await source.channel.send(options);\n      sentMessageIds = [sent.id];\n      if (fallback === "none") fallback = "native_bot_sticker";\n    } catch {\n      return skippedSmartOutput("sticker", "sticker_delivery_failed");\n    }\n  }\n  return {\n    sentMessageIds,\n    outgoingText: "",\n    action: "sticker",\n    resourceKey: candidate.resource_key,\n    applied: true,\n    fallback,\n    smartAction: "sticker",\n    mentionedDeploymentIds: []\n  };\n}\n\n'''
replace_once(
    "connectors/discord/src/index.ts",
    "interface BotConversationBudget {\n",
    smart_executor + "interface BotConversationBudget {\n",
)

# Keep Bot-to-Bot chains bounded to unique characters within one human-trigger chain.
replace_once(
    "connectors/discord/src/index.ts",
    """  depth: number,\n  budget: BotConversationBudget\n): Promise<void> {\n""",
    """  depth: number,\n  budget: BotConversationBudget,\n  participantsSeen: Set<string>\n): Promise<void> {\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """  const eligible = audience.deployments.filter((deployment) =>\n    shouldSubmitMessage(\n      deployment,\n""",
    """  const eligible = audience.deployments.filter(\n    (deployment) =>\n      !participantsSeen.has(deployment.deployment_id) &&\n      shouldSubmitMessage(\n        deployment,\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """      },\n      config.smartParticipationEnabled\n    )\n  );\n""",
    """        },\n        config.smartParticipationEnabled\n      )\n  );\n""",
)

# Add the runtime-approved participant catalog to all three provider calls.
replace_once(
    "connectors/discord/src/index.ts",
    """    const preparedExpression = await prepareExpression(\n      expressionSource,\n      deployment,\n      audience.text || sourceText,\n      [],\n      [],\n      context.get(key)\n    );\n    await sourceMessage.channel.sendTyping();\n""",
    """    const recentMessages = context.get(key);\n    const mentionableParticipants = buildMentionableParticipants(\n      candidates,\n      recentMessages,\n      deployment\n    );\n    const preparedExpression = await prepareExpression(\n      expressionSource,\n      deployment,\n      audience.text || sourceText,\n      [],\n      [],\n      recentMessages\n    );\n    await sourceMessage.channel.sendTyping();\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """      available_characters: candidates\n        .filter((item) => item.deployment_id !== deployment.deployment_id)\n        .map(deploymentAddressAlias),\n      recent_messages: context.get(key)\n""",
    """      available_characters: candidates\n        .filter((item) => item.deployment_id !== deployment.deployment_id)\n        .map(deploymentAddressAlias),\n      mentionable_participants: mentionableParticipants,\n      recent_messages: recentMessages\n""",
)

# Bot-tag execution: prefer Smart Output, retain legacy response compatibility.
bot_old = '''    if (reply.action === "silent" || (!reply.text && reply.expression.action === "none")) {\n      continue;\n    }\n    const normalizedReply = reply.text\n      ? normalizeBotTagReply(\n          candidates,\n          reply.text,\n          deployment.deployment_id,\n          config.groupAddressAliases\n        )\n      : { displayText: "" };\n    const visibleText = normalizedReply.displayText.trim();\n    const execution = await executeCharacterOutput(\n      expressionSource,\n      deployment,\n      visibleText,\n      reply.expression,\n      preparedExpression,\n      botUserId\n    );\n'''
bot_new = '''    if (\n      reply.action === "silent" ||\n      reply.smart_output?.action === "ignore" ||\n      (!reply.smart_output && !reply.text && reply.expression.action === "none")\n    ) {\n      continue;\n    }\n    const execution = reply.smart_output\n      ? await executeSmartOutput(\n          expressionSource,\n          deployment,\n          reply.smart_output,\n          preparedExpression,\n          botUserId,\n          candidates,\n          mentionableParticipants\n        )\n      : await executeCharacterOutput(\n          expressionSource,\n          deployment,\n          reply.text\n            ? normalizeBotTagReply(\n                candidates,\n                reply.text,\n                deployment.deployment_id,\n                config.groupAddressAliases\n              ).displayText.trim()\n            : "",\n          reply.expression,\n          preparedExpression,\n          botUserId\n        );\n'''
replace_once("connectors/discord/src/index.ts", bot_old, bot_new)
replace_once(
    "connectors/discord/src/index.ts",
    """      depth + 1,\n      budget\n    );\n""",
    """      depth + 1,\n      budget,\n      new Set([...participantsSeen, turn.deployment.deployment_id])\n    );\n""",
)

# Interaction session participant catalog and execution.
replace_once(
    "connectors/discord/src/index.ts",
    """        const preparedExpression = await prepareExpression(\n          sourceMessage,\n          deployment,\n          originalText,\n          stickers,\n          emojis,\n          context.get(key)\n        );\n""",
    """        const recentMessages = context.get(key);\n        const mentionableParticipants = buildMentionableParticipants(\n          candidates,\n          recentMessages,\n          deployment\n        ).filter((participant) => participant.kind === \"human\");\n        const preparedExpression = await prepareExpression(\n          sourceMessage,\n          deployment,\n          originalText,\n          stickers,\n          emojis,\n          recentMessages\n        );\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """          available_characters: [],\n          recent_messages: context.get(key),\n""",
    """          available_characters: [],\n          mentionable_participants: mentionableParticipants,\n          recent_messages: recentMessages,\n""",
)
interaction_old = '''        if (reply.action === "silent" || (!reply.text && reply.expression.action === "none")) {\n          continue;\n        }\n        let visibleText = "";\n        if (reply.text) {\n          const normalizedReply = normalizeBotTagReply(\n            candidates,\n            reply.text,\n            deployment.deployment_id,\n            config.groupAddressAliases\n          );\n          visibleText = (\n            normalizedReply.audience.reason === "not_found"\n              ? normalizedReply.displayText\n              : normalizedReply.audience.text\n          ).trim();\n        }\n        const execution = await executeCharacterOutput(\n          sourceMessage,\n          deployment,\n          visibleText,\n          reply.expression,\n          preparedExpression,\n          botUserId\n        );\n'''
interaction_new = '''        if (\n          reply.action === "silent" ||\n          reply.smart_output?.action === "ignore" ||\n          (!reply.smart_output && !reply.text && reply.expression.action === "none")\n        ) {\n          continue;\n        }\n        const execution = reply.smart_output\n          ? await executeSmartOutput(\n              sourceMessage,\n              deployment,\n              reply.smart_output,\n              preparedExpression,\n              botUserId,\n              candidates,\n              mentionableParticipants\n            )\n          : await executeCharacterOutput(\n              sourceMessage,\n              deployment,\n              reply.text\n                ? normalizeBotTagReply(\n                    candidates,\n                    reply.text,\n                    deployment.deployment_id,\n                    config.groupAddressAliases\n                  ).audience.text.trim() || reply.text.trim()\n                : "",\n              reply.expression,\n              preparedExpression,\n              botUserId\n            );\n'''
replace_once("connectors/discord/src/index.ts", interaction_old, interaction_new)

# Normal human-trigger path.
replace_once(
    "connectors/discord/src/index.ts",
    """      const preparedExpression = await prepareExpression(\n        guildMessage,\n        deployment,\n        (addressedToMultiple ? originalText : audience.text) || originalText,\n        stickers,\n        emojis,\n        context.get(key)\n      );\n      await guildMessage.channel.sendTyping();\n""",
    """      const recentMessages = context.get(key);\n      const mentionableParticipants = buildMentionableParticipants(\n        candidates,\n        recentMessages,\n        deployment\n      );\n      const preparedExpression = await prepareExpression(\n        guildMessage,\n        deployment,\n        (addressedToMultiple ? originalText : audience.text) || originalText,\n        stickers,\n        emojis,\n        recentMessages\n      );\n      await guildMessage.channel.sendTyping();\n""",
)
# This is the second occurrence after the bot-tag replacement.
text = Path("connectors/discord/src/index.ts").read_text(encoding="utf-8")
needle = '''        available_characters: candidates\n          .filter((item) => item.deployment_id !== deployment.deployment_id)\n          .map(deploymentAddressAlias),\n        recent_messages: context.get(key)\n'''
if text.count(needle) != 1:
    raise SystemExit(f"Expected one normal available_characters block, found {text.count(needle)}")
text = text.replace(
    needle,
    '''        available_characters: candidates\n          .filter((item) => item.deployment_id !== deployment.deployment_id)\n          .map(deploymentAddressAlias),\n        mentionable_participants: mentionableParticipants,\n        recent_messages: recentMessages\n''',
    1,
)
Path("connectors/discord/src/index.ts").write_text(text, encoding="utf-8")

normal_old = '''      if (reply.action === "silent" || (!reply.text && reply.expression.action === "none")) {\n'''
normal_new = '''      if (\n        reply.action === "silent" ||\n        reply.smart_output?.action === "ignore" ||\n        (!reply.smart_output && !reply.text && reply.expression.action === "none")\n      ) {\n'''
# At this point only the normal-path legacy condition remains.
replace_once("connectors/discord/src/index.ts", normal_old, normal_new)
normal_exec_old = '''      const normalizedReply = reply.text\n        ? normalizeBotTagReply(\n            candidates,\n            reply.text,\n            deployment.deployment_id,\n            config.groupAddressAliases\n          )\n        : { displayText: "" };\n      const visibleText = normalizedReply.displayText.trim();\n      let execution: ExpressionExecutionResult;\n      try {\n        execution = await executeCharacterOutput(\n          guildMessage,\n          deployment,\n          visibleText,\n          reply.expression,\n          preparedExpression,\n          botUser.id\n        );\n'''
normal_exec_new = '''      let execution: ExpressionExecutionResult | SmartOutputExecutionResult;\n      try {\n        execution = reply.smart_output\n          ? await executeSmartOutput(\n              guildMessage,\n              deployment,\n              reply.smart_output,\n              preparedExpression,\n              botUser.id,\n              candidates,\n              mentionableParticipants\n            )\n          : await executeCharacterOutput(\n              guildMessage,\n              deployment,\n              reply.text\n                ? normalizeBotTagReply(\n                    candidates,\n                    reply.text,\n                    deployment.deployment_id,\n                    config.groupAddressAliases\n                  ).displayText.trim()\n                : "",\n              reply.expression,\n              preparedExpression,\n              botUser.id\n            );\n'''
replace_once("connectors/discord/src/index.ts", normal_exec_old, normal_exec_new)
replace_once(
    "connectors/discord/src/index.ts",
    """        0,\n        botConversationBudget\n      );\n""",
    """        0,\n        botConversationBudget,\n        new Set([deployment.deployment_id])\n      );\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """      expression_retrieval_backend: "hybrid_sparse_v1",\n      expression_max_candidates: 6,\n""",
    """      expression_retrieval_backend: "hybrid_sparse_v1",\n      smart_output_v1_enabled: true,\n      expression_max_candidates: 6,\n""",
)

print("Smart Output V1 connector migration applied.")
