import type { DiscordDeployment } from "./types.js";

export function destinationKey(channelId: string, threadId = ""): string {
  return threadId ? `${channelId}:${threadId}` : channelId;
}

export function buildDeploymentIndex(
  deployments: DiscordDeployment[]
): Map<string, DiscordDeployment> {
  return new Map(
    deployments.map((deployment) => [
      destinationKey(deployment.channel_id, deployment.thread_id),
      deployment
    ])
  );
}

export function findDeployment(
  index: Map<string, DiscordDeployment>,
  channelId: string,
  threadId = ""
): DiscordDeployment | undefined {
  return index.get(destinationKey(channelId, threadId));
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
