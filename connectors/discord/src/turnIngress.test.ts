import { afterEach, describe, expect, it, vi } from "vitest";

import {
  TurnIngressCoordinator,
  buildConversationBurstId,
  buildConversationBurstText,
  decideTurnCollection,
  summarizeConversationBurst
} from "./turnIngress.js";

interface SampleTurn {
  id: string;
  text: string;
}

function sample(id: string, text: string): SampleTurn {
  return { id, text };
}

describe("TurnIngressCoordinator", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("collapses rapid collectable messages into one queued runtime turn", async () => {
    vi.useFakeTimers();
    const runtimeTasks: Array<() => Promise<void>> = [];
    const executed: Array<{ id: string; burstIds: string[] }> = [];
    const coordinator = new TurnIngressCoordinator<SampleTurn>(
      { quietWindowMs: 100, maxWaitMs: 400, maxMessages: 5, maxCharacters: 100 },
      (_scope, task) => { runtimeTasks.push(task); return true; }
    );

    for (const [id, text] of [
      ["1", "我觉得"],
      ["2", "刚才那个"],
      ["3", "其实蛮好笑的"]
    ] as const) {
      coordinator.submit("channel", {
        id,
        value: sample(id, text),
        characters: text.length,
        collect: true,
        execute: async (burst) => {
          executed.push({ id, burstIds: burst?.itemIds ?? [] });
        }
      });
      if (id !== "3") await vi.advanceTimersByTimeAsync(40);
    }

    await vi.advanceTimersByTimeAsync(99);
    expect(runtimeTasks).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(runtimeTasks).toHaveLength(1);

    await runtimeTasks[0]?.();
    expect(executed).toEqual([{ id: "3", burstIds: ["1", "2", "3"] }]);
    await coordinator.shutdown(false);
  });

  it("flushes an older burst before an immediate explicit turn", async () => {
    const runtimeTasks: Array<() => Promise<void>> = [];
    const order: string[] = [];
    const coordinator = new TurnIngressCoordinator<SampleTurn>(
      { quietWindowMs: 5_000, maxWaitMs: 10_000, maxMessages: 5, maxCharacters: 100 },
      (_scope, task) => { runtimeTasks.push(task); return true; }
    );

    coordinator.submit("channel", {
      id: "1",
      value: sample("1", "ordinary"),
      characters: 8,
      collect: true,
      execute: async () => {
        order.push("burst");
      }
    });
    coordinator.submit("channel", {
      id: "2",
      value: sample("2", "Ann, what do you think?"),
      characters: 23,
      collect: false,
      execute: async (burst) => {
        expect(burst).toBeNull();
        order.push("explicit");
      }
    });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(runtimeTasks).toHaveLength(2);
    await runtimeTasks[0]?.();
    await runtimeTasks[1]?.();
    expect(order).toEqual(["burst", "explicit"]);
    await coordinator.shutdown(false);
  });

  it("bypasses collection when the interaction preflight claims the turn", async () => {
    const runtimeTasks: Array<() => Promise<void>> = [];
    let prepareCalls = 0;
    let receivedBurst: unknown = "unset";
    const coordinator = new TurnIngressCoordinator<SampleTurn>(
      { quietWindowMs: 5_000, maxWaitMs: 10_000, maxMessages: 5, maxCharacters: 100 },
      (_scope, task) => { runtimeTasks.push(task); return true; }
    );

    coordinator.submit("channel", {
      id: "1",
      value: sample("1", "roast trigger"),
      characters: 13,
      collect: true,
      prepareCollection: async () => {
        prepareCalls += 1;
        return false;
      },
      execute: async (burst) => {
        receivedBurst = burst;
      }
    });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(prepareCalls).toBe(1);
    expect(runtimeTasks).toHaveLength(1);
    await runtimeTasks[0]?.();
    expect(receivedBurst).toBeNull();
    await coordinator.shutdown(false);
  });

  it("drains already accepted preflight work before shutdown", async () => {
    const runtimeTasks: Array<() => Promise<void>> = [];
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const coordinator = new TurnIngressCoordinator<SampleTurn>(
      { quietWindowMs: 5_000, maxWaitMs: 10_000, maxMessages: 5, maxCharacters: 100 },
      (_scope, task) => { runtimeTasks.push(task); return true; }
    );

    coordinator.submit("channel", {
      id: "1",
      value: sample("1", "ordinary"),
      characters: 8,
      collect: true,
      prepareCollection: async () => {
        await gate;
        return true;
      },
      execute: async () => undefined
    });

    const shuttingDown = coordinator.shutdown(true);
    release?.();
    await shuttingDown;
    expect(runtimeTasks).toHaveLength(1);
  });

  it("bounds preflight admission and expires stale work before Runtime", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const runtimeTasks: Array<() => Promise<void>> = [];
    const rejected: string[] = [];
    const coordinator = new TurnIngressCoordinator<SampleTurn>(
      { enabled: false },
      (_scope, task) => { runtimeTasks.push(task); return true; },
      undefined,
      { maxPending: 2, maxPendingPerScope: 2, maxPreflightAgeMs: 50 },
      (_scope, reason) => { rejected.push(reason); }
    );
    expect(coordinator.submit("channel", {
      id: "first", value: sample("first", "one"), characters: 3, collect: true,
      prepareCollection: async () => { await gate; return true; }, execute: async () => undefined
    })).toBe(true);
    expect(coordinator.submit("channel", {
      id: "second", value: sample("second", "two"), characters: 3, collect: false,
      execute: async () => undefined
    })).toBe(true);
    expect(coordinator.submit("channel", {
      id: "third", value: sample("third", "three"), characters: 5, collect: false,
      execute: async () => undefined
    })).toBe(false);
    await vi.advanceTimersByTimeAsync(51);
    release?.();
    await vi.runAllTimersAsync();
    expect(rejected).toEqual(["busy", "expired"]);
    // The first accepted item may already have reached Runtime; the stale queued
    // item did not add another task.
    expect(runtimeTasks).toHaveLength(1);
    await coordinator.shutdown(false);
  });

  it("rechecks expiry immediately before a delayed Runtime task executes", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    const runtimeTasks: Array<() => Promise<void>> = [];
    const rejected: string[] = [];
    let executed = false;
    const coordinator = new TurnIngressCoordinator<SampleTurn>(
      { enabled: false },
      (_scope, task) => {
        runtimeTasks.push(task);
        return true;
      },
      undefined,
      { maxPending: 2, maxPendingPerScope: 2, maxPreflightAgeMs: 50 },
      (_scope, reason) => rejected.push(reason)
    );
    coordinator.submit("channel", {
      id: "delayed-runtime",
      value: sample("delayed-runtime", "one"),
      characters: 3,
      collect: false,
      execute: async () => {
        executed = true;
      }
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(runtimeTasks).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(51);
    await runtimeTasks[0]?.();
    expect(executed).toBe(false);
    expect(rejected).toEqual(["expired"]);
    await coordinator.shutdown(false);
  });

  it("keeps collector-held bursts within the same global ingress bound", async () => {
    vi.useFakeTimers();
    const rejected: string[] = [];
    const coordinator = new TurnIngressCoordinator<SampleTurn>(
      { enabled: true, quietWindowMs: 1_000, maxWaitMs: 2_000 },
      () => true,
      undefined,
      { maxPending: 2, maxPendingPerScope: 2, maxPreflightAgeMs: 5_000 },
      (_scope, reason) => rejected.push(reason)
    );
    for (const id of ["first", "second"]) {
      expect(
        coordinator.submit(id, {
          id,
          value: sample(id, id),
          characters: id.length,
          collect: true,
          execute: async () => undefined
        })
      ).toBe(true);
    }
    await vi.advanceTimersByTimeAsync(0);
    expect(
      coordinator.submit("third", {
        id: "third",
        value: sample("third", "third"),
        characters: 5,
        collect: true,
        execute: async () => undefined
      })
    ).toBe(false);
    expect(rejected).toEqual(["busy"]);
    await coordinator.shutdown(false);
  });
});

