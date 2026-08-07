from pathlib import Path

path = Path("connectors/discord/src/index.ts")
text = path.read_text()

def one(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return value.replace(old, new, 1)

text = one(
    text,
    '''async function validateExpressionResource(
  source: Message<true>,
  candidate: DiscordExpressionCandidate
): Promise<boolean> {''',
    '''async function resolveExpressionSourceMessage(
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

async function validateExpressionResource(
  source: Message<true>,
  candidate: DiscordExpressionCandidate
): Promise<boolean> {''',
    "expression source helper",
)

start = text.index("async function continueBotTagConversation(")
end = text.index("\n\nasync function processInteractionSession(", start)
bot = text[start:end]
bot = one(
    bot,
    '''    const deployment = resolveDeploymentLocation(baseDeployment, location);
    await sourceMessage.channel.sendTyping();''',
    '''    const deployment = resolveDeploymentLocation(baseDeployment, location);
    const expressionSource = await resolveExpressionSourceMessage(
      sourceMessage,
      sourceDiscordMessageId
    );
    const preparedExpression = await prepareExpression(
      expressionSource,
      deployment,
      audience.text || sourceText,
      [],
      [],
      context.get(key)
    );
    await sourceMessage.channel.sendTyping();''',
    "bot prepare expression",
)
bot = one(
    bot,
    '''      expression_run_id: "",
      expression_candidates: [],''',
    '''      expression_run_id: preparedExpression.retrieval?.run_id ?? "",
      expression_candidates: preparedExpression.retrieval?.candidates ?? [],''',
    "bot expression payload",
)
bot = one(
    bot,
    '''    if (reply.action !== "reply" || !reply.text) continue;
    const normalizedReply = normalizeBotTagReply(
      candidates,
      reply.text,
      deployment.deployment_id,
      config.groupAddressAliases
    );
    const outgoingText = normalizedReply.displayText.trim();
    if (!outgoingText) {
      log("Suppressed an empty character reply after removing a self Tag.", {
        deploymentId: deployment.deployment_id,
        sourceDeploymentId: sourceDeployment.deployment_id
      });
      continue;
    }

    const sentMessageIds = await sendCharacterReply(
      sourceMessage,
      deployment,
      outgoingText,
      botUserId
    );''',
    '''    if (preparedExpression.retrieval) {
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
      continue;
    }
    const normalizedReply = reply.text
      ? normalizeBotTagReply(
          candidates,
          reply.text,
          deployment.deployment_id,
          config.groupAddressAliases
        )
      : { displayText: "" };
    const visibleText = normalizedReply.displayText.trim();
    const execution = await executeCharacterOutput(
      expressionSource,
      deployment,
      visibleText,
      reply.expression,
      preparedExpression,
      botUserId
    );
    const sentMessageIds = execution.sentMessageIds;
    const outgoingText = execution.outgoingText;
    if (!outgoingText && !sentMessageIds.length && !execution.applied) continue;''',
    "bot execute expression",
)
bot = one(
    bot,
    '''    nextTurns.push({ deployment, text: outgoingText, sentMessageIds });''',
    '''    if (outgoingText) {
      nextTurns.push({ deployment, text: outgoingText, sentMessageIds });
    }''',
    "bot recursion guard",
)
text = text[:start] + bot + text[end:]

text = one(
    text,
    '''    let expressionBudget = 1;
    for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {''',
    '''    for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {''',
    "shared expression budget",
)
text = one(
    text,
    '''      const preparedExpression = expressionBudget > 0
        ? await prepareExpression(
            guildMessage,
            deployment,
            (addressedToMultiple ? originalText : audience.text) || originalText,
            stickers,
            emojis,
            context.get(key)
          )
        : { retrieval: null, query: "" };''',
    '''      const preparedExpression = await prepareExpression(
        guildMessage,
        deployment,
        (addressedToMultiple ? originalText : audience.text) || originalText,
        stickers,
        emojis,
        context.get(key)
      );''',
    "ordinary expression preparation",
)
text = one(
    text,
    '''      if (execution.applied) expressionBudget -= 1;
      reportDiscordEvent({''',
    '''      reportDiscordEvent({''',
    "expression budget decrement",
)
text = one(
    text,
    '''      expression_max_candidates: 6,
      expression_max_per_trigger: 1,''',
    '''      expression_max_candidates: 6,
      expression_max_per_character_reply: 1,''',
    "health limit",
)

path.write_text(text)
