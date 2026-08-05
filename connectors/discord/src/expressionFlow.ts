import type { DiscordExpressionCandidate, DiscordExpressionDecision } from "./types.js";

const CUSTOM_EMOJI_PATTERN = /<(a?):([A-Za-z0-9_]{2,32}):([0-9]{2,24})>/g;

export interface ParsedCustomEmoji {
  resource_key: string;
  resource_id: string;
  name: string;
  animated: boolean;
  token: string;
}

export function parseCustomEmojiTokens(content: string): ParsedCustomEmoji[] {
  const values: ParsedCustomEmoji[] = [];
  const seen = new Set<string>();
  for (const match of content.matchAll(CUSTOM_EMOJI_PATTERN)) {
    const resourceId = match[3] ?? "";
    if (!resourceId || seen.has(resourceId)) continue;
    seen.add(resourceId);
    values.push({
      resource_key: `emoji:${resourceId}`,
      resource_id: resourceId,
      name: match[2] ?? "emoji",
      animated: match[1] === "a",
      token: match[0]
    });
  }
  return values;
}

export function stripCustomEmojiTokens(content: string): string {
  return content.replace(CUSTOM_EMOJI_PATTERN, " ").replace(/\s+/g, " ").trim();
}

export function renderCustomEmoji(candidate: DiscordExpressionCandidate): string {
  if (candidate.resource_type !== "emoji") return "";
  return `<${candidate.animated ? "a" : ""}:${candidate.name}:${candidate.resource_id}>`;
}

export function expressionCandidate(
  candidates: DiscordExpressionCandidate[],
  resourceKey: string | null | undefined
): DiscordExpressionCandidate | null {
  if (!resourceKey) return null;
  return candidates.find((item) => item.resource_key === resourceKey) ?? null;
}

export function fallbackExpressionCandidate(
  candidates: DiscordExpressionCandidate[],
  decision: DiscordExpressionDecision,
  excludedResourceKeys: Set<string>
): DiscordExpressionCandidate | null {
  const action = decision.action;
  if (action === "none") return null;
  return (
    candidates.find(
      (item) =>
        !excludedResourceKeys.has(item.resource_key) &&
        item.allowed_actions.includes(action)
    ) ?? null
  );
}

export function expressionQuery(input: {
  text: string;
  stickerMeanings: string[];
  emojiMeanings: string[];
  recentText: string[];
}): string {
  return [input.text, ...input.stickerMeanings, ...input.emojiMeanings, ...input.recentText.slice(-4)]
    .map((item) => item.trim())
    .filter(Boolean)
    .join("\n")
    .slice(0, 4000);
}
