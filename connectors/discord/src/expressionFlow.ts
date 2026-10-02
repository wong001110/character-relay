import type { DiscordExpressionCandidate } from "./types.js";
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
        if (!resourceId || seen.has(resourceId))
            continue;
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
    if (candidate.resource_type !== "emoji")
        return "";
    return `<${candidate.animated ? "a" : ""}:${candidate.name}:${candidate.resource_id}>`;
}
