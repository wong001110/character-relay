export type BotMentionSource =
  | "structured_user"
  | "raw_user_token"
  | "managed_bot_role"
  | "none";

export interface BotMentionDetectionInput {
  content: string;
  botUserId: string;
  structuredUserMention: boolean;
  mentionedUserIds: string[];
  mentionedRoleIds: string[];
  managedBotRoleIds: string[];
}

export interface BotMentionDetection {
  mentionedBot: boolean;
  source: BotMentionSource;
  structuredUserMention: boolean;
  rawUserMention: boolean;
  managedBotRoleMention: boolean;
  mentionedUserIds: string[];
  mentionedRoleIds: string[];
  managedBotRoleIds: string[];
}

export function detectBotMention(
  input: BotMentionDetectionInput
): BotMentionDetection {
  const rawUserMention =
    input.content.includes(`<@${input.botUserId}>`) ||
    input.content.includes(`<@!${input.botUserId}>`);
  const managedBotRoleMention = input.managedBotRoleIds.length > 0;

  let source: BotMentionSource = "none";
  if (input.structuredUserMention) source = "structured_user";
  else if (rawUserMention) source = "raw_user_token";
  else if (managedBotRoleMention) source = "managed_bot_role";

  return {
    mentionedBot: source !== "none",
    source,
    structuredUserMention: input.structuredUserMention,
    rawUserMention,
    managedBotRoleMention,
    mentionedUserIds: [...input.mentionedUserIds],
    mentionedRoleIds: [...input.mentionedRoleIds],
    managedBotRoleIds: [...input.managedBotRoleIds]
  };
}

export function stripBotMentionTokens(
  content: string,
  botUserId: string,
  managedBotRoleIds: string[]
): string {
  let result = content
    .replaceAll(`<@${botUserId}>`, "")
    .replaceAll(`<@!${botUserId}>`, "");

  for (const roleId of managedBotRoleIds) {
    result = result.replaceAll(`<@&${roleId}>`, "");
  }

  return result.trim();
}
