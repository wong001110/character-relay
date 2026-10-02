import { describe,expect,it } from "vitest";
import { RoomPublicationLock,RoomWorkQueue } from "./roomWorkQueue.js";

const tick = () => new Promise<void>(resolve => setTimeout(resolve, 0));
function deferred(): { promise: Promise<void>; release: () => void } {
  let release!: () => void;
  const promise = new Promise<void>(resolve => { release = resolve; });
  return { promise, release };
}

describe("room work scheduling", () => {
  it("a slow tool job doesn't block an unrelated direct reply in the same room", async () => {
    const queue = new RoomWorkQueue({ maximumPending: 10, maximumPerRoom: 5, concurrency: 3, concurrencyPerRoom: 2 }, () => undefined);
    const slow = deferred(); const completed: string[] = [];
    queue.enqueue("room", async () => { await slow.promise; completed.push("slow"); });
    queue.enqueue("room", async () => { completed.push("direct"); });
    await tick();
    expect(completed).toEqual(["direct"]);
    slow.release(); await queue.drain();
    expect(completed).toEqual(["direct", "slow"]);
    expect(queue.pending).toBe(0);
    expect(queue.pendingFor("room")).toBe(0);
  });

  it("skips a saturated room without bypassing room/global pending limits", async () => {
    const queue = new RoomWorkQueue({ maximumPending: 4, maximumPerRoom: 3, concurrency: 2, concurrencyPerRoom: 1 }, () => undefined);
    const slow = deferred(); const started: string[] = [];
    queue.enqueue("a", () => slow.promise);
    queue.enqueue("a", async () => { started.push("a2"); });
    queue.enqueue("a", async () => { started.push("a3"); });
    expect(queue.enqueue("a", async () => undefined)).toBe(false);
    expect(queue.enqueue("b", async () => { started.push("b"); })).toBe(true);
    expect(queue.enqueue("c", async () => undefined)).toBe(false);
    await tick(); expect(started).toEqual(["b"]);
    slow.release(); await queue.drain();
    expect(started).toEqual(["b", "a2", "a3"]);
  });

  it("contains failed work and failed diagnostics without leaking capacity", async () => {
    const failures: unknown[] = [];
    const queue = new RoomWorkQueue({ maximumPending: 5, maximumPerRoom: 5, concurrency: 1, concurrencyPerRoom: 1 }, error => { failures.push(error); throw new Error("diagnostics failed"); });
    queue.enqueue("a", async () => { throw new Error("tool failed"); });
    let next = false;
    queue.enqueue("a", async () => { next = true; });
    await queue.drain();
    expect(next).toBe(true); expect(failures).toHaveLength(1);
    expect(queue.pending).toBe(0);
  });

  it("serializes a room's publication but allows other rooms; release is idempotent", async () => {
    const lock = new RoomPublicationLock();
    const release = await lock.acquire("a");
    let entered = false;
    const later = lock.acquire("a").then(done => { entered = true; done(); });
    const otherRelease = await lock.acquire("b"); otherRelease();
    await tick(); expect(entered).toBe(false);
    release(); release(); await later;
    expect(entered).toBe(true);
    const final = await lock.acquire("a"); final();
  });
});
