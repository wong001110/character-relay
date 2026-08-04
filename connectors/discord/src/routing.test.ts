import { describe, expect, it } from "vitest";

import {
  buildDeploymentIndex,
  deploymentsFor,
  destinationKey,
  findDeployment,
  selectDeployment,
  shouldSubmitMessage,
  splitDiscordMessage
} from "./routing.js";
import type { DiscordDeployment } from "./types.js";

function deployment(
  participationMode: DiscordDeployment["participation_mode"],
  threadId = "",
  name = "Ann"
): DiscordDeployment {
  return {
    deployment_id: `deployment-${name}-${participationMode}-${threadId || "channel"}`,
    connection_id: "connection-1",
    character_card_id: `character-${name}`,
    character_display_name: name,
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "companions",
    thread_id: threadId,
    thread_name: threadId ? "Thread" : "",
    participation_mode: participationMode,
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: name,
    identity_avatar_url: `https://example.com/${name}.png`,
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null
  };
}

describe("Discord deployment routing", () => {
  it("keeps channel and thread destinations independent", () => {
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

  it("keeps multiple characters in one destination without overwriting", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");
    const index = buildDeploymentIndex([ann, ning]);

    expect(findDeployment(index, "channel-1")).toBeUndefined();
    expect(deploymentsFor(index, "channel-1").map((item) => item.character_display_name))
      .toEqual(["Ann", "宁"]);
  });

  it("selects a character by leading display name and removes the selector", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");

    const english = selectDeployment([ann, ning], "Ann, what do you think?");
    expect(english.deployment?.deployment_id).toBe(ann.deployment_id);
    expect(english.text).toBe("what do you think?");
    expect(english.reason).toBe("selected_alias");

    const chinese = selectDeployment([ann, ning], "宁：你同意吗？");
    expect(chinese.deployment?.deployment_id).toBe(ning.deployment_id);
    expect(chinese.text).toBe("你同意吗？");
  });

  it("derives Chinese and English aliases from a composite character name", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁 · Ning");

    const chinese = selectDeployment([ann, ning], "宁，你在吗？");
    expect(chinese.deployment?.deployment_id).toBe(ning.deployment_id);
    expect(chinese.text).toBe("你在吗？");
    expect(chinese.reason).toBe("selected_alias");

    const english = selectDeployment([ann, ning], "Ning, are you there?");
    expect(english.deployment?.deployment_id).toBe(ning.deployment_id);
    expect(english.text).toBe("are you there?");
  });

  it("derives aliases from parenthesized bilingual names", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁（Ning）");

    expect(selectDeployment([ann, ning], "宁：你好").deployment?.deployment_id)
      .toBe(ning.deployment_id);
    expect(selectDeployment([ann, ning], "Ning: hello").deployment?.deployment_id)
      .toBe(ning.deployment_id);
  });

  it("routes replies by the persisted deployment id before parsing aliases", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");
    const selected = selectDeployment(
      [ann, ning],
      "Why?",
      ning.deployment_id
    );

    expect(selected.deployment?.deployment_id).toBe(ning.deployment_id);
    expect(selected.reason).toBe("selected_reply");
  });

  it("requires disambiguation when multiple characters have no selector", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");
    const selected = selectDeployment([ann, ning], "What does everyone think?");

    expect(selected.deployment).toBeUndefined();
    expect(selected.reason).toBe("ambiguous");
    expect(selected.options).toEqual(["Ann", "宁"]);
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
