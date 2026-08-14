import { afterEach, describe, expect, it, vi } from "vitest";

import {
  TurnIngressCoordinator,
  buildConversationBurstId,
  buildConversationBurstText,
  decideTurnCollection
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
      (_scope, task) => runtimeTasks.push(task)
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
      (_scope, task) => runtimeTasks.push(task)
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
      (_scope, task) => runtimeTasks.push(task)
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
      (_scope, task) => runtimeTasks.push(task)
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
});