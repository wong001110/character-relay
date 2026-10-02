import { describe,expect,it,vi } from "vitest";
import { currentDraftEvidence,type DraftEvidencePort } from "./draftPreflight.js";
import type { RoomSource } from "./roomEvidence.js";
import type { DiscordReply } from "./types.js";

const room = { guild_id: "g", channel_id: "room", thread_id: "", category_id: "" };
const source = (id: string, changes: Partial<RoomSource> = {}): RoomSource => ({
  message_id: id, channel_id: "room", thread_id: "", author_id: "alice", author_display_name: "Alice",
  author_is_bot: false, author_deployment_id: "", text: "Question", reply_to_message_id: "",
  created_at: "2026-10-01T00:00:00Z", edited_at: null, deleted: false, content_available: true,
  has_unseen_media: false, ...changes
});
const reply = { context_trace: { source_target_message_id: "target", source_revisions: { target: 1, old: 1 } } } as unknown as DiscordReply;
const access = { readable: true, writable: true, checkedAt: "2026-10-01T00:00:01Z" };
const port = (changes: Partial<DraftEvidencePort> = {}): DraftEvidencePort => ({
  checkAccess: vi.fn(async () => access), read: vi.fn(async id => source(id)),
  recent: vi.fn(async () => [source("new", {author_id: "bob"})]), ...changes
});

describe("draft source preflight", () => {
  it("reads the actual selected source and old inputs, not cached trigger prose", async () => {
    const io = port();
    const result = await currentDraftEvidence(room, reply, io);
    expect(result.messages.map(s => s.message_id).sort()).toEqual(["new", "old", "target"]);
    expect(io.read).toHaveBeenCalledWith("target");
    expect(io.read).toHaveBeenCalledWith("old");
    expect(io.checkAccess).toHaveBeenCalledTimes(2);
  });
  it("returns explicit tombstones for deleted inputs", async () => {
    const result = await currentDraftEvidence(room, reply, port({read: vi.fn(async () => null)}));
    expect(result.messages.find(s => s.message_id === "target")).toMatchObject({deleted: true, text: ""});
    expect(result.messages.find(s => s.message_id === "old")).toMatchObject({deleted: true, text: ""});
  });
  it("doesn't fetch private data without access and discards data on mid-read revocation", async () => {
    const io = port({checkAccess: vi.fn(async () => ({...access, readable: false}))});
    expect((await currentDraftEvidence(room, reply, io)).messages).toEqual([]);
    expect(io.read).not.toHaveBeenCalled();
    let calls = 0;
    const revoked = port({checkAccess: vi.fn(async () => ({...access, readable: ++calls < 2}))});
    const result = await currentDraftEvidence(room, reply, revoked);
    expect(result.messages).toEqual([]);
    expect(result.writable).toBe(false);
  });
  it("never treats an access or network error as proof of deletion", async () => {
    const io = port({read: vi.fn(async () => {throw new Error("access_denied");})});
    await expect(currentDraftEvidence(room, reply, io)).rejects.toThrow("access_denied");
  });
  it("rejects substituted IDs and private ancestors", async () => {
    await expect(currentDraftEvidence(room, reply, port({
      read: vi.fn(async id => source(id, id === "old" ? {thread_id: "secret"} : {}))
    }))).rejects.toThrow("draft_source_scope_mismatch");
  });
  it("requires a server source binding, even for apparently harmless text", async () => {
    await expect(currentDraftEvidence(room, {} as DiscordReply, port())).rejects.toThrow("draft_source_binding_missing");
  });
});
