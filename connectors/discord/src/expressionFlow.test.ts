import { describe, expect, it } from "vitest";

import {
  expressionCandidate,
  expressionQuery,
  fallbackExpressionCandidate,
  parseCustomEmojiTokens,
  renderCustomEmoji,
  stripCustomEmojiTokens
} from "./expressionFlow.js";
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

describe("Discord expression helpers", () => {
  it("parses static and animated custom Emoji without duplicates", () => {
    const parsed = parseCustomEmojiTokens(
      "hello <:peek:123456789012345678> <a:dance:223456789012345678> <:peek:123456789012345678>"
    );

    expect(parsed).toEqual([
      {
        resource_key: "emoji:123456789012345678",
        resource_id: "123456789012345678",
        name: "peek",
        animated: false,
        token: "<:peek:123456789012345678>"
      },
      {
        resource_key: "emoji:223456789012345678",
        resource_id: "223456789012345678",
        name: "dance",
        animated: true,
        token: "<a:dance:223456789012345678>"
      }
    ]);
  });

  it("strips only custom Emoji tokens from readable text", () => {
    expect(
      stripCustomEmojiTokens("hello <:peek:123456789012345678> world ✨")
    ).toBe("hello world ✨");
  });

  it("renders custom Emoji and resolves exact candidates", () => {
    const animated = candidate("emoji:223456789012345678", {
      name: "dance",
      animated: true
    });
    expect(renderCustomEmoji(animated)).toBe("<a:dance:223456789012345678>");
    expect(expressionCandidate([animated], animated.resource_key)).toEqual(animated);
    expect(expressionCandidate([animated], "emoji:missing")).toBeNull();
  });

  it("chooses a fallback matching the requested action", () => {
    const inlineOnly = candidate("emoji:1", { allowed_actions: ["inline"] });
    const reaction = candidate("emoji:2", { allowed_actions: ["reaction"] });
    const decision: DiscordExpressionDecision = {
      action: "reaction",
      resource_key: inlineOnly.resource_key,
      reason: "react briefly"
    };

    expect(
      fallbackExpressionCandidate(
        [inlineOnly, reaction],
        decision,
        new Set([inlineOnly.resource_key])
      )
    ).toEqual(reaction);
  });

  it("builds a bounded retrieval query", () => {
    const query = expressionQuery({
      text: "latest message",
      stickerMeanings: ["playful disbelief"],
      emojiMeanings: ["curious peek"],
      recentText: ["one", "two", "three", "four", "five", "x".repeat(5000)]
    });

    expect(query).toContain("latest message");
    expect(query).toContain("curious peek");
    expect(query.length).toBeLessThanOrEqual(4000);
    expect(query).not.toContain("one");
    expect(query).not.toContain("two");
  });
});
