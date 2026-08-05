import { describe, expect, it } from "vitest";

import { detectBotMention, stripBotMentionTokens } from "./mentionDetection.js";

const BOT_ID = "1533872701884596334";

describe("detectBotMention", () => {
  it("accepts a structured user mention", () => {
    const result = detectBotMention({
      content: "ping",
      botUserId: BOT_ID,
      structuredUserMention: true,
      mentionedUserIds: [BOT_ID],
      mentionedRoleIds: [],
      managedBotRoleIds: []
    });

    expect(result.mentionedBot).toBe(true);
    expect(result.source).toBe("structured_user");
  });

  it("falls back to the raw Discord user mention token", () => {
    const result = detectBotMention({
      content: `<@${BOT_ID}> ping`,
      botUserId: BOT_ID,
      structuredUserMention: false,
      mentionedUserIds: [],
      mentionedRoleIds: [],
      managedBotRoleIds: []
    });

    expect(result.mentionedBot).toBe(true);
    expect(result.source).toBe("raw_user_token");
  });

  it("accepts only a managed role that belongs to this Bot", () => {
    const result = detectBotMention({
      content: "<@&role-bot> ping",
      botUserId: BOT_ID,
      structuredUserMention: false,
      mentionedUserIds: [],
      mentionedRoleIds: ["role-bot"],
      managedBotRoleIds: ["role-bot"]
    });

    expect(result.mentionedBot).toBe(true);
    expect(result.source).toBe("managed_bot_role");
  });

  it("does not treat an unrelated role as a Bot mention", () => {
    const result = detectBotMention({
      content: "<@&role-other> ping",
      botUserId: BOT_ID,
      structuredUserMention: false,
      mentionedUserIds: [],
      mentionedRoleIds: ["role-other"],
      managedBotRoleIds: []
    });

    expect(result.mentionedBot).toBe(false);
    expect(result.source).toBe("none");
  });
});

describe("stripBotMentionTokens", () => {
  it("removes user and managed Bot role tokens without changing the message body", () => {
    expect(
      stripBotMentionTokens(
        `<@${BOT_ID}> <@&role-bot> 賽琳娜，你好`,
        BOT_ID,
        ["role-bot"]
      )
    ).toBe("賽琳娜，你好");
  });
});
