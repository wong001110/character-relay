import { describe,expect,it } from "vitest";
import { parseCustomEmojiTokens,stripCustomEmojiTokens } from "./expressionFlow.js";
import type { DiscordExpressionCandidate } from "./types.js";
function candidate(resourceKey: string, options: Partial<DiscordExpressionCandidate> = {}): DiscordExpressionCandidate {
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
        const parsed = parseCustomEmojiTokens("hello <:peek:123456789012345678> <a:dance:223456789012345678> <:peek:123456789012345678>");
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
        expect(stripCustomEmojiTokens("hello <:peek:123456789012345678> world ✨")).toBe("hello world ✨");
    });
});
