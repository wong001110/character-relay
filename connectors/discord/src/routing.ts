import type { DiscordDeployment } from "./types.js";

export type DeploymentIndex = Map<string, DiscordDeployment[]>;

export function destinationKey(channelId: string, threadId = ""): string {
  return threadId ? `${channelId}:${threadId}` : channelId;
}

export function buildDeploymentIndex(
  deployments: DiscordDeployment[]
): DeploymentIndex {
  const index: DeploymentIndex = new Map();
  for (const deployment of deployments) {
    const key = destinationKey(deployment.channel_id, deployment.thread_id);
    const current = index.get(key) ?? [];
    current.push(deployment);
    index.set(key, current);
  }
  return index;
}

export function deploymentsFor(
  index: DeploymentIndex,
  channelId: string,
  threadId = ""
): DiscordDeployment[] {
  return index.get(destinationKey(channelId, threadId)) ?? [];
}

export function findDeployment(
  index: DeploymentIndex,
  channelId: string,
  threadId = ""
): DiscordDeployment | undefined {
  const candidates = deploymentsFor(index, channelId, threadId);
  return candidates.length === 1 ? candidates[0] : undefined;
}

export function flattenDeployments(index: DeploymentIndex): DiscordDeployment[] {
  return [...index.values()].flat();
}

export interface DeploymentSelection {
  deployment?: DiscordDeployment;
  text: string;
  reason:
    | "selected_reply"
    | "selected_alias"
    | "selected_single"
    | "ambiguous"
    | "not_found";
  options: string[];
}

function displayName(deployment: DiscordDeployment): string {
  return deployment.identity_display_name || deployment.character_display_name;
}

function aliases(deployment: DiscordDeployment): string[] {
  return [...new Set([
    deployment.identity_display_name.trim(),
    deployment.character_display_name.trim()
  ].filter(Boolean))].sort((left, right) => right.length - left.length);
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function withoutAlias(value: string, alias: string): string | null {
  const pattern = new RegExp(
    `^${escapeRegex(alias)}(?=$|[\\s:：,，\\-—])[\\s:：,，\\-—]*`,
    "iu"
  );
  const match = value.trim().match(pattern);
  if (!match) return null;
  return value.trim().slice(match[0].length).trim();
}

export function selectDeployment(
  candidates: DiscordDeployment[],
  text: string,
  replyDeploymentId?: string | null
): DeploymentSelection {
  const options = [...new Set(candidates.map(displayName))];
  if (!candidates.length) {
    return { text, reason: "not_found", options };
  }

  if (replyDeploymentId) {
    const replyTarget = candidates.find(
      (item) => item.deployment_id === replyDeploymentId
    );
    if (replyTarget) {
      return {
        deployment: replyTarget,
        text: text.trim(),
        reason: "selected_reply",
        options
      };
    }
  }

  const matched = candidates.flatMap((deployment) =>
    aliases(deployment).flatMap((alias) => {
      const remaining = withoutAlias(text, alias);
      return remaining === null ? [] : [{ deployment, remaining }];
    })
  );
  const uniqueMatches = new Map(
    matched.map((item) => [item.deployment.deployment_id, item])
  );
  if (uniqueMatches.size === 1) {
    const selected = [...uniqueMatches.values()][0];
    if (selected) {
      return {
        deployment: selected.deployment,
        text: selected.remaining,
        reason: "selected_alias",
        options
      };
    }
  }
  if (uniqueMatches.size > 1) {
    return { text: text.trim(), reason: "ambiguous", options };
  }

  const only = candidates[0];
  if (candidates.length === 1 && only) {
    return {
      deployment: only,
      text: text.trim(),
      reason: "selected_single",
      options
    };
  }
  return { text: text.trim(), reason: "ambiguous", options };
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
