import { renderCustomEmoji } from "./expressionFlow.js";
import type {
  DiscordActionParticipant,
  DiscordContextMessage,
  DiscordDeployment,
  DiscordExpressionCandidate,
  DiscordSmartOutput
} from "./types.js";

export interface CompiledSmartMessage {
  ok: boolean;
  content: string;
  allowedUserIds: string[];
  mentionedDeploymentIds: string[];
  customEmojiResourceKeys: string[];
  error: string;
}

function displayName(deployment: DiscordDeployment): string {
  return deployment.identity_display_name || deployment.character_display_name;
}

function addressName(deployment: DiscordDeployment): string {
  return deployment.address_aliases?.[0] || displayName(deployment);
}

export function buildMentionableParticipants(
  deployments: DiscordDeployment[],
  recentMessages: DiscordContextMessage[],
  currentDeployment: DiscordDeployment
): DiscordActionParticipant[] {
  const participants = new Map<string, DiscordActionParticipant>();

  // Recent humans must not be crowded out by a room full of deployed roles.
  // Newest first preserves the latest name for a stable ID, never name identity.
  const newestFirst = [...recentMessages].reverse();
  for (const message of newestFirst) {
    if (message.is_bot || !message.author_id || !message.author_display_name) continue;
    const ref = `user:${message.author_id}`;
    if (!participants.has(ref)) {
      participants.set(ref, {
        ref,
        display_name: message.author_display_name,
        kind: "human"
      });
    }
  }

  for (const message of newestFirst) {
    if (!message.is_bot || !message.author_id) continue;
    // Existing synthetic role messages use Character Card IDs. Never infer a
    // role from a display name or pick one when a Card has multiple deployments.
    const matches = deployments.filter(
      (item) => message.author_deployment_id
      ? item.deployment_id === message.author_deployment_id
      : message.author_id === `character:${item.character_card_id}`
    );
    const role = matches.length === 1 ? matches[0] : undefined;
    if (!role || role.deployment_id === currentDeployment.deployment_id) continue;
    const ref = `deployment:${role.deployment_id}`;
    if (!participants.has(ref)) {
      participants.set(ref, {
        ref,
        display_name: addressName(role),
        kind: "character"
      });
    }
  }

  for (const deployment of deployments) {
    if (deployment.deployment_id === currentDeployment.deployment_id) continue;
    const ref = `deployment:${deployment.deployment_id}`;
    if (!participants.has(ref)) {
      participants.set(ref, {
        ref,
        display_name: addressName(deployment),
        kind: "character"
      });
    }
  }

  return [...participants.values()].slice(0, 12);
}

export function reserveUniqueCharacterTurn(
  participantsSeen: Set<string>,
  deploymentId: string
): boolean {
  if (participantsSeen.has(deploymentId)) return false;
  participantsSeen.add(deploymentId);
  return true;
}

function failed(error: string): CompiledSmartMessage {
  return {
    ok: false,
    content: "",
    allowedUserIds: [],
    mentionedDeploymentIds: [],
    customEmojiResourceKeys: [],
    error
  };
}

export function compileSmartMessage(
  output: DiscordSmartOutput,
  deployments: DiscordDeployment[],
  currentDeployment: DiscordDeployment,
  expressionCandidates: DiscordExpressionCandidate[],
  mentionableParticipants: DiscordActionParticipant[]
): CompiledSmartMessage {
  if (output.action !== "message") return failed("not_message_action");

  const expressionByKey = new Map(
    expressionCandidates.map((candidate) => [candidate.resource_key, candidate])
  );
  const participantByRef = new Map(
    mentionableParticipants.map((participant) => [participant.ref, participant])
  );
  const deploymentById = new Map(
    deployments.map((deployment) => [deployment.deployment_id, deployment])
  );

  const values: string[] = [];
  const allowedUserIds = new Set<string>();
  const mentionedDeploymentIds = new Set<string>();
  const customEmojiResourceKeys = new Set<string>();

  for (const part of output.content) {
    if ("text" in part) {
      values.push(part.text);
      continue;
    }

    if ("emoji" in part) {
      const candidate = expressionByKey.get(part.emoji);
      if (
        !candidate ||
        candidate.resource_type !== "emoji" ||
        !candidate.available ||
        !candidate.enabled ||
        !candidate.allowed_actions.includes("inline")
      ) {
        return failed("inline_emoji_resource_not_allowed");
      }
      customEmojiResourceKeys.add(candidate.resource_key);
      if (customEmojiResourceKeys.size > 1) return failed("too_many_custom_emojis");
      values.push(renderCustomEmoji(candidate));
      continue;
    }

    const participant = participantByRef.get(part.mention);
    if (!participant) return failed("mention_participant_not_allowed");

    if (participant.kind === "human") {
      if (!participant.ref.startsWith("user:")) return failed("invalid_human_reference");
      const userId = participant.ref.slice("user:".length);
      if (!/^\d{5,30}$/u.test(userId)) return failed("invalid_human_reference");
      allowedUserIds.add(userId);
      values.push(`<@${userId}>`);
      continue;
    }

    if (!participant.ref.startsWith("deployment:")) {
      return failed("invalid_character_reference");
    }
    const deploymentId = participant.ref.slice("deployment:".length);
    if (deploymentId === currentDeployment.deployment_id) {
      return failed("self_mention_not_allowed");
    }
    const deployment = deploymentById.get(deploymentId);
    if (!deployment) return failed("character_reference_not_active");
    mentionedDeploymentIds.add(deploymentId);
    values.push(`@${addressName(deployment)}`);
  }

  const content = values.join("");
  if (!content.trim()) return failed("empty_message_content");
  if (content.length > 8000) return failed("message_content_too_long");

  return {
    ok: true,
    content,
    allowedUserIds: [...allowedUserIds],
    mentionedDeploymentIds: [...mentionedDeploymentIds],
    customEmojiResourceKeys: [...customEmojiResourceKeys],
    error: ""
  };
}

export function smartOutputResourceCandidate(
  output: DiscordSmartOutput,
  candidates: DiscordExpressionCandidate[]
): DiscordExpressionCandidate | null {
  const resourceKey =
    output.action === "react"
      ? output.emoji_resource_key
      : output.action === "sticker"
        ? output.sticker_resource_key
        : null;
  if (!resourceKey) return null;
  const candidate = candidates.find((item) => item.resource_key === resourceKey) ?? null;
  if (!candidate || !candidate.available || !candidate.enabled) return null;
  if (
    output.action === "react" &&
    (candidate.resource_type !== "emoji" || !candidate.allowed_actions.includes("reaction"))
  ) {
    return null;
  }
  if (
    output.action === "sticker" &&
    (candidate.resource_type !== "sticker" || !candidate.allowed_actions.includes("sticker"))
  ) {
    return null;
  }
  return candidate;
}
