import { describe, expect, it } from "vitest";

import {
  buildMentionableParticipants,
  compileSmartMessage,
  smartOutputResourceCandidate
} from "./smartOutput.js";
import type {
  DiscordContextMessage,
  DiscordDeployment,
  DiscordExpressionCandidate,
  DiscordSmartOutput
} from "./types.js";

function deployment(id: string, name: string): DiscordDeployment {
  return {
    deployment_id: id,
    connection_id: "connection-1",
    character_card_id: `card-${id}`,
    character_display_name: name,
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "general",
    thread_id: "",
    thread_name: "",
    category_id: "",
    server_profile_id: "",
    channel_scope_mode: "exact",
    excluded_channel_ids: [],
    excluded_category_ids: [],
    participation_mode: "smart",
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: name,
    identity_avatar_url: "",
    address_aliases: [name],
    webhook_status: "active",
    webhook_id: "webhook-1",
    webhook_token: "token"
  };
}

function emoji(): DiscordExpressionCandidate {
  return {
    resource_key: "emoji:123",
    resource_type: "emoji",
    resource_id: "123",
    name: "peek",
    animated: false,
    available: true,
    enabled: true,
    allowed_actions: ["inline", "reaction"],
    semantic_intent: "peek",
    semantic_emotion: "curious",
    semantic_description: "curious peek",
    semantic_source: "manual",
    semantic_confidence: 1,
    asset_url: "",
    format_type: "emoji",
    score: 1,
    signals: {}
  };
}

function sticker(): DiscordExpressionCandidate {
  return {
    ...emoji(),
    resource_key: "sticker:456",
    resource_type: "sticker",
    resource_id: "456",
    name: "wave",
    allowed_actions: ["sticker"],
    format_type: "png"
  };
}

const ann = deployment("ann", "Ann");
const ning = deployment("ning", "Ning");

const recent: DiscordContextMessage[] = [
  {
    message_id: "message-1",
    author_id: "123456789012345678",
    author_display_name: "Juen",
    text: "hello",
    emojis: [],
    stickers: [],
    is_bot: false
  }
];

describe("Smart Output V1 compiler", () => {
  it("builds an allowlist without exposing the current character as mentionable", () => {
    const participants = buildMentionableParticipants([ann, ning], recent, ann);
    expect(participants).toEqual([
      {
        ref: "deployment:ning",
        display_name: "Ning",
        kind: "character"
      },
      {
        ref: "user:123456789012345678",
        display_name: "Juen",
        kind: "human"
      }
    ]);
  });

  it("compiles ordered text, custom Emoji, human mention, and character mention", () => {
    const participants = buildMentionableParticipants([ann, ning], recent, ann);
    const output: DiscordSmartOutput = {
      action: "message",
      content: [
        { text: "你 " },
        { emoji: "emoji:123" },
        { text: " 真的认真的？ " },
        { mention: "user:123456789012345678" },
        { text: " " },
        { mention: "deployment:ning" }
      ],
      reply_to_message_id: null,
      target_message_id: null,
      emoji_resource_key: null,
      sticker_resource_key: null
    };

    const result = compileSmartMessage(output, [ann, ning], ann, [emoji()], participants);
    expect(result.ok).toBe(true);
    expect(result.content).toBe("你 <:peek:123> 真的认真的？ <@123456789012345678> @Ning");
    expect(result.allowedUserIds).toEqual(["123456789012345678"]);
    expect(result.mentionedDeploymentIds).toEqual(["ning"]);
    expect(result.customEmojiResourceKeys).toEqual(["emoji:123"]);
  });

  it("rejects self or unapproved mentions instead of partially compiling", () => {
    const participants = buildMentionableParticipants([ann, ning], recent, ann);
    const output: DiscordSmartOutput = {
      action: "message",
      content: [{ text: "hi " }, { mention: "deployment:ann" }],
      reply_to_message_id: null,
      target_message_id: null,
      emoji_resource_key: null,
      sticker_resource_key: null
    };
    const result = compileSmartMessage(output, [ann, ning], ann, [emoji()], participants);
    expect(result.ok).toBe(false);
    expect(result.error).toBe("mention_participant_not_allowed");
    expect(result.content).toBe("");
  });

  it("rejects a custom Emoji that was not retrieved for inline use", () => {
    const participants = buildMentionableParticipants([ann, ning], recent, ann);
    const output: DiscordSmartOutput = {
      action: "message",
      content: [{ emoji: "emoji:unknown" }],
      reply_to_message_id: null,
      target_message_id: null,
      emoji_resource_key: null,
      sticker_resource_key: null
    };
    expect(
      compileSmartMessage(output, [ann, ning], ann, [emoji()], participants).error
    ).toBe("inline_emoji_resource_not_allowed");
  });

  it("validates reaction and Sticker resources against allowed actions", () => {
    expect(
      smartOutputResourceCandidate(
        {
          action: "react",
          content: [],
          reply_to_message_id: null,
          target_message_id: "message-1",
          emoji_resource_key: "emoji:123",
          sticker_resource_key: null
        },
        [emoji(), sticker()]
      )?.resource_key
    ).toBe("emoji:123");
    expect(
      smartOutputResourceCandidate(
        {
          action: "sticker",
          content: [],
          reply_to_message_id: null,
          target_message_id: null,
          emoji_resource_key: null,
          sticker_resource_key: "sticker:456"
        },
        [emoji(), sticker()]
      )?.resource_key
    ).toBe("sticker:456");
  });
});
