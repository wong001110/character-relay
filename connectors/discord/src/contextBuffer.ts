import type { DiscordContextMessage } from "./types.js";

/** A bounded room history. Readers receive immutable-by-copy snapshots. */
export class ContextBuffer {
  private readonly values = new Map<string, DiscordContextMessage[]>();
  private readonly deleted = new Map<string, Set<string>>();
  private readonly invalidated = new Map<string, Set<string>>();

  constructor(private readonly maximumMessages: number) {
    if (!Number.isSafeInteger(maximumMessages) || maximumMessages < 1) {
      throw new RangeError("Context capacity must be a positive integer.");
    }
  }

  push(destinationKey: string, message: DiscordContextMessage, freshSource = false): void {
    // A delayed queued turn/enrichment must not resurrect a deleted source.
    if (this.deleted.get(destinationKey)?.has(message.message_id)) return;
    if (this.invalidated.get(destinationKey)?.has(message.message_id)) {
      if (!freshSource) return;
      this.invalidated.get(destinationKey)?.delete(message.message_id);
    }
    const current = this.values.get(destinationKey) ?? [];
    const index = current.findIndex(item => item.message_id === message.message_id);
    const copy = structuredClone(message);
    if (index >= 0) {
      const previous = current[index]!;
      // An edit received at ingress wins over an older queued snapshot.
      if (previous.edited_at && (!copy.edited_at || previous.edited_at > copy.edited_at)) return;
      current[index] = copy;
    } else {
      const before = copy.created_at
        ? current.findIndex(item => item.created_at && item.created_at > copy.created_at!) : -1;
      if (before >= 0) current.splice(before, 0, copy);
      else current.push(copy);
    }
    this.values.set(destinationKey, current.slice(-this.maximumMessages));
  }

  remove(destinationKey: string, messageId: string): void {
    this.values.set(destinationKey,
      (this.values.get(destinationKey) ?? []).filter(item => item.message_id !== messageId));
    const tombstones = this.deleted.get(destinationKey) ?? new Set<string>();
    tombstones.add(messageId);
    while (tombstones.size > Math.max(1, this.maximumMessages * 2)) {
      tombstones.delete(tombstones.values().next().value!);
    }
    this.deleted.set(destinationKey, tombstones);
  }

  invalidate(destinationKey: string, messageId: string): void {
    this.values.set(destinationKey,
      (this.values.get(destinationKey) ?? []).filter(item => item.message_id !== messageId));
    const pending = this.invalidated.get(destinationKey) ?? new Set<string>();
    pending.add(messageId);
    while (pending.size > this.maximumMessages * 2) pending.delete(pending.values().next().value!);
    this.invalidated.set(destinationKey, pending);
  }

  wasDeleted(destinationKey: string, messageId: string): boolean {
    return this.deleted.get(destinationKey)?.has(messageId) ?? false;
  }

  get(destinationKey: string): DiscordContextMessage[] {
    return structuredClone(this.values.get(destinationKey) ?? []);
  }

  clear(destinationKey?: string): void {
    if (destinationKey !== undefined) {
      this.values.delete(destinationKey);
      this.deleted.delete(destinationKey);
      this.invalidated.delete(destinationKey);
      return;
    }
    this.values.clear();
    this.deleted.clear();
    this.invalidated.clear();
  }
}
