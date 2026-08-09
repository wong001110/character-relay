import { describe, expect, it } from "vitest";

import {
  buildDeploymentIndex,
  deploymentsFor,
  destinationKey,
  findDeployment,
  normalizeBotTagReply,
  resolveAudience,
  resolveBotTagAudience,
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
    address_aliases: [],
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null,
    orchestration_mode: "off",
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

it("routes explicit character tags while ignoring self tags", () => {
  const ann = deployment("mention_and_reply", "", "安 · Ann");
  const ning = deployment("mention_and_reply", "", "宁 · Ning");
  const zhi = deployment("mention_and_reply", "", "织 · Zhi");

  const single = resolveBotTagAudience(
    [ann, ning, zhi],
    "@宁，你怎么看？",
    ann.deployment_id
  );
  expect(single.reason).toBe("selected_alias");
  expect(single.deployments.map((item) => item.deployment_id)).toEqual([
    ning.deployment_id
  ]);
  expect(single.text).toBe("你怎么看？");

  const multiple = resolveBotTagAudience(
    [ann, ning, zhi],
    "@Ning and @Zhi, can you check this?",
    ann.deployment_id
  );
  expect(multiple.reason).toBe("selected_multiple");
  expect(multiple.deployments.map((item) => item.deployment_id)).toEqual([
    ning.deployment_id,
    zhi.deployment_id
  ]);
  expect(multiple.text).toBe("can you check this?");

  const self = resolveBotTagAudience(
    [ann, ning],
    "@Ann, I should not trigger myself.",
    ann.deployment_id
  );
  expect(self.deployments).toEqual([]);
  expect(self.reason).toBe("not_found");
});

it("uses explicit aliases independently of the Discord display name", () => {
  const ann = deployment("mention_and_reply", "", "安", {
    address_aliases: ["安", "Ann"]
  });
  const ning = deployment("mention_and_reply", "", "宁", {
    address_aliases: ["宁", "Ning"]
  });

  const selected = resolveAudience([ann, ning], "Ann ping");
  expect(selected.deployments[0]?.deployment_id).toBe(ann.deployment_id);
  expect(selected.text).toBe("ping");
});

it("removes self Tags before display and preserves other tagged characters", () => {
  const ann = deployment("mention_and_reply", "", "安・Ann", {
    address_aliases: ["安", "Ann"]
  });
  const ning = deployment("mention_and_reply", "", "宁・Ning", {
    address_aliases: ["宁", "Ning"]
  });

  const selfOnly = normalizeBotTagReply(
    [ann, ning],
    "@Ning 刚才的话题没有需要补充的。",
    ning.deployment_id
  );
  expect(selfOnly.displayText).toBe("刚才的话题没有需要补充的。");
  expect(selfOnly.audience.deployments).toEqual([]);
  expect(selfOnly.removedSelfTag).toBe(true);

  const mixed = normalizeBotTagReply(
    [ann, ning],
    "@Ning and @Ann 这部分交给你。",
    ning.deployment_id
  );
  expect(mixed.displayText).toBe("@Ann 这部分交给你。");
  expect(mixed.audience.deployments.map((item) => item.deployment_id)).toEqual([
    ann.deployment_id
  ]);
  expect(mixed.audience.text).toBe("这部分交给你。");
});

it("routes tagged group aliases to every other character", () => {
  const ann = deployment("mention_and_reply", "", "Ann");
  const ning = deployment("mention_and_reply", "", "宁 · Ning");
  const zhi = deployment("mention_and_reply", "", "织 · Zhi");

  const group = resolveBotTagAudience(
    [ann, ning, zhi],
    "@你们，这件事怎么看？",
    ann.deployment_id
  );
  expect(group.reason).toBe("selected_all");
  expect(group.deployments.map((item) => item.deployment_id)).toEqual([
    ning.deployment_id,
    zhi.deployment_id
  ]);
  expect(group.text).toBe("这件事怎么看？");

  const custom = resolveBotTagAudience(
    [ann, ning, zhi],
    "@companions, hello",
    ann.deployment_id,
    ["companions"]
  );
  expect(custom.deployments).toHaveLength(2);
  expect(custom.text).toBe("hello");
});

it("routes character tags that appear naturally inside a sentence", () => {
  const lili = deployment("mention_and_reply", "", "莉莉 · Lili");
  const mengmeng = deployment("mention_and_reply", "", "梦梦 · Mengmeng", {
    address_aliases: ["梦梦", "Mengmeng"]
  });

  const direct = resolveBotTagAudience(
    [lili, mengmeng],
    "你这个想法听起来很不错，@梦梦，你要不要试试把这些功能加进去？",
    lili.deployment_id
  );
  expect(direct.deployments.map((item) => item.deployment_id)).toEqual([
    mengmeng.deployment_id
  ]);
  expect(direct.text).toBe("你要不要试试把这些功能加进去？");

  const sharedBotName = resolveBotTagAudience(
    [lili, mengmeng],
    "这个方向可行，@CharacterRelayBot 梦梦，你怎么看？",
    lili.deployment_id
  );
  expect(sharedBotName.deployments[0]?.deployment_id).toBe(mengmeng.deployment_id);
  expect(sharedBotName.text).toBe("你怎么看？");

  const rawDiscordMention = resolveBotTagAudience(
    [lili, mengmeng],
    "我先整理方案，<@123456789012345678> 梦梦，接下来交给你。",
    lili.deployment_id
  );
  expect(rawDiscordMention.deployments[0]?.deployment_id).toBe(
    mengmeng.deployment_id
  );
  expect(rawDiscordMention.text).toBe("接下来交给你。");
});

it("routes multiple inline character tags once and still ignores inline self tags", () => {
  const ann = deployment("mention_and_reply", "", "安 · Ann");
  const ning = deployment("mention_and_reply", "", "宁 · Ning");
  const zhi = deployment("mention_and_reply", "", "织 · Zhi");

  const multiple = resolveBotTagAudience(
    [ann, ning, zhi],
    "我先给结论，@宁 负责复核，@织 负责整理。",
    ann.deployment_id
  );
  expect(multiple.deployments.map((item) => item.deployment_id)).toEqual([
    ning.deployment_id,
    zhi.deployment_id
  ]);

  const selfOnly = resolveBotTagAudience(
    [ann, ning],
    "这部分由 @Ann 我自己继续处理。",
    ann.deployment_id
  );
  expect(selfOnly.deployments).toEqual([]);
  expect(selfOnly.reason).toBe("not_found");
});

it("does not treat untagged character names as bot conversation triggers", () => {
  const ann = deployment("mention_and_reply", "", "Ann");
  const ning = deployment("mention_and_reply", "", "Ning");
  const result = resolveBotTagAudience(
    [ann, ning],
    "Ning, this is ordinary narration.",
    ann.deployment_id
  );
  expect(result.deployments).toEqual([]);
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