describe("Turn collection policy", () => {
  const base = {
    collectorEnabled: true,
    smartParticipationEnabled: true,
    recovery: false,
    mentionedBot: false,
    hasReplyReference: false,
    explicitAudience: false,
    hasReadableText: true,
    customEmojiCount: 0,
    stickerCount: 0,
    attachmentCount: 0,
    visibleImageAttachmentCount: 0,
    embedCount: 0,
    hasUrl: false,
    smartCandidateCount: 2
  };

  it("collects only ordinary unresolved Smart Participation text", () => {
    expect(decideTurnCollection(base)).toEqual({ collect: true, reason: "collect" });
    expect(decideTurnCollection({ ...base, mentionedBot: true }).collect).toBe(false);
    expect(decideTurnCollection({ ...base, hasReplyReference: true }).collect).toBe(false);
    expect(decideTurnCollection({ ...base, explicitAudience: true }).collect).toBe(false);
    expect(decideTurnCollection({ ...base, attachmentCount: 1 }).reason).toBe("rich_content");
    expect(decideTurnCollection({ ...base, hasUrl: true }).reason).toBe("url_content");
    expect(decideTurnCollection({ ...base, recovery: true }).reason).toBe("recovery");
    expect(decideTurnCollection({ ...base, smartCandidateCount: 0 }).reason).toBe(
      "no_smart_candidates"
    );
  });

  it("builds stable bounded burst identity and analysis text", () => {
    const first = buildConversationBurstId(["message-1", "message-2", "message-2"]);
    const second = buildConversationBurstId(["message-1", "message-2"]);
    expect(first).toBe(second);
    expect(first).toHaveLength(40);
    expect(
      buildConversationBurstText([{ text: "  first   line " }, { text: " second line " }])
    ).toBe("first line\nsecond line");
    expect(buildConversationBurstText([{ text: "12345" }, { text: "67890" }], 6)).toBe(
      "\n67890"
    );
  });

  it("summarizes burst telemetry without copying message text", () => {
    const burst = {
      scopeKey: "channel",
      items: [sample("1", "private text"), sample("2", "more private text")],
      itemIds: ["message-1", "message-2"],
      totalCharacters: 29,
      openedAt: 1_000,
      flushedAt: 2_750,
      reason: "quiet_window" as const
    };

    expect(summarizeConversationBurst(burst, ["user-a", "user-b", "user-b"])).toEqual({
      burstId: buildConversationBurstId(["message-1", "message-2"]),
      flushReason: "quiet_window",
      messageCount: 2,
      authorCount: 2,
      totalCharacters: 29,
      openedAt: 1_000,
      flushedAt: 2_750,
      collectionLatencyMs: 1_750,
      collapsedMessageCount: 1,
      sourceMessageIds: ["message-1", "message-2"]
    });
  });
});

const basePolicy = {
  collectorEnabled: true,
  smartParticipationEnabled: true,
  recovery: false,
  mentionedBot: false,
  hasReplyReference: false,
  explicitAudience: false,
  hasReadableText: true,
  customEmojiCount: 0,
  stickerCount: 0,
  attachmentCount: 0,
  visibleImageAttachmentCount: 0,
  embedCount: 0,
  hasUrl: false,
  smartCandidateCount: 2
};

describe("visible-image Turn Collection policy", () => {
  it("collects a pure visible image attachment so following text can share one burst", () => {
    expect(
      decideTurnCollection({
        ...basePolicy,
        hasReadableText: false,
        attachmentCount: 1,
        visibleImageAttachmentCount: 1
      })
    ).toEqual({ collect: true, reason: "collect" });
  });

  it("still bypasses mixed or non-image attachments", () => {
    expect(
      decideTurnCollection({
        ...basePolicy,
        attachmentCount: 2,
        visibleImageAttachmentCount: 1
      })
    ).toEqual({ collect: false, reason: "rich_content" });
  });
});
