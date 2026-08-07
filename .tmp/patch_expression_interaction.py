from pathlib import Path

path = Path("connectors/discord/src/index.ts")
text = path.read_text()

def one(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return value.replace(old, new, 1)

start = text.index("async function processInteractionSession(")
end = text.index("\n\nasync function processMessage(", start)
section = text[start:end]

section = one(
    section,
    '''        const deployment = resolveDeploymentLocation(baseDeployment, location);
        await sourceMessage.channel.sendTyping();''',
    '''        const deployment = resolveDeploymentLocation(baseDeployment, location);
        const preparedExpression = await prepareExpression(
          sourceMessage,
          deployment,
          originalText,
          stickers,
          emojis,
          context.get(key)
        );
        await sourceMessage.channel.sendTyping();''',
    "interaction prepare expression",
)
section = one(
    section,
    '''          expression_run_id: "",
          expression_candidates: []''',
    '''          expression_run_id: preparedExpression.retrieval?.run_id ?? "",
          expression_candidates: preparedExpression.retrieval?.candidates ?? []''',
    "interaction expression payload",
)
section = one(
    section,
    '''        if (reply.action !== "reply" || !reply.text) continue;
        const normalizedReply = normalizeBotTagReply(
          candidates,
          reply.text,
          deployment.deployment_id,
          config.groupAddressAliases
        );
        const outgoingText = (
          normalizedReply.audience.reason === "not_found"
            ? normalizedReply.displayText
            : normalizedReply.audience.text
        ).trim();
        if (!outgoingText) continue;
        const sentMessageIds = await sendCharacterReply(
          sourceMessage,
          deployment,
          outgoingText,
          botUserId
        );''',
    '''        if (preparedExpression.retrieval) {
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
        let visibleText = "";
        if (reply.text) {
          const normalizedReply = normalizeBotTagReply(
            candidates,
            reply.text,
            deployment.deployment_id,
            config.groupAddressAliases
          );
          visibleText = (
            normalizedReply.audience.reason === "not_found"
              ? normalizedReply.displayText
              : normalizedReply.audience.text
          ).trim();
        }
        const execution = await executeCharacterOutput(
          sourceMessage,
          deployment,
          visibleText,
          reply.expression,
          preparedExpression,
          botUserId
        );
        const sentMessageIds = execution.sentMessageIds;
        const outgoingText = execution.outgoingText;
        if (!outgoingText && !sentMessageIds.length && !execution.applied) continue;''',
    "interaction execute expression",
)

text = text[:start] + section + text[end:]
path.write_text(text)
