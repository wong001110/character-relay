import type { DiscordContextMessage } from "./types.js";

export class ContextBuffer {
  private readonly values = new Map<string, DiscordContextMessage[]>();

  constructor(private readonly maximumMessages: number) {}

  push(destinationKey: string, message: DiscordContextMessage): void {
    const current = this.values.get(destinationKey) ?? [];
    const deduplicated = current.filter((item) => item.message_id !== message.message_id);
    deduplicated.push(message);
    this.values.set(destinationKey, deduplicated.slice(-this.maximumMessages));
  }

  get(destinationKey: string): DiscordContextMessage[] {
    return [...(this.values.get(destinationKey) ?? [])];
  }

  clear(destinationKey?: string): void {
    if (destinationKey) {
      this.values.delete(destinationKey);
      return;
    }
    this.values.clear();
  }
}
