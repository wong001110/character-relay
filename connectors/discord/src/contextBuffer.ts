import type { DiscordContextMessage } from "./types.js";

/** Bounded room history. Returned values are snapshots, not shared mutable state. */
export class ContextBuffer {
  private readonly values = new Map<string, DiscordContextMessage[]>();

  constructor(private readonly maximumMessages: number) {}

  push(destinationKey: string, message: DiscordContextMessage): void {
    const current = this.values.get(destinationKey) ?? [];
    const stored = structuredClone(message);
    const index = current.findIndex((item) => item.message_id === message.message_id);
    if (index >= 0) {
      // Enrichment or a repeated Gateway event is not a new conversational turn.
      // Preserve the original position instead of moving an older source to the end.
      const updated = [...current];
      updated[index] = stored;
      this.values.set(destinationKey, updated);
      return;
    }
    this.values.set(destinationKey, [...current, stored].slice(-this.maximumMessages));
  }

  get(destinationKey: string): DiscordContextMessage[] {
    // A generation snapshot, renderer or caller must not mutate another role's history.
    return structuredClone(this.values.get(destinationKey) ?? []);
  }

  clear(destinationKey?: string): void {
    if (destinationKey) {
      this.values.delete(destinationKey);
      return;
    }
    this.values.clear();
  }
}
