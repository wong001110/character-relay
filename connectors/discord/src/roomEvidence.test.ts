import { describe, expect, it, vi } from "vitest";
import { collectEvidence, sourceContext, type RoomLocation, type RoomSource } from "./roomEvidence.js";

const room: RoomLocation = { guild_id: "g", channel_id: "c", thread_id: "", category_id: "" };
function source(id: string, updates: Partial<RoomSource> = {}): RoomSource {
  return { message_id: id, channel_id: "c", thread_id: "", author_id: "alice",
    author_display_name: "Alice", author_is_bot: false, author_deployment_id: "",
    text: id, reply_to_message_id: "", created_at: "2026-10-01T00:00:00Z",
    edited_at: null, deleted: false, content_available: true, has_unseen_media: false, ...updates };
}
const base = { room, readable: true, checkedAt: "2026-10-01T00:00:01Z" };

describe("room evidence boundaries", () => {
  it("preserves primary and ancestors despite an interleaved recent burst", async () => {
    const result = await collectEvidence({ ...base, trigger: source("primary", { reply_to_message_id: "parent" }),
      recent: Array.from({length: 40}, (_, index) => source(`new-${index}`)),
      fetchSameRoom: async id => source(id) });
    expect(result.messages.map(item => item.message_id)).toContain("primary");
    expect(result.messages.map(item => item.message_id)).toContain("parent");
    expect(result.messages).toHaveLength(26);
  });
  it("never relabels private ancestors as public room content", async () => {
    await expect(collectEvidence({ ...base,
      trigger: source("m", { reply_to_message_id: "private" }), recent: [],
      fetchSameRoom: async id => source(id, {thread_id: "private-thread"})
    })).rejects.toThrow("ancestor_scope_mismatch");
  });
  it("doesn't fetch at all when permission is absent", async () => {
    const fetchSameRoom = vi.fn();
    const result = await collectEvidence({ ...base, readable: false, trigger: source("m"),
      recent: [source("secret")], fetchSameRoom });
    expect(result.messages).toEqual([]);
    expect(fetchSameRoom).not.toHaveBeenCalled();
  });
  it("bounds Reply cycles and keeps missing sources missing", async () => {
    const fetchSameRoom = vi.fn(async id => source(id, {reply_to_message_id: "m"}));
    const result = await collectEvidence({ ...base, trigger: source("m", {reply_to_message_id: "p"}),
      recent: [], fetchSameRoom });
    expect(result.messages).toHaveLength(2);
    expect(fetchSameRoom).toHaveBeenCalledTimes(1);
    const missing = await collectEvidence({ ...base, trigger: source("m", {reply_to_message_id: "p"}),
      recent: [], fetchSameRoom: async () => null });
    expect(missing.messages).toHaveLength(1);
    expect(missing.messages[0]?.reply_to_message_id).toBe("p");
  });
  it("never substitutes another ID returned by a fetcher", async () => {
    await expect(collectEvidence({ ...base, trigger: source("m", {reply_to_message_id: "p"}),
      recent: [], fetchSameRoom: async () => source("someone-else")
    })).rejects.toThrow("ancestor_scope_mismatch");
  });
  it("keeps raw source origin and edit metadata in the bounded context", () => {
    const result = sourceContext(source("m", { thread_id: "thread", edited_at: "2026-10-01T00:00:03Z" }));
    expect(result.thread_id).toBe("thread");
    expect(result.channel_id).toBe("c");
    expect(result.edited_at).toBe("2026-10-01T00:00:03Z");
  });
});


describe("delivered-source identity", () => {
  it("does not fall back when the delivered source was deleted or denied", async () => {
    const { fetchDeliveredSource } = await import("./roomEvidence.js");
    const trigger={id:"human",channelId:"room"};
    expect(await fetchDeliveredSource(trigger,"bot",async()=>null)).toBeNull();
    expect(await fetchDeliveredSource(trigger,"bot",async()=>{throw new Error("403")})).toBeNull();
    expect(await fetchDeliveredSource(trigger,"bot",async()=>({id:"bot",channelId:"private"}))).toBeNull();
    expect(await fetchDeliveredSource(trigger,"bot",async()=>({id:"another",channelId:"room"}))).toBeNull();
    expect(await fetchDeliveredSource(trigger,"bot",async()=>({id:"bot",channelId:"room"}))).toEqual({id:"bot",channelId:"room"});
  });
});
