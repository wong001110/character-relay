import { afterEach, describe, expect, it, vi } from "vitest";

import { RecoveryLoop } from "./recoveryLoop.js";

describe("RecoveryLoop", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("retries after an initial failure and later succeeds", async () => {
    vi.useFakeTimers();
    let attempts = 0;
    let successes = 0;
    let failures = 0;

    const loop = new RecoveryLoop(1_000, {
      execute: async () => {
        attempts += 1;
        if (attempts === 1) throw new Error("API is still starting");
      },
      succeeded: () => {
        successes += 1;
      },
      failed: () => {
        failures += 1;
      }
    });

    loop.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(attempts).toBe(1);
    expect(failures).toBe(1);
    expect(successes).toBe(0);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(attempts).toBe(2);
    expect(failures).toBe(1);
    expect(successes).toBe(1);

    loop.stop();
  });

  it("does not overlap executions", async () => {
    let release: (() => void) | undefined;
    let attempts = 0;
    const blocked = new Promise<void>((resolve) => {
      release = resolve;
    });

    const loop = new RecoveryLoop(1_000, {
      execute: async () => {
        attempts += 1;
        await blocked;
      },
      succeeded: () => undefined,
      failed: () => undefined
    });

    const first = loop.runNow();
    await loop.runNow();
    expect(attempts).toBe(1);

    release?.();
    await first;
  });
});
