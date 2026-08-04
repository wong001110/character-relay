import { describe, expect, it } from "vitest";

import {
  buildDeploymentIndex,
  deploymentsFor,
  destinationKey,
  findDeployment,
  resolveAudience,
  shouldSubmitMessage,
  splitDiscordMessage
} from "./routing.js";
import type { DiscordDeployment } from "./types.js";

function deployment(
  participationMode: DiscordDeployment["participation_mode"],
  threadId = "",
  name = "Ann",
  overrides: Partial<DiscordDeployment> = {}
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
    category_id: "category-1",
    server_profile_id: "",
    channel_scope_mode: "exact",
    excluded_channel_ids: [],
    excluded_category_ids: [],
    participation_mode: participationMode,
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: name,
    identity_avatar_url: `https://example.com/${name}.png`,
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null,
    ...overrides
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

  it("routes server-wide deployments to new channels by default", () => {
    const ann = deployment("mention_and_reply", "", "Ann", {
      deployment_id: "ann-server-wide",
      channel_id: "@server:profile-1",
      channel_name: "All available channels",
      server_profile_id: "profile-1",
      channel_scope_mode: "all_except"
    });
    const index = buildDeploymentIndex([ann]);

    expect(
      deploymentsFor(index, "new-channel", "", "guild-1", "new-category").map(
        (item) => item.deployment_id
      )
    ).toEqual([ann.deployment_id]);
  });

  it("applies profile and character channel exclusions", () => {
    const ann = deployment("mention_and_reply", "", "Ann", {
      deployment_id: "ann-server-wide",
      channel_id: "@server:profile-1",
      server_profile_id: "profile-1",
      channel_scope_mode: "all_except",
      excluded_channel_ids: ["private-channel"],
      excluded_category_ids: ["staff-category"]
    });
    const index = buildDeploymentIndex([ann]);

    expect(deploymentsFor(index, "general", "", "guild-1", "public-category")).toEqual([
      ann
    ]);
    expect(deploymentsFor(index, "private-channel", "", "guild-1", "public-category"))
      .toEqual([]);
    expect(deploymentsFor(index, "general", "", "guild-1", "staff-category"))
      .toEqual([]);
    expect(deploymentsFor(index, "general", "", "another-guild", "public-category"))
      .toEqual([]);
  });

  it("keeps multiple characters in one destination without overwriting", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");
    const index = buildDeploymentIndex([ann, ning]);

    expect(findDeployment(index, "channel-1")).toBeUndefined();
    expect(deploymentsFor(index, "channel-1").map((item) => item.character_display_name))
      .toEqual(["Ann", "宁"]);
  });

  it("selects one character by leading display name and removes the selector", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");

    const english = resolveAudience([ann, ning], "Ann, what do you think?");
    expect(english.deployments.map((item) => item.deployment_id)).toEqual([
      ann.deployment_id
    ]);
    expect(english.text).toBe("what do you think?");
    expect(english.reason).toBe("selected_alias");

    const chinese = resolveAudience([ann, ning], "宁：你同意吗？");
    expect(chinese.deployments.map((item) => item.deployment_id)).toEqual([
      ning.deployment_id
    ]);
    expect(chinese.text).toBe("你同意吗？");
  });

  it("derives Chinese and English aliases from a composite character name", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁 · Ning");

    const chinese = resolveAudience([ann, ning], "宁，你在吗？");
    expect(chinese.deployments[0]?.deployment_id).toBe(ning.deployment_id);
    expect(chinese.text).toBe("你在吗？");

    const english = resolveAudience([ann, ning], "Ning, are you there?");
    expect(english.deployments[0]?.deployment_id).toBe(ning.deployment_id);
    expect(english.text).toBe("are you there?");
  });

  it("selects multiple named characters in one mention", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁 · Ning");

    const chinese = resolveAudience([ann, ning], "Ann 和 宁，你们好呀");
    expect(chinese.reason).toBe("selected_multiple");
    expect(chinese.deployments.map((item) => item.deployment_id)).toEqual([
      ann.deployment_id,
      ning.deployment_id
    ]);
    expect(chinese.text).toBe("你们好呀");

    const english = resolveAudience([ann, ning], "Ann and Ning, hello");
    expect(english.deployments.map((item) => item.deployment_id)).toEqual([
      ann.deployment_id,
      ning.deployment_id
    ]);
    expect(english.text).toBe("hello");
  });

  it("routes explicit group addresses to every character", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁 · Ning");

    const chinese = resolveAudience([ann, ning], "你们好呀");
    expect(chinese.reason).toBe("selected_all");
    expect(chinese.deployments).toHaveLength(2);
    expect(chinese.text).toBe("好呀");

    const english = resolveAudience([ann, ning], "both of you, are you there?");
    expect(english.reason).toBe("selected_all");
    expect(english.deployments).toHaveLength(2);
    expect(english.text).toBe("are you there?");

    const languageNeutral = resolveAudience([ann, ning], "*: hello");
    expect(languageNeutral.reason).toBe("selected_all");
    expect(languageNeutral.text).toBe("hello");
  });

  it("accepts custom group address aliases without changing routing code", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");
    const selected = resolveAudience(
      [ann, ning],
      "companions, hello",
      null,
      ["companions"]
    );

    expect(selected.reason).toBe("selected_all");
    expect(selected.deployments).toHaveLength(2);
    expect(selected.text).toBe("hello");
  });

  it("routes replies by persisted deployment id before parsing aliases", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");
    const selected = resolveAudience(
      [ann, ning],
      "Ann, what do you think?",
      ning.deployment_id
    );

    expect(selected.deployments[0]?.deployment_id).toBe(ning.deployment_id);
    expect(selected.reason).toBe("selected_reply");
  });

  it("requires disambiguation when multiple characters have no audience signal", () => {
    const ann = deployment("mention_and_reply", "", "Ann");
    const ning = deployment("mention_and_reply", "", "宁");
    const selected = resolveAudience([ann, ning], "今天频道很安静");

    expect(selected.deployments).toEqual([]);
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
