import { afterEach, describe, expect, it, vi } from "vitest";

import { TurnCollector, type ConversationBurst } from "./turnCollector.js";

interface SampleTurn {
  id: string;
  text: string;
}

function sample(id: string, text: string): SampleTurn {
  return { id, text };
}

describe("TurnCollector", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("collects rapid fragments and flushes once after the quiet window", async () => {
    vi.useFakeTimers();
    const bursts: ConversationBurst<SampleTurn>[] = [];
    const collector = new TurnCollector<SampleTurn>(
      { quietWindowMs: 1_500, maxWaitMs: 4_000, maxMessages: 5, maxCharacters: 1_500 },
      (burst) => {
        bursts.push(burst);
      }
    );

    collector.add("channel", { id: "1", value: sample("1", "我觉得"), characters: 3 });
    await vi.advanceTimersByTimeAsync(600);
    collector.add("channel", { id: "2", value: sample("2", "刚才那张图"), characters: 5 });
    await vi.advanceTimersByTimeAsync(800);
    collector.add("channel", { id: "3", value: sample("3", "其实蛮好笑的"), characters: 6 });

    await vi.advanceTimersByTimeAsync(1_499);
    expect(bursts).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);

    expect(bursts).toHaveLength(1);
    expect(bursts[0]?.itemIds).toEqual(["1", "2", "3"]);
    expect(bursts[0]?.reason).toBe("quiet_window");
    expect(collector.pendingScopeCount).toBe(0);
  });

  it("flushes at max wait even when messages keep arriving", async () => {
    vi.useFakeTimers();
    const bursts: ConversationBurst<SampleTurn>[] = [];
    const collector = new TurnCollector<SampleTurn>(
      { quietWindowMs: 1_500, maxWaitMs: 4_000, maxMessages: 20, maxCharacters: 10_000 },
      (burst) => {
        bursts.push(burst);
      }
    );

    collector.add("channel", { id: "1", value: sample("1", "a"), characters: 1 });
    for (let index = 2; index <= 4; index += 1) {
      await vi.advanceTimersByTimeAsync(1_000);
      collector.add("channel", {
        id: String(index),
        value: sample(String(index), "a"),
        characters: 1
      });
    }
    await vi.advanceTimersByTimeAsync(1_000);

    expect(bursts).toHaveLength(1);
    expect(bursts[0]?.itemIds).toEqual(["1", "2", "3", "4"]);
    expect(bursts[0]?.reason).toBe("max_wait");
  });

  it("flushes immediately when the message or character bound is reached", async () => {
    const reasons: string[] = [];
    const messageBound = new TurnCollector<SampleTurn>(
      { quietWindowMs: 5_000, maxWaitMs: 10_000, maxMessages: 2, maxCharacters: 100 },
      (burst) => {
        reasons.push(burst.reason);
      }
    );
    messageBound.add("message-bound", {
      id: "1",
      value: sample("1", "one"),
      characters: 3
    });
    messageBound.add("message-bound", {
      id: "2",
      value: sample("2", "two"),
      characters: 3
    });

    const characterBound = new TurnCollector<SampleTurn>(
      { quietWindowMs: 5_000, maxWaitMs: 10_000, maxMessages: 10, maxCharacters: 5 },
      (burst) => {
        reasons.push(burst.reason);
      }
    );
    characterBound.add("character-bound", {
      id: "3",
      value: sample("3", "12345"),
      characters: 5
    });

    await Promise.resolve();
    expect(reasons).toEqual(["max_messages", "max_characters"]);
    await messageBound.shutdown();
    await characterBound.shutdown();
  });

  it("supports an explicit flush without losing ordering", async () => {
    const bursts: ConversationBurst<SampleTurn>[] = [];
    const collector = new TurnCollector<SampleTurn>(
      { quietWindowMs: 5_000, maxWaitMs: 10_000, maxMessages: 5, maxCharacters: 100 },
      (burst) => {
        bursts.push(burst);
      }
    );
    collector.add("channel", { id: "1", value: sample("1", "first"), characters: 5 });
    collector.add("channel", { id: "2", value: sample("2", "second"), characters: 6 });

    expect(await collector.flush("channel", "explicit_flush")).toBe(true);
    expect(bursts[0]?.itemIds).toEqual(["1", "2"]);
    expect(bursts[0]?.reason).toBe("explicit_flush");
    expect(await collector.flush("channel", "explicit_flush")).toBe(false);
  });

  it("deduplicates the same source message inside one pending burst", async () => {
    const bursts: ConversationBurst<SampleTurn>[] = [];
    const collector = new TurnCollector<SampleTurn>(
      { quietWindowMs: 5_000, maxWaitMs: 10_000, maxMessages: 5, maxCharacters: 100 },
      (burst) => {
        bursts.push(burst);
      }
    );
    const value = sample("1", "hello");
    collector.add("channel", { id: "1", value, characters: 5 });
    collector.add("channel", { id: "1", value, characters: 5 });

    await collector.flush("channel");
    expect(bursts[0]?.itemIds).toEqual(["1"]);
    expect(bursts[0]?.totalCharacters).toBe(5);
  });
});

describe("TurnCollector live reconfiguration", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps an open burst on its original config snapshot after reconfigure", async () => {
    vi.useFakeTimers();
    const bursts: ConversationBurst<SampleTurn>[] = [];
    const collector = new TurnCollector<SampleTurn>(
      { quietWindowMs: 3_000, maxWaitMs: 10_000, maxMessages: 5, maxCharacters: 1_500 },
      (burst) => {
        bursts.push(burst);
      }
    );

    collector.add("channel", { id: "old", value: sample("old", "old"), characters: 3 });
    collector.reconfigure({ quietWindowMs: 5_000, maxWaitMs: 15_000 });

    expect(collector.currentConfig.quietWindowMs).toBe(5_000);
    await vi.advanceTimersByTimeAsync(2_999);
    expect(bursts).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(bursts.map((item) => item.itemIds)).toEqual([["old"]]);

    collector.add("channel", { id: "new", value: sample("new", "new"), characters: 3 });
    await vi.advanceTimersByTimeAsync(4_999);
    expect(bursts).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(bursts.map((item) => item.itemIds)).toEqual([["old"], ["new"]]);
  });
});
