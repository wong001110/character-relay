import { groupAddressAliases } from "./audienceAliases.js";
import type { DiscordDeployment } from "./types.js";

export type DeploymentIndex = Map<string, DiscordDeployment[]>;

export function destinationKey(channelId: string, threadId = ""): string {
  return threadId ? `${channelId}:${threadId}` : channelId;
}

function guildScopeKey(guildId: string): string {
  return `@guild:${guildId}`;
}

export function buildDeploymentIndex(
  deployments: DiscordDeployment[]
): DeploymentIndex {
  const index: DeploymentIndex = new Map();
  for (const deployment of deployments) {
    const key =
      deployment.channel_scope_mode === "all_except"
        ? guildScopeKey(deployment.workspace_id)
        : destinationKey(deployment.channel_id, deployment.thread_id);
    const current = index.get(key) ?? [];
    current.push(deployment);
    index.set(key, current);
  }
  return index;
}

export function deploymentsFor(
  index: DeploymentIndex,
  channelId: string,
  threadId = "",
  guildId = "",
  categoryId = ""
): DiscordDeployment[] {
  const exact = index.get(destinationKey(channelId, threadId)) ?? [];
  const serverWide = guildId
    ? (index.get(guildScopeKey(guildId)) ?? []).filter(
        (deployment) =>
          !deployment.excluded_channel_ids.includes(channelId) &&
          (!categoryId || !deployment.excluded_category_ids.includes(categoryId))
      )
    : [];
  return [
    ...new Map(
      [...exact, ...serverWide].map((deployment) => [
        deployment.deployment_id,
        deployment
      ])
    ).values()
  ];
}

export function findDeployment(
  index: DeploymentIndex,
  channelId: string,
  threadId = "",
  guildId = "",
  categoryId = ""
): DiscordDeployment | undefined {
  const candidates = deploymentsFor(
    index,
    channelId,
    threadId,
    guildId,
    categoryId
  );
  return candidates.length === 1 ? candidates[0] : undefined;
}

export function flattenDeployments(index: DeploymentIndex): DiscordDeployment[] {
  return [...index.values()].flat();
}

export type AudienceReason =
  | "selected_reply"
  | "selected_alias"
  | "selected_multiple"
  | "selected_all"
  | "selected_single"
  | "ambiguous"
  | "not_found";

export interface AudienceResolution {
  deployments: DiscordDeployment[];
  text: string;
  reason: AudienceReason;
  options: string[];
}

function displayName(deployment: DiscordDeployment): string {
  return deployment.identity_display_name || deployment.character_display_name;
}

function nameAliases(value: string): string[] {
  const full = value.trim();
  if (!full) return [];

  const aliases = new Set([full]);
  const normalized = full
    .replaceAll(/[（(]/gu, " · ")
    .replaceAll(/[）)]/gu, "");
  const parts = normalized.split(
    /\s*(?:·|•|・|／|\/|\||｜)\s*|\s+(?:-|—|–)\s+/u
  );
  for (const part of parts) {
    const alias = part.trim();
    if (alias) aliases.add(alias);
  }
  return [...aliases];
}

