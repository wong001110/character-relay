import { groupAddressAliases } from "./audienceAliases.js";
import { recordSmartParticipationDecision } from "./behaviorDecisionTrace.js";
import {
  consumeSmartSelection,
  coordinateExplicitSmartParticipants,
  evaluateSmartFollowUp,
  evaluateSmartParticipation,
  markExplicitSmartSelections,
  type SmartParticipationSemanticScores
} from "./smartParticipation.js";
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
  const candidates = deploymentsFor(index, channelId, threadId, guildId, categoryId);
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
  | "selected_coordinated"
  | "selected_smart"
  | "selected_smart_multiple"
  | "selected_smart_follow_up"
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

  const values = new Set([full]);
  const normalized = full.replaceAll(/[（(]/gu, " · ").replaceAll(/[）)]/gu, "");
  const parts = normalized.split(/\s*(?:·|•|・|／|\/|\||｜)\s*|\s+(?:-|—|–)\s+/u);
  for (const part of parts) {
    const alias = part.trim();
    if (alias) values.add(alias);
  }
  return [...values];
}

function aliases(deployment: DiscordDeployment): string[] {
  return [
    ...new Set([
      ...(deployment.address_aliases ?? []).flatMap(nameAliases),
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
    .replace(/^(?:and|plus|和|与|與|跟|及|以及|还有|還有|&|＆)\s+/iu, "")
    .trimStart();
}

function withoutNameAlias(value: string, alias: string, requireTag = false): string | null {
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
  matches: Array<{ deployment: DiscordDeployment; alias: string }>;
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
  const uniqueMatches = new Map<string, { deployment: DiscordDeployment; alias: string }>();
  for (const item of top) {
    if (!uniqueMatches.has(item.deployment.deployment_id)) {
      uniqueMatches.set(item.deployment.deployment_id, {
        deployment: item.deployment,
        alias: item.alias
      });
    }
  }
  const selected = [...uniqueMatches.values()];
  return {
    matches: selected,
    deployments: selected.map((item) => item.deployment),
    remainder: top[0]?.remainder ?? value
  };
}

function requiresAsciiBoundary(alias: string): boolean {
  return /[A-Za-z0-9]$/u.test(alias);
}

function stripGroupAddress(value: string, additionalAliases: string[]): string | null {
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

function stripTaggedGroupAddress(value: string, additionalAliases: string[]): string | null {
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
      return { deployments: [], text: text.trim(), reason: "ambiguous", options };
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
    if (afterConnector !== afterPunctuation && matchNamePrefix(candidates, afterConnector, requireTag)) {
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
  additionalGroupAliases: string[] = [],
  semanticScores: SmartParticipationSemanticScores = {},
  runtimeScopeKey?: string
): AudienceResolution {
  const options = [...new Set(candidates.map(displayName))];
  if (!candidates.length) {
    return { deployments: [], text, reason: "not_found", options };
  }

  if (replyDeploymentId) {
    const replyTarget = candidates.find((item) => item.deployment_id === replyDeploymentId);
    if (replyTarget) {
      markExplicitSmartSelections([replyTarget], Date.now(), runtimeScopeKey);
      return { deployments: [replyTarget], text: text.trim(), reason: "selected_reply", options };
    }
  }

  const groupText = stripGroupAddress(text, additionalGroupAliases);
  if (groupText !== null) {
    markExplicitSmartSelections(candidates, Date.now(), runtimeScopeKey);
    return { deployments: [...candidates], text: groupText, reason: "selected_all", options };
  }

  const named = namedAudience(candidates, text, options);
  if (named) {
    if (named.deployments.length === 1) {
      const coordinated = coordinateExplicitSmartParticipants(
        candidates,
        named.deployments,
        named.text,
        Date.now(),
        semanticScores,
        runtimeScopeKey
      );
      if (coordinated.coordinated) {
        return { ...named, deployments: coordinated.deployments, reason: "selected_coordinated" };
      }
      return named;
    }
    markExplicitSmartSelections(named.deployments, Date.now(), runtimeScopeKey);
    return named;
  }

  const smartDecision = evaluateSmartParticipation(
    candidates,
    text,
    Date.now(),
    semanticScores,
    runtimeScopeKey
  );
  recordSmartParticipationDecision({
    message: text,
    decision: smartDecision,
    deployments: candidates
  });
  if (smartDecision.selectedDeployments.length) {
    return {
      deployments: smartDecision.selectedDeployments,
      text: text.trim(),
      reason:
        smartDecision.selectedDeployments.length > 1
          ? "selected_smart_multiple"
          : "selected_smart",
      options
    };
  }

  const only = candidates[0];
  if (candidates.length === 1 && only) {
    return { deployments: [only], text: text.trim(), reason: "selected_single", options };
  }
  return { deployments: [], text: text.trim(), reason: "ambiguous", options };
}

interface TaggedNameSequence {
  matches: Array<{ deployment: DiscordDeployment; alias: string }>;
  remainder: string;
  ambiguous: boolean;
}

function taggedNameSequence(candidates: DiscordDeployment[], text: string): TaggedNameSequence {
  const selected = new Map<string, { deployment: DiscordDeployment; alias: string }>();
  let remaining = text.trim();

  while (remaining) {
    const match = matchNamePrefix(candidates, remaining, true);
    if (!match) break;
    if (match.matches.length !== 1) {
      return { matches: [], remainder: text.trim(), ambiguous: true };
    }
    const selectedMatch = match.matches[0];
    if (!selectedMatch) break;
    selected.set(selectedMatch.deployment.deployment_id, selectedMatch);

    const afterPunctuation = stripLeadingPunctuation(match.remainder);
    if (matchNamePrefix(candidates, afterPunctuation, true)) {
      remaining = afterPunctuation;
      continue;
    }
    const afterConnector = stripLeadingNameConnector(afterPunctuation);
    if (afterConnector !== afterPunctuation && matchNamePrefix(candidates, afterConnector, true)) {
      remaining = afterConnector;
      continue;
    }
    remaining = afterPunctuation;
    break;
  }

  return { matches: [...selected.values()], remainder: remaining.trim(), ambiguous: false };
}

export interface BotTagNormalization {
  displayText: string;
  audience: AudienceResolution;
  removedSelfTag: boolean;
}

export function normalizeBotTagReply(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string,
  additionalGroupAliases: string[] = []
): BotTagNormalization {
  const available = candidates.filter((item) => item.deployment_id !== sourceDeploymentId);
  const options = [...new Set(available.map(displayName))];
  const original = text.trim();

  const groupText = stripTaggedGroupAddress(original, additionalGroupAliases);
  if (groupText !== null) {
    return {
      displayText: original,
      audience: {
        deployments: available,
        text: groupText,
        reason: available.length ? "selected_all" : "not_found",
        options
      },
      removedSelfTag: false
    };
  }

  const sequence = taggedNameSequence(candidates, original);
  if (sequence.ambiguous) {
    return {
      displayText: original,
      audience: { deployments: [], text: original, reason: "ambiguous", options },
      removedSelfTag: false
    };
  }
  if (!sequence.matches.length) {
    return {
      displayText: original,
      audience: { deployments: [], text: original, reason: "not_found", options },
      removedSelfTag: false
    };
  }

  const removedSelfTag = sequence.matches.some(
    (item) => item.deployment.deployment_id === sourceDeploymentId
  );
  const targetMatches = sequence.matches.filter(
    (item) => item.deployment.deployment_id !== sourceDeploymentId
  );
  const targetDeployments = targetMatches.map((item) => item.deployment);
  const visibleTags = targetMatches.map((item) => `@${item.alias}`).join(" and ");
  const displayText = [visibleTags, sequence.remainder].filter(Boolean).join(" ").trim();

  return {
    displayText,
    audience: {
      deployments: targetDeployments,
      text: sequence.remainder,
      reason:
        targetDeployments.length > 1
          ? "selected_multiple"
          : targetDeployments.length === 1
            ? "selected_alias"
            : "not_found",
      options
    },
    removedSelfTag
  };
}

interface InlineCharacterTagMatch {
  deployment: DiscordDeployment;
  alias: string;
  start: number;
  end: number;
}

const INLINE_TAG_LEFT_BOUNDARY = String.raw`(^|[\s:：,，、.。?？!！;；\-—–&＆/／+(（\[【])`;
const INLINE_TAG_RIGHT_BOUNDARY = String.raw`(?=$|[\s:：,，、.。?？!！;；\-—–&＆/／+)）\]】])`;
const SHARED_BOT_TAG_NAME = String.raw`[^\s:：,，、.。?？!！;；\-—–&＆/／+()（）\[\]【】<>]+`;

function inlineTagPosition(value: string, alias: string): { start: number; end: number } | null {
  const escapedAlias = escapeRegex(alias);
  const direct = new RegExp(
    `${INLINE_TAG_LEFT_BOUNDARY}[@＠]\\s*${escapedAlias}${INLINE_TAG_RIGHT_BOUNDARY}`,
    "iu"
  );
  const sharedBot = new RegExp(
    `${INLINE_TAG_LEFT_BOUNDARY}(?:<@!?\\d+>|[@＠]${SHARED_BOT_TAG_NAME})` +
      `\\s+${escapedAlias}${INLINE_TAG_RIGHT_BOUNDARY}`,
    "iu"
  );
  const matches = [direct.exec(value), sharedBot.exec(value)]
    .filter((item): item is RegExpExecArray => item !== null)
    .map((item) => ({
      start: item.index + (item[1]?.length ?? 0),
      end: item.index + item[0].length
    }))
    .sort((left, right) => left.start - right.start || right.end - left.end);
  return matches[0] ?? null;
}

function inlineTaggedAudience(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string
): AudienceResolution | null {
  const options = [
    ...new Set(
      candidates
        .filter((item) => item.deployment_id !== sourceDeploymentId)
        .map(displayName)
    )
  ];
  const matches: InlineCharacterTagMatch[] = [];
  for (const deployment of candidates) {
    if (deployment.deployment_id === sourceDeploymentId) continue;
    for (const alias of aliases(deployment)) {
      const position = inlineTagPosition(text, alias);
      if (!position) continue;
      matches.push({ deployment, alias, ...position });
    }
  }
  if (!matches.length) return null;

  matches.sort(
    (left, right) =>
      left.start - right.start || right.end - left.end || right.alias.length - left.alias.length
  );
  const selected = new Map<string, InlineCharacterTagMatch>();
  for (const match of matches) {
    if (!selected.has(match.deployment.deployment_id)) {
      selected.set(match.deployment.deployment_id, match);
    }
  }
  const uniqueMatches = [...selected.values()].sort((left, right) => left.start - right.start);
  const deployments = uniqueMatches.map((item) => item.deployment);
  const firstTagEnd = uniqueMatches[0]?.end ?? text.length;
  const remainder = stripLeadingPunctuation(text.slice(firstTagEnd));
  return {
    deployments,
    text: remainder || text.trim(),
    reason: deployments.length > 1 ? "selected_multiple" : "selected_alias",
    options
  };
}

export function resolveBotTagAudience(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string,
  additionalGroupAliases: string[] = []
): AudienceResolution {
  const leading = normalizeBotTagReply(
    candidates,
    text,
    sourceDeploymentId,
    additionalGroupAliases
  ).audience;
  if (leading.reason !== "not_found") return leading;

  const inline = inlineTaggedAudience(candidates, text, sourceDeploymentId);
  if (inline) return inline;

  const sourceDeployment = candidates.find((item) => item.deployment_id === sourceDeploymentId);
  if (!sourceDeployment) return leading;
  const followUp = evaluateSmartFollowUp(sourceDeployment, candidates);
  if (!followUp.selectedDeployment) return leading;
  return {
    deployments: [followUp.selectedDeployment],
    text: text.trim(),
    reason: "selected_smart_follow_up",
    options: leading.options
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
    case "smart": {
      const selected = consumeSmartSelection(deployment.deployment_id);
      return (
        trigger.mentionedBot ||
        trigger.repliedToBot ||
        (smartParticipationEnabled && trigger.hasReadableText && selected)
      );
    }
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
