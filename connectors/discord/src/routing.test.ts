import { describe, expect, it } from "vitest";

import {
  buildDeploymentIndex,
  destinationKey,
  findDeployment,
  shouldSubmitMessage,
  splitDiscordMessage
} from "./routing.js";
import type { DiscordDeployment } from "./types.js";

function deployment(
  participationMode: DiscordDeployment["participation_mode"],
  threadId = ""
): DiscordDeployment {
  return {
    deployment_id: `deployment-${participationMode}-${threadId || "channel"}`,
    connection_id: "connection-1",
    character_card_id: "character-1",
    character_display_name: "Ann",
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "ann-room",
    thread_id: threadId,
    thread_name: threadId ? "Thread" : "",
    participation_mode: participationMode,
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: "Ann",
    identity_avatar_url: "https://example.com/ann.png",
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null
  };
}

describe("Discord deployment routing", () => {
  it("keeps channel and thread deployments independent", () => {
    const channel = deployment("mention_and_reply");
    const thread = deployment("reply_only", "thread-1");
    const index = buildDeploymentIndex([channel, thread]);

    expect(destinationKey("channel-1")).toBe("channel-1");
    expect(destinationKey("channel-1", "thread-1")).toBe("channel-1:thread-1");
    expect(findDeployment(index, "channel-1")?.deployment_id).toBe(channel.deployment_id);
    expect(findDeployment(index, "channel-1", "thread-1")?.deployment_id).toBe(
      thread.deployment_id
    );
  });

  it("applies explicit trigger modes", () => {
    expect(
      shouldSubmitMessage(
        deployment("mention_only"),
        { mentionedBot: true, repliedToBot: false, hasReadableText: true },
        false
      )
    ).toBe(true);
    expect(
      shouldSubmitMessage(
        deployment("reply_only"),
        { mentionedBot: true, repliedToBot: false, hasReadableText: true },
        false
      )
    ).toBe(false);
    expect(
      shouldSubmitMessage(
        deployment("mention_and_reply"),
        { mentionedBot: false, repliedToBot: true, hasReadableText: true },
        false
      )
    ).toBe(true);
  });

  it("keeps smart participation opt-in", () => {
    const smart = deployment("smart");
    const ordinaryMessage = {
      mentionedBot: false,
      repliedToBot: false,
      hasReadableText: true
    };
    expect(shouldSubmitMessage(smart, ordinaryMessage, false)).toBe(false);
    expect(shouldSubmitMessage(smart, ordinaryMessage, true)).toBe(true);
  });

  it("splits long Discord messages without losing content", () => {
    const chunks = splitDiscordMessage("one two three four five", 10);
    expect(chunks.every((item) => item.length <= 10)).toBe(true);
    expect(chunks.join(" ")).toBe("one two three four five");
  });
});
