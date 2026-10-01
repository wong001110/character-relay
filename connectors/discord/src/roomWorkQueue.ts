/** Bounded work concurrency, with publication serialized separately from slow generation. */
type Work = { room: string; run: () => Promise<void> };

export class RoomWorkQueue {
  private readonly waiting: Work[] = [];
  private readonly roomPending = new Map<string, number>();
  private readonly roomActive = new Map<string, number>();
  private active = 0;
  private drainWaiters: Array<() => void> = [];

  constructor(
    private readonly limits: {
      maximumPending: number; maximumPerRoom: number;
      concurrency: number; concurrencyPerRoom: number;
    },
    private readonly onError: (error: unknown, room: string) => void
  ) {
    for (const value of Object.values(limits)) {
      if (!Number.isInteger(value) || value < 1) throw new Error("invalid_work_queue_limits");
    }
    if (limits.concurrencyPerRoom > limits.concurrency) throw new Error("invalid_room_concurrency");
  }

  get pending(): number { return this.active + this.waiting.length; }
  pendingFor(room: string): number { return this.roomPending.get(room) ?? 0; }

  enqueue(room: string, run: () => Promise<void>): boolean {
    if (this.pending >= this.limits.maximumPending ||
        this.pendingFor(room) >= this.limits.maximumPerRoom) return false;
    this.waiting.push({ room, run });
    this.roomPending.set(room, this.pendingFor(room) + 1);
    this.startAvailable();
    return true;
  }

  async drain(): Promise<void> {
    if (!this.pending) return;
    await new Promise<void>(resolve => this.drainWaiters.push(resolve));
  }

  private startAvailable(): void {
    while (this.active < this.limits.concurrency) {
      // Oldest eligible work wins. A busy room cannot block other rooms' free slots.
      const index = this.waiting.findIndex(item =>
        (this.roomActive.get(item.room) ?? 0) < this.limits.concurrencyPerRoom);
      if (index < 0) break;
      const item = this.waiting.splice(index, 1)[0]!;
      this.active += 1;
      this.roomActive.set(item.room, (this.roomActive.get(item.room) ?? 0) + 1);
      void Promise.resolve().then(item.run).catch(error => {
        try { this.onError(error, item.room); } catch { /* Diagnostics do not poison the queue. */ }
      }).finally(() => {
        this.active -= 1;
        this.reduce(this.roomActive, item.room);
        this.reduce(this.roomPending, item.room);
        this.startAvailable();
        if (!this.pending) {
          const waiters = this.drainWaiters;
          this.drainWaiters = [];
          for (const resolve of waiters) resolve();
        }
      });
    }
  }

  private reduce(map: Map<string, number>, key: string): void {
    const next = (map.get(key) ?? 1) - 1;
    if (next > 0) map.set(key, next); else map.delete(key);
  }
}

export class RoomPublicationLock {
  private readonly tails = new Map<string, Promise<void>>();

  async acquire(room: string): Promise<() => void> {
    const prior = this.tails.get(room) ?? Promise.resolve();
    let release!: () => void;
    const current = new Promise<void>(resolve => { release = resolve; });
    this.tails.set(room, current);
    await prior;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      release();
      if (this.tails.get(room) === current) this.tails.delete(room);
    };
  }
}
