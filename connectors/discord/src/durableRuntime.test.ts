import { describe, expect, it } from "vitest";

import { socialOperationId } from "./durableRuntime.js";

describe("durable Social Turn operation IDs", () => {
  it("is stable for retries of the same Discord source event", () => {
    const input = {
      connectionId: "connection-1",
      guildId: "guild-1",
      channelId: "channel-1",
      threadId: "",
      sourceMessageId: "message-1"
    };

    const first = socialOperationId(input);
    const second = socialOperationId({ ...input });

    expect(first).toBe(second);
    expect(first).toMatch(/^[a-f0-9]{64}$/u);
  });

  it("changes when the Discord source event changes", () => {
    const base = {
      connectionId: "connection-1",
      guildId: "guild-1",
      channelId: "channel-1",
      threadId: "",
      sourceMessageId: "message-1"
    };

    expect(socialOperationId(base)).not.toBe(
      socialOperationId({ ...base, sourceMessageId: "message-2" })
    );
  });
});
