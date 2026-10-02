import { describe, expect, it } from "vitest";

import { parseCustomEmojiTokens, renderCustomEmoji, stripCustomEmojiTokens } from "./expressionFlow.js";
import type {
  DiscordExpressionCandidate,
  DiscordExpressionDecision
} from "./types.js";

function candidate(
  resourceKey: string,
  options: Partial<DiscordExpressionCandidate> = {}
): DiscordExpressionCandidate {
  const [resourceType, resourceId] = resourceKey.split(":", 2) as [
    "emoji" | "sticker",
    string
  ];
  return {
    resource_key: resourceKey,
    resource_type: resourceType,
    resource_id: resourceId,
    name: resourceId,
    animated: false,
    available: true,
    enabled: true,
    allowed_actions: resourceType === "emoji" ? ["inline", "reaction"] : ["sticker"],
    semantic_intent: "",
    semantic_emotion: "",
    semantic_description: "",
    semantic_source: "manual",
    semantic_confidence: 1,
    asset_url: "",
    format_type: resourceType,
    score: 0.8,
    signals: {},
    ...options
  };
}

describe("Discord expression rendering, without a candidate selection workflow", () => {
  it("parses static and animated tokens without duplicate resources", () => {
    expect(parseCustomEmojiTokens("hello <:peek:123456789012345678> <a:dance:223456789012345678> <:peek:123456789012345678>"))
      .toEqual([
        { resource_key: "emoji:123456789012345678", resource_id: "123456789012345678", name: "peek", animated: false, token: "<:peek:123456789012345678>" },
        { resource_key: "emoji:223456789012345678", resource_id: "223456789012345678", name: "dance", animated: true, token: "<a:dance:223456789012345678>" }
      ]);
  });
  it("strips only custom tokens and preserves ordinary Unicode", () => {
    expect(stripCustomEmojiTokens("hello <:peek:123456789012345678> world ✨")).toBe("hello world ✨");
  });
  it("renders the resolved emoji, never inventing a fallback sticker", () => {
    expect(renderCustomEmoji(candidate("emoji:223456789012345678", { name: "dance", animated: true })))
      .toBe("<a:dance:223456789012345678>");
    expect(renderCustomEmoji(candidate("sticker:123"))).toBe("");
  });
  it("does not reinterpret ordinary prose or incomplete tokens", () => {
    expect(parseCustomEmojiTokens("dance:123 <wrong> <:x:123> <:a_b:no-id>")).toEqual([]);
  });
});
