from pathlib import Path

path = Path("scripts/apply_expression_connector.py")
text = path.read_text(encoding="utf-8")

old_gateway = '''replace_once(
    "connectors/discord/src/index.ts",
    \'\'\'          hasReadableText: Boolean(originalText),
          sticker_count: guildMessage.stickers.size\'\'\',
    \'\'\'          hasReadableText: Boolean(originalText || parseCustomEmojiTokens(guildMessage.content).length),
          custom_emoji_count: parseCustomEmojiTokens(guildMessage.content).length,
          sticker_count: guildMessage.stickers.size\'\'\',
)'''
new_gateway = '''replace_once(
    "connectors/discord/src/index.ts",
    \'\'\'  hasReadableText: Boolean(originalText),
  stickerCount: guildMessage.stickers.size,\'\'\',
    \'\'\'  hasReadableText: Boolean(originalText || parseCustomEmojiTokens(guildMessage.content).length),
  customEmojiCount: parseCustomEmojiTokens(guildMessage.content).length,
  stickerCount: guildMessage.stickers.size,\'\'\',
)'''
if old_gateway not in text:
    raise SystemExit("Gateway anchor repair target not found")
text = text.replace(old_gateway, new_gateway, 1)

old_context_call = '''replace_once(
    "connectors/discord/src/index.ts",
    \'\'\'      await rememberSentMessages(
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
      });\'\'\',
    \'\'\'      const sentMessageIds = execution.sentMessageIds;
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
      });\'\'\',
)'''
new_context_call = '''target = Path("connectors/discord/src/index.ts")
target_text = target.read_text(encoding="utf-8")
context_without_emojis = \'\'\'      await rememberSentMessages(
        deployment,
        sentMessageIds,
        guildMessage.guildId
      );
      context.push(key, {
        message_id: sentMessageIds[0] ?? `relay-${Date.now()}`,
        author_id: `character:${deployment.character_card_id}`,
        author_display_name: deploymentDisplayName(deployment),
        text: outgoingText,
        stickers: [],
        created_at: new Date().toISOString(),
        is_bot: true
      });\'\'\'
context_with_emojis = context_without_emojis.replace(
    "        text: outgoingText,\\n        stickers: [],",
    "        text: outgoingText,\\n        emojis: [],\\n        stickers: [],",
)
replacement_context = \'\'\'      const sentMessageIds = execution.sentMessageIds;
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
      });\'\'\'
context_anchor = context_with_emojis if context_with_emojis in target_text else context_without_emojis
if context_anchor not in target_text:
    raise SystemExit("Expression context replacement anchor not found")
target.write_text(target_text.replace(context_anchor, replacement_context, 1), encoding="utf-8")'''
if old_context_call not in text:
    raise SystemExit("Context anchor repair target not found")
text = text.replace(old_context_call, new_context_call, 1)

path.write_text(text, encoding="utf-8")
