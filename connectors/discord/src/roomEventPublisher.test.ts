import { describe,expect,it } from "vitest";
import { RoomEventPublisher } from "./roomEventPublisher.js";
import type { RoomEvidence,RoomSource } from "./roomEvidence.js";
const location = { guild_id: "guild", channel_id: "room", thread_id: "", category_id: "" };
const access = async () => ({ readable: true, checkedAt: new Date().toISOString() });
const source = (id: string, changes: Partial<RoomSource> = {}): RoomSource => ({
  message_id: id, channel_id: "room", thread_id: "", author_id: "alice", author_display_name: "Alice",
  author_is_bot: false, author_deployment_id: "", text: "hello", reply_to_message_id: "",
  created_at: "2026-10-01T00:00:00Z", edited_at: null, deleted: false,
  content_available: true, has_unseen_media: false, ...changes
});

describe("raw source publication", () => {
  it("coalesces edits, then a tombstone, without resurrecting content", async () => {
    const sent: RoomEvidence[] = [];
    const publisher = new RoomEventPublisher(async value => { sent.push(value); }, () => undefined);
    publisher.publish(location, source("one"), access);
    publisher.publish(location, source("one", { text: "correction", edited_at: "2026-10-01T00:01:00Z" }), access);
    publisher.publish(location, source("one", { text: "", deleted: true }), access);
    publisher.publish(location, source("one", { text: "late edit", edited_at: "2026-10-01T00:02:00Z" }), access);
    await publisher.stop();
    expect(sent).toHaveLength(1);
    expect(sent[0]!.messages).toEqual([source("one", { text: "", deleted: true })]);
  });
  it("rechecks access at flush; denied access never serializes cached text", async () => {
    const sent: RoomEvidence[] = [];
    let readable = true;
    const publisher = new RoomEventPublisher(async value => { sent.push(value); }, () => undefined);
    publisher.publish(location, source("one"), async () => ({ readable, checkedAt: new Date().toISOString() }));
    readable = false;
    await publisher.stop();
    expect(sent[0]!.readable).toBe(false); expect(sent[0]!.messages).toEqual([]);
  });
  it("capacity loss is reported, and failed publication doesn't loop or hold shutdown", async () => {
    const errors: unknown[] = []; let calls = 0;
    const publisher = new RoomEventPublisher(async () => { calls += 1; throw new Error("unavailable"); }, error => { errors.push(error); }, { rooms: 2, messagesPerRoom: 1, concurrency: 1, coalesceMs: 100 });
    expect(publisher.publish(location, source("one"), access)).toBe(true);
    expect(publisher.publish(location, source("two"), access)).toBe(false);
    await publisher.stop();
    expect(calls).toBe(1); expect(errors).toHaveLength(2);
    expect(publisher.publish(location, source("three"), access)).toBe(false);
  });
});
