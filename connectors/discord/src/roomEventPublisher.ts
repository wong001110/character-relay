/** Coalesce raw Gateway observations independently of model/tool work. No unbounded retries. */
import type { RoomEvidence, RoomLocation, RoomSource } from "./roomEvidence.js";

type Access = { readable: boolean; checkedAt: string };
type Pending = {
  location: RoomLocation;
  sources: Map<string, RoomSource>;
  access: () => Promise<Access>;
};

export class RoomEventPublisher {
  private readonly pending = new Map<string, Pending>();
  private readonly activeRooms = new Set<string>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private active = 0;
  private closing = false;
  private waiters: Array<() => void> = [];

  constructor(
    private readonly send: (evidence: RoomEvidence) => Promise<unknown>,
    private readonly onError: (error: unknown, room: string) => void,
    private readonly limits = { rooms: 64, messagesPerRoom: 64, concurrency: 2, coalesceMs: 100 }
  ) {
    if (Object.values(limits).some(value => !Number.isInteger(value) || value < 1)) {
      throw new Error("invalid_event_publisher_limits");
    }
  }

  publish(location: RoomLocation, source: RoomSource, access: () => Promise<Access>): boolean {
    if (this.closing) return false;
    if (source.channel_id !== location.channel_id || source.thread_id !== location.thread_id) {
      throw new Error("source_scope_mismatch");
    }
    const key = JSON.stringify([location.guild_id, location.channel_id, location.thread_id]);
    let room = this.pending.get(key);
    if (!room) {
      if (this.pending.size + this.activeRooms.size >= this.limits.rooms) {
        this.report(new Error("room_event_capacity"), key); return false;
      }
      room = { location, sources: new Map(), access };
      this.pending.set(key, room);
    }
    room.access = access;
    const previous = room.sources.get(source.message_id);
    if (previous?.deleted) return true; // Tombstones cannot be overwritten by a queued edit.
    if (!previous && room.sources.size >= this.limits.messagesPerRoom) {
      this.report(new Error("room_event_capacity"), key); return false;
    }
    if (previous && !source.deleted && (source.edited_at ?? source.created_at ?? "") <
        (previous.edited_at ?? previous.created_at ?? "")) return true;
    room.sources.set(source.message_id, source);
    if (!this.timer) this.timer = setTimeout(() => {
      this.timer = null; this.startAvailable();
    }, this.limits.coalesceMs);
    return true;
  }

  async stop(): Promise<void> {
    this.closing = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.startAvailable();
    if (!this.pending.size && !this.active) return;
    await new Promise<void>(resolve => this.waiters.push(resolve));
  }

  private report(error: unknown, key: string): void {
    try { this.onError(error, key); } catch { /* A lost diagnostic cannot change effects. */ }
  }

  private startAvailable(): void {
    while (this.active < this.limits.concurrency) {
      const item = [...this.pending.entries()].find(([key]) => !this.activeRooms.has(key));
      if (!item) break;
      const [key, room] = item;
      this.pending.delete(key); this.activeRooms.add(key); this.active += 1;
      void Promise.resolve().then(async () => {
        const access = await room.access();
        await this.send({ ...room.location, readable: access.readable,
          permission_checked_at: access.checkedAt,
          messages: access.readable ? [...room.sources.values()] : [] });
      }).catch(error => this.report(error, key)).finally(() => {
        this.active -= 1; this.activeRooms.delete(key);
        this.startAvailable();
        if (!this.active && !this.pending.size) {
          const waiters = this.waiters; this.waiters = [];
          for (const resolve of waiters) resolve();
        }
      });
    }
  }
}