function aliases(deployment: DiscordDeployment): string[] {
  return [
    ...new Set([
      ...nameAliases(deployment.identity_display_name),
      ...nameAliases(deployment.character_display_name)
    ])
  ].sort((left, right) => right.length - left.length);
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function stripLeadingPunctuation(value: string): string {
  return value.replace(/^[\s:：,，、.。?？!！\-—–/／+]+/u, "").trimStart();
}

function stripLeadingNameConnector(value: string): string {
  return value
    .replace(
      /^(?:and|plus|和|与|與|跟|及|以及|还有|還有|&|＆)\s+/iu,
      ""
    )
    .trimStart();
}

function withoutNameAlias(
  value: string,
  alias: string,
  requireTag = false
): string | null {
  const pattern = new RegExp(
    `^${escapeRegex(alias)}(?=$|[\\s:：,，、.。?？!！\\-—–&＆/／+和与與跟及])`,
    "iu"
  );
  let trimmed = value.trimStart();
  if (requireTag) {
    const tag = trimmed.match(/^[@＠]\s*/u);
    if (!tag) return null;
    trimmed = trimmed.slice(tag[0].length);
  }
  const match = trimmed.match(pattern);
  if (!match) return null;
  return trimmed.slice(match[0].length);
}

interface NameMatch {
  deployments: DiscordDeployment[];
  remainder: string;
}

function matchNamePrefix(
  candidates: DiscordDeployment[],
  value: string,
  requireTag = false
): NameMatch | null {
  const matches = candidates.flatMap((deployment) =>
    aliases(deployment).flatMap((alias) => {
      const remainder = withoutNameAlias(value, alias, requireTag);
      return remainder === null ? [] : [{ deployment, alias, remainder }];
    })
  );
  if (!matches.length) return null;

  const longest = Math.max(...matches.map((item) => item.alias.length));
  const top = matches.filter((item) => item.alias.length === longest);
  const deployments = [
    ...new Map(top.map((item) => [item.deployment.deployment_id, item.deployment])).values()
  ];
  return {
    deployments,
    remainder: top[0]?.remainder ?? value
  };
}

function requiresAsciiBoundary(alias: string): boolean {
  return /[A-Za-z0-9]$/u.test(alias);
}

function stripGroupAddress(
  value: string,
  additionalAliases: string[]
): string | null {
  const trimmed = value.trimStart();
  const explicitAll = trimmed.match(/^\*(?:\s*[:：,，-])?\s*/u);
  if (explicitAll) return trimmed.slice(explicitAll[0].length).trimStart();

  for (const alias of groupAddressAliases(additionalAliases)) {
    const lowerValue = trimmed.toLocaleLowerCase();
    const lowerAlias = alias.toLocaleLowerCase();
    if (!lowerValue.startsWith(lowerAlias)) continue;

    const remainder = trimmed.slice(alias.length);
    if (
      requiresAsciiBoundary(alias) &&
      remainder &&
      !/^[\s:：,，、.。?？!！\-—–/／+]/u.test(remainder)
    ) {
      continue;
    }
    return stripLeadingPunctuation(remainder);
  }
  return null;
}

function stripTaggedGroupAddress(
  value: string,
  additionalAliases: string[]
): string | null {
  const trimmed = value.trimStart();
  const tag = trimmed.match(/^[@＠]\s*/u);
  if (!tag) return null;
  return stripGroupAddress(trimmed.slice(tag[0].length), additionalAliases);
}

function namedAudience(
  candidates: DiscordDeployment[],
  text: string,
  options: string[],
  requireTag = false
): AudienceResolution | null {
  const selected = new Map<string, DiscordDeployment>();
  let remaining = text.trim();

  while (remaining) {
    const match = matchNamePrefix(candidates, remaining, requireTag);
    if (!match) break;
    if (match.deployments.length !== 1) {
      return {
        deployments: [],
        text: text.trim(),
        reason: "ambiguous",
        options
      };
    }

    const deployment = match.deployments[0];
    if (!deployment) break;
    selected.set(deployment.deployment_id, deployment);

    const afterPunctuation = stripLeadingPunctuation(match.remainder);
    const directNext = matchNamePrefix(candidates, afterPunctuation, requireTag);
    if (directNext) {
      remaining = afterPunctuation;
      continue;
    }

    const afterConnector = stripLeadingNameConnector(afterPunctuation);
    if (
      afterConnector !== afterPunctuation &&
      matchNamePrefix(candidates, afterConnector, requireTag)
    ) {
      remaining = afterConnector;
      continue;
    }

    remaining = afterPunctuation;
    break;
  }

  const deployments = [...selected.values()];
  if (!deployments.length) return null;
  return {
    deployments,
    text: remaining,
    reason: deployments.length > 1 ? "selected_multiple" : "selected_alias",
    options
  };
}

export function resolveAudience(
  candidates: DiscordDeployment[],
  text: string,
  replyDeploymentId?: string | null,
  additionalGroupAliases: string[] = []
): AudienceResolution {
  const options = [...new Set(candidates.map(displayName))];
  if (!candidates.length) {
    return {
      deployments: [],
      text,
      reason: "not_found",
      options
    };
  }

  if (replyDeploymentId) {
    const replyTarget = candidates.find(
      (item) => item.deployment_id === replyDeploymentId
    );
    if (replyTarget) {
      return {
        deployments: [replyTarget],
        text: text.trim(),
        reason: "selected_reply",
        options
      };
    }
  }

  const groupText = stripGroupAddress(text, additionalGroupAliases);
  if (groupText !== null) {
    return {
      deployments: [...candidates],
      text: groupText,
      reason: "selected_all",
      options
    };
  }

  const named = namedAudience(candidates, text, options);
  if (named) return named;

  const only = candidates[0];
  if (candidates.length === 1 && only) {
    return {
      deployments: [only],
      text: text.trim(),
      reason: "selected_single",
      options
    };
  }
  return {
    deployments: [],
    text: text.trim(),
    reason: "ambiguous",
    options
  };
}

export function resolveBotTagAudience(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string,
  additionalGroupAliases: string[] = []
): AudienceResolution {
  const available = candidates.filter(
    (item) => item.deployment_id !== sourceDeploymentId
  );
  const options = [...new Set(available.map(displayName))];
  if (!available.length) {
    return { deployments: [], text: text.trim(), reason: "not_found", options };
  }

  const groupText = stripTaggedGroupAddress(text, additionalGroupAliases);
  if (groupText !== null) {
    return {
      deployments: available,
      text: groupText,
      reason: "selected_all",
      options
    };
  }

  const named = namedAudience(available, text, options, true);
  if (named) return named;
  return {
    deployments: [],
    text: text.trim(),
    reason: "not_found",
    options
  };
}

export interface TriggerState {
  mentionedBot: boolean;
  repliedToBot: boolean;
  hasReadableText: boolean;
}

export function shouldSubmitMessage(
  deployment: DiscordDeployment,
  trigger: TriggerState,
  smartParticipationEnabled: boolean
): boolean {
  if (!trigger.hasReadableText && !trigger.mentionedBot && !trigger.repliedToBot) {
    return false;
  }
  switch (deployment.participation_mode) {
    case "mention_only":
      return trigger.mentionedBot;
    case "reply_only":
      return trigger.repliedToBot;
    case "mention_and_reply":
      return trigger.mentionedBot || trigger.repliedToBot;
    case "smart":
      return (
        trigger.mentionedBot ||
        trigger.repliedToBot ||
        (smartParticipationEnabled && trigger.hasReadableText)
      );
  }
}

export function splitDiscordMessage(value: string, maximumLength = 1900): string[] {
  const normalized = value.trim();
  if (!normalized) return [];
  const chunks: string[] = [];
  let remaining = normalized;
  while (remaining.length > maximumLength) {
    const window = remaining.slice(0, maximumLength + 1);
    const boundary = Math.max(window.lastIndexOf("\n"), window.lastIndexOf(" "));
    const splitAt = boundary > maximumLength * 0.5 ? boundary : maximumLength;
    chunks.push(remaining.slice(0, splitAt).trimEnd());
    remaining = remaining.slice(splitAt).trimStart();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}
