import { afterEach, describe, expect, it, vi } from "vitest";
import { RoomRequestError } from "./roomHttp";
import { webRoomApi, unmatchedOutbox, type WebMessage, type WebOutbox, type WebProfile, type WebRoom, type WebSnapshot, type WebUpload } from "./webRoomApi";
import { WebRoomSession } from "./webRoomSession";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function room(id = "room-a", changes: Partial<WebRoom> = {}): WebRoom {
  return { id, name: id, connection_id: "connection", guild_id: "guild", channel_id: "channel", thread_id: "", enabled: true, can_manage: false, can_post: true, ...changes };
}
const profile: WebProfile = { id: "owned-profile", display_name: "Dots", avatar_url: "", version: 1 };
function message(id: string, changes: Partial<WebMessage> = {}): WebMessage {
  return { id, author_id: "discord-author", display_name: "Alice", avatar_url: "", actor_type: "discord_user", text: id, deleted: false, content_available: true, created_at: "2026-10-04T01:00:00Z", edited_at: null, reply_to_message_id: "", reply_preview: null, attachments: [], custom_emojis: [], stickers: [], mentions: [], embeds: [], poll: null, reactions: [], pinned: false, ...changes };
}
function receipt(changes: Partial<WebOutbox> = {}): WebOutbox {
  return { id: "receipt", client_message_id: "client-id", profile_id: profile.id, display_name: profile.display_name, avatar_url: "", text: "Hello", reply_to_message_id: "", sticker_resource_key: "", attachments: [], status: "pending", discord_message_id: "", reason: "", created_at: "2026-10-04T01:00:00Z", routing_status: "", ...changes };
}
function snapshot(ids: string[] = ["m1"], roomId = "room-a", outbox: WebOutbox[] = []): WebSnapshot {
  return { room_id: roomId, messages: ids.map(id => message(id)), outbox, history_limit: 64 };
}

class FakeStream {
  close = vi.fn();
  onerror: EventSource["onerror"] = null;
  private handlers = new Map<string, EventListenerOrEventListenerObject[]>();
  constructor(readonly url: string) {}
  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this.handlers.set(type, [...this.handlers.get(type) ?? [], listener]);
  }
  emit(type: string, data: unknown = {}) {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>;
    for (const listener of this.handlers.get(type) ?? []) {
      if (typeof listener === "function") listener(event);
      else listener.handleEvent(event);
    }
  }
  fail() { this.onerror?.call(this as unknown as EventSource, new Event("error")); }
}

const sessions: WebRoomSession[] = [];
function harness() {
  const api = {
    ...webRoomApi,
    rooms: vi.fn(async () => [room(), room("room-b")]),
    profiles: vi.fn(async () => [profile]),
    send: vi.fn(async (_room: string, payload: Parameters<typeof webRoomApi.send>[1]) => receipt({ client_message_id: payload.client_message_id })),
    uploadAttachment: vi.fn(async (): Promise<WebUpload> => ({ id: "upload", filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 3 }))
  };
  const streams: FakeStream[] = [];
  const createStream = vi.fn((url: string) => {
    const stream = new FakeStream(url);
    streams.push(stream);
    return stream as unknown as EventSource;
  });
  const session = new WebRoomSession(api, createStream);
  sessions.push(session);
  session.configure("account-a", false);
  async function connected() {
    await session.ensureLoaded();
    session.selectRoom("room-a");
    streams.at(-1)!.emit("snapshot", snapshot());
  }
  return { session, api, streams, createStream, connected };
}

afterEach(() => {
  for (const session of sessions.splice(0)) session.dispose();
  vi.restoreAllMocks();
});

describe("one Web Room session across presentations", () => {
  it("shares the exact snapshot and one stream while consumers mount, leave routes, and close", async () => {
    const h = harness();
    await h.connected();
    const full = vi.fn();
    const companion = vi.fn();
    const leaveFull = h.session.subscribe(full);
    const closeCompanion = h.session.subscribe(companion);
    const before = h.session.getSnapshot();
    expect(h.session.getSnapshot()).toBe(before);
    h.streams[0].emit("snapshot", snapshot(["m1", "m2"]));
    expect(full).toHaveBeenCalledOnce();
    expect(companion).toHaveBeenCalledOnce();
    leaveFull();
    closeCompanion();
    h.streams[0].emit("snapshot", snapshot(["m1", "m2", "m3"]));
    expect(h.session.getSnapshot().snapshot.messages.at(-1)?.id).toBe("m3");
    expect(h.createStream).toHaveBeenCalledOnce();
    expect(h.streams[0].url).toBe("/api/web-chat/rooms/room-a/events");
    expect(h.streams[0].close).not.toHaveBeenCalled();
    expect(full).toHaveBeenCalledOnce();
    expect(companion).toHaveBeenCalledOnce();
  });

  it("coalesces initial loading by simultaneous presentations", async () => {
    const h = harness();
    const loadedRooms = deferred<WebRoom[]>();
    h.api.rooms.mockReturnValueOnce(loadedRooms.promise);
    const full = h.session.ensureLoaded();
    const companion = h.session.ensureLoaded();
    expect(h.api.rooms).toHaveBeenCalledOnce();
    expect(h.api.profiles).toHaveBeenCalledOnce();
    loadedRooms.resolve([room()]);
    await Promise.all([full, companion]);
    await h.session.ensureLoaded();
    expect(h.api.rooms).toHaveBeenCalledOnce();
  });

  it("refreshes permissions without clearing the same transcript or opening another stream", async () => {
    const h = harness();
    await h.connected();
    const before = h.session.getSnapshot().snapshot;
    h.api.rooms.mockResolvedValueOnce([room("room-a", { can_post: false })]);
    await h.session.refresh();
    expect(h.session.getSnapshot().snapshot).toBe(before);
    expect(h.createStream).toHaveBeenCalledOnce();
    h.session.patch({ text: "Unauthorized" });
    await h.session.send();
    expect(h.api.send).not.toHaveBeenCalled();
  });

  it("keeps REST send available through normal SSE rollover", async () => {
    const h = harness();
    await h.connected();
    const before = h.session.getSnapshot().snapshot;
    h.streams[0].fail();
    expect(h.session.getSnapshot().connection).toBe("reconnecting");
    expect(h.session.getSnapshot().snapshot).toBe(before);
    h.session.patch({ text: "Send during rollover" });
    await h.session.send();
    expect(h.api.send).toHaveBeenCalledOnce();
    expect(h.createStream).toHaveBeenCalledOnce();
    expect(h.streams[0].close).not.toHaveBeenCalled();
  });

  it("preserves the last transcript on a server-side snapshot availability failure", async () => {
    const h = harness();
    await h.connected();
    const before = h.session.getSnapshot().snapshot;
    h.streams[0].emit("unavailable");
    expect(h.session.getSnapshot().snapshot).toBe(before);
    expect(h.session.getSnapshot().connection).toBe("unavailable");
    expect(h.streams[0].close).toHaveBeenCalledOnce();
    h.session.patch({ text: "Blocked" });
    await h.session.send();
    expect(h.api.send).not.toHaveBeenCalled();
  });

  it("clears unsafe snapshots and rejects events from an old room stream", async () => {
    const h = harness();
    await h.connected();
    h.session.selectRoom("room-b");
    h.streams[0].emit("snapshot", snapshot(["private-old"]));
    expect(h.session.getSnapshot().snapshot.messages).toEqual([]);
    h.streams[1].emit("snapshot", snapshot(["b1"], "room-b"));
    h.streams[1].emit("snapshot", snapshot(["wrong-room"], "room-a"));
    expect(h.session.getSnapshot().snapshot.messages).toEqual([]);
    expect(h.session.getSnapshot().connection).toBe("unavailable");
    expect(h.session.getSnapshot().error).toBe("invalid_room_snapshot");
    expect(h.streams[0].close).toHaveBeenCalledOnce();
  });

  it("rejects old stream callbacks after a same-room reconnect", async () => {
    const h = harness();
    await h.connected();
    h.session.reconnect();
    h.streams[1].emit("snapshot", snapshot(["current"]));
    h.streams[0].emit("snapshot", snapshot(["stale"]));
    h.streams[0].emit("revoked", { reason: "session_revoked" });
    expect(h.session.getSnapshot().snapshot.messages.map(item => item.id)).toEqual(["current"]);
    expect(h.session.getSnapshot().authenticated).toBe(true);
    expect(h.session.getSnapshot().roomId).toBe("room-a");
    expect(h.session.getSnapshot().connection).toBe("connected");
  });
});

describe("shared sends and delivery receipts", () => {
  it("synchronously locks two surfaces to one logical POST", async () => {
    const h = harness();
    await h.connected();
    const accepted = deferred<WebOutbox>();
    h.api.send.mockReturnValueOnce(accepted.promise);
    h.session.patch({ text: "One message" });
    const fullSend = h.session.send();
    const companionSend = h.session.send();
    expect(h.api.send).toHaveBeenCalledOnce();
    expect(h.session.getSnapshot().busy).toBe(true);
    const payload = h.api.send.mock.calls[0][1];
    expect(payload.client_message_id).toMatch(/^[0-9a-f-]{36}$/u);
    expect(payload.profile_id).toBe(profile.id);
    accepted.resolve(receipt({ client_message_id: payload.client_message_id }));
    await Promise.all([fullSend, companionSend]);
    expect(h.session.getSnapshot().busy).toBe(false);
    expect(h.session.getSnapshot().localSubmission).toBeNull();
  });

  it("retains an unknown payload and only explicitly retries the same client ID and body", async () => {
    const h = harness();
    await h.connected();
    h.api.send.mockRejectedValueOnce(new Error("timeout"));
    h.session.patch({ text: "Original", reply: "m1", stickerResourceKey: "sticker:one", attachments: [{ id: "private-upload", filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 3 }] });
    await h.session.send();
    const payload = h.api.send.mock.calls[0][1];
    expect(h.session.getSnapshot().localSubmission?.phase).toBe("unknown");
    expect(h.session.getSnapshot().text).toBe("Original");
    h.streams[0].fail();
    await h.session.send();
    expect(h.api.send).toHaveBeenCalledOnce();
    h.session.patch({ text: "Changed draft", reply: "", attachments: [], stickerResourceKey: "" });
    await h.session.retry();
    expect(h.api.send).toHaveBeenCalledTimes(2);
    expect(h.api.send.mock.calls[1]).toEqual(["room-a", payload]);
    expect(payload.reply_to_message_id).toBe("m1");
    expect(payload.attachment_ids).toEqual(["private-upload"]);
    expect(payload.sticker_resource_key).toBe("sticker:one");
    expect(h.session.getSnapshot().localSubmission).toBeNull();
    expect(h.session.getSnapshot().text).toBe("");
  });

  it("surfaces acceptance and frees the composer before SSE, then reconciles one Discord echo", async () => {
    const h = harness();
    await h.connected();
    h.session.patch({ text: "Accepted now", reply: "m1" });
    await h.session.send();
    const accepted = h.session.getSnapshot().snapshot.outbox[0];
    expect(accepted.status).toBe("pending");
    expect(h.session.getSnapshot().text).toBe("");
    expect(h.session.getSnapshot().reply).toBe("");
    expect(h.session.getSnapshot().localSubmission).toBeNull();
    h.streams[0].emit("snapshot", snapshot(["m1", "discord-echo"], "room-a", [{ ...accepted, status: "delivered", discord_message_id: "discord-echo" }]));
    expect(unmatchedOutbox(h.session.getSnapshot().snapshot)).toEqual([]);
    expect(h.session.getSnapshot().snapshot.messages.filter(item => item.id === "discord-echo")).toHaveLength(1);
    expect(h.api.send).toHaveBeenCalledOnce();
  });

  it("keeps an outstanding REST acceptance authoritative across a same-room stream restart", async () => {
    const h = harness();
    await h.connected();
    const accepted = deferred<WebOutbox>();
    h.api.send.mockReturnValueOnce(accepted.promise);
    h.session.patch({ text: "Before stream restart" });
    const sending = h.session.send();
    const payload = h.api.send.mock.calls[0][1];
    h.session.reconnect();
    h.streams[1].emit("snapshot", snapshot());
    accepted.resolve(receipt({ client_message_id: payload.client_message_id }));
    await sending;
    expect(h.session.getSnapshot().snapshot.outbox).toHaveLength(1);
    expect(h.session.getSnapshot()).toMatchObject({ busy: false, text: "", localSubmission: null });
    expect(h.api.send).toHaveBeenCalledOnce();
  });

  it("accepts SSE convergence after an unknown POST and clears the shared locked draft", async () => {
    const h = harness();
    await h.connected();
    h.api.send.mockRejectedValueOnce(new Error("response lost"));
    h.session.patch({ text: "Already accepted remotely", reply: "m1" });
    await h.session.send();
    const payload = h.api.send.mock.calls[0][1];
    h.streams[0].emit("snapshot", snapshot(["m1"], "room-a", [receipt({ client_message_id: payload.client_message_id })]));
    expect(h.session.getSnapshot()).toMatchObject({ localSubmission: null, text: "", reply: "" });
    await h.session.retry();
    expect(h.api.send).toHaveBeenCalledOnce();
  });

  it("does not revive an unknown local submission when SSE already proves acceptance before a POST failure", async () => {
    const h = harness();
    await h.connected();
    const accepted = deferred<WebOutbox>();
    h.api.send.mockReturnValueOnce(accepted.promise);
    h.session.patch({ text: "Already accepted" });
    const sending = h.session.send();
    const payload = h.api.send.mock.calls[0][1];
    h.streams[0].emit("snapshot", snapshot(["m1"], "room-a", [receipt({ client_message_id: payload.client_message_id })]));
    accepted.reject(new Error("late timeout"));
    await sending;
    expect(h.session.getSnapshot()).toMatchObject({ localSubmission: null, text: "", busy: false, error: "" });
    expect(h.session.getSnapshot().snapshot.outbox).toHaveLength(1);
  });

  it("preserves newer delivered SSE evidence when a delayed POST returns its original pending receipt", async () => {
    const h = harness();
    await h.connected();
    const accepted = deferred<WebOutbox>();
    h.api.send.mockReturnValueOnce(accepted.promise);
    h.session.patch({ text: "Already delivered" });
    const sending = h.session.send();
    const clientMessageId = h.api.send.mock.calls[0][1].client_message_id;
    h.streams[0].emit("snapshot", snapshot(["m1"], "room-a", [receipt({ client_message_id: clientMessageId, status: "delivered", discord_message_id: "discord-echo" })]));
    accepted.resolve(receipt({ client_message_id: clientMessageId, status: "pending" }));
    await sending;
    expect(h.session.getSnapshot().snapshot.outbox[0]).toMatchObject({ client_message_id: clientMessageId, status: "delivered", discord_message_id: "discord-echo" });
    expect(h.session.getSnapshot()).toMatchObject({ localSubmission: null, busy: false, text: "" });
  });

  it("does not revive a pending receipt after SSE acknowledged it and retired it behind its Discord echo", async () => {
    const h = harness();
    await h.connected();
    const accepted = deferred<WebOutbox>();
    h.api.send.mockReturnValueOnce(accepted.promise);
    h.session.patch({ text: "Echo arrived first" });
    const sending = h.session.send();
    const clientMessageId = h.api.send.mock.calls[0][1].client_message_id;
    h.streams[0].emit("snapshot", snapshot(["m1"], "room-a", [receipt({ client_message_id: clientMessageId, status: "delivered", discord_message_id: "discord-echo" })]));
    h.streams[0].emit("snapshot", snapshot(["m1", "discord-echo"]));
    accepted.resolve(receipt({ client_message_id: clientMessageId, status: "pending" }));
    await sending;
    expect(unmatchedOutbox(h.session.getSnapshot().snapshot)).toEqual([]);
    expect(h.session.getSnapshot().snapshot.messages.map(item => item.id)).toEqual(["m1", "discord-echo"]);
    expect(h.session.getSnapshot()).toMatchObject({ localSubmission: null, busy: false, text: "" });
  });

  it.each(["pending", "claimed", "delivered", "failed", "uncertain", "cancelled"] as const)("preserves %s delivery state without automatically resending", async status => {
    const h = harness();
    await h.connected();
    h.streams[0].emit("snapshot", snapshot(["m1"], "room-a", [receipt({ status, reason: "receipt detail", discord_message_id: status === "delivered" ? "not-in-view" : "" })]));
    expect(unmatchedOutbox(h.session.getSnapshot().snapshot)[0]).toMatchObject({ status, reason: "receipt detail" });
    expect(h.api.send).not.toHaveBeenCalled();
  });

  it.each(["connecting", "disconnected", "unavailable"])("blocks sends while connection is %s", async connection => {
    const h = harness();
    await h.connected();
    h.session.patch({ connection, text: "No send" });
    await h.session.send();
    expect(h.api.send).not.toHaveBeenCalled();
  });

  it.each(["anonymous", "demo", "read-only", "paused", "no-profile"])("enforces the %s restriction in the action itself", async restriction => {
    const h = harness();
    await h.connected();
    if (restriction === "anonymous") h.session.configure("", false);
    if (restriction === "demo") h.session.configure("account-a", true);
    if (restriction === "read-only") h.session.patch({ rooms: [room("room-a", { can_post: false })] });
    if (restriction === "paused") h.session.patch({ rooms: [room("room-a", { enabled: false })] });
    if (restriction === "no-profile") h.session.patch({ profileId: "unowned-profile" });
    h.session.patch({ text: "Blocked" });
    await h.session.send();
    expect(h.api.send).not.toHaveBeenCalled();
  });
});

describe("shared unread and read observers", () => {
  it("counts new IDs once and retains unread for hidden, unfocused, and history readers", async () => {
    const h = harness();
    await h.connected();
    h.session.setReader("full", false);
    h.session.setReader("companion", false);
    h.streams[0].emit("snapshot", snapshot(["m1", "m2"]));
    expect(h.session.getSnapshot().unread).toBe(1);
    const changed = snapshot(["m1", "m2"]);
    changed.messages[0] = message("m1", { text: "Edited", edited_at: "2026-10-04T01:01:00Z", pinned: true });
    h.streams[0].emit("snapshot", changed);
    expect(h.session.getSnapshot().unread).toBe(1);
    h.streams[0].emit("snapshot", snapshot(["m1", "m2", "m3"]));
    expect(h.session.getSnapshot().unread).toBe(2);
    h.session.setReader("companion", true);
    expect(h.session.getSnapshot().unread).toBe(0);
    h.streams[0].emit("snapshot", snapshot(["m2", "m3", "m4"]));
    expect(h.session.getSnapshot().unread).toBe(0);
  });

  it("removes read ownership on route leave and Companion close without terminating the stream", async () => {
    const h = harness();
    await h.connected();
    h.session.setReader("full", true);
    h.session.setReader("companion", true);
    h.session.removeReader("full");
    h.streams[0].emit("snapshot", snapshot(["m1", "m2"]));
    expect(h.session.getSnapshot().unread).toBe(0);
    h.session.removeReader("companion");
    h.streams[0].emit("snapshot", snapshot(["m1", "m2", "m3"]));
    expect(h.session.getSnapshot().unread).toBe(1);
    expect(h.streams[0].close).not.toHaveBeenCalled();
    h.session.markRead();
    expect(h.session.getSnapshot().unread).toBe(0);
  });
});

describe("authentication and room lifecycle isolation", () => {
  it("suspends private state, transport and previews before the parent document leaves", async () => {
    const h = harness();
    await h.connected();
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    h.session.patch({ text: "Private draft", reply: "m1", attachments: [{ id: "private-upload", filename: "image.png", mime_type: "image/png", size_bytes: 5, preview_url: "blob:suspended" }] });
    h.session.suspend();
    expect(h.session.getSnapshot()).toMatchObject({ authenticated: false, roomId: "", rooms: [], profiles: [], text: "", reply: "", attachments: [], snapshot: { messages: [], outbox: [] }, busy: false, connection: "disconnected" });
    expect(revoke).toHaveBeenCalledWith("blob:suspended");
    expect(h.streams[0].close).toHaveBeenCalledOnce();
  });

  it("restores the remembered room only after reauthentication of the same actor", async () => {
    const h = harness();
    await h.connected();
    h.session.patch({ text: "Unsaved private draft" });
    h.session.setReader("old-full", true);
    h.session.suspend();
    const rooms = deferred<WebRoom[]>();
    h.api.rooms.mockReturnValueOnce(rooms.promise);
    const restoring = h.session.restore("account-a", false);
    expect(h.session.getSnapshot()).toMatchObject({ authenticated: true, roomId: "room-a", rooms: [], text: "", snapshot: { messages: [] }, connection: "disconnected" });
    expect(h.createStream).toHaveBeenCalledOnce();
    rooms.resolve([room()]);
    await restoring;
    expect(h.session.getSnapshot()).toMatchObject({ roomId: "room-a", connection: "connecting", text: "" });
    expect(h.createStream).toHaveBeenCalledTimes(2);
    h.streams[1].emit("snapshot", snapshot(["restored"]));
    h.streams[0].emit("snapshot", snapshot(["stale-private"]));
    h.streams[1].emit("snapshot", snapshot(["restored", "new"]));
    expect(h.session.getSnapshot().snapshot.messages.map(item => item.id)).toEqual(["restored", "new"]);
    expect(h.session.getSnapshot().unread).toBe(1);
  });

  it("never restores the previous actor's room selection for a different authenticated actor", async () => {
    const h = harness();
    await h.connected();
    h.session.suspend();
    // Both actors may have access to the same room. Access alone must not let
    // the new actor inherit the prior actor's remembered selection.
    h.api.rooms.mockResolvedValueOnce([room("room-a"), room("account-b-room")]);
    await h.session.restore("account-b", false);
    expect(h.session.getSnapshot()).toMatchObject({ authenticated: true, roomId: "", snapshot: { messages: [], outbox: [] }, connection: "disconnected" });
    expect(h.session.getSnapshot().rooms.map(item => item.id)).toEqual(["room-a", "account-b-room"]);
    expect(h.createStream).toHaveBeenCalledOnce();
  });

  it("ignores a restore load that returns after logout", async () => {
    const h = harness();
    await h.connected();
    h.session.suspend();
    const rooms = deferred<WebRoom[]>();
    h.api.rooms.mockReturnValueOnce(rooms.promise);
    const restoring = h.session.restore("account-a", false);
    h.session.configure("", false);
    rooms.resolve([room("private-after-logout")]);
    await restoring;
    expect(h.session.getSnapshot()).toMatchObject({ authenticated: false, roomId: "", rooms: [], profiles: [], snapshot: { messages: [], outbox: [] }, connection: "disconnected" });
    expect(h.createStream).toHaveBeenCalledOnce();
  });

  it("drops remembered room restoration when logout explicitly follows suspension", async () => {
    const h = harness();
    await h.connected();
    h.session.suspend();
    h.session.configure("", false);
    await h.session.restore("account-a", false);
    expect(h.session.getSnapshot()).toMatchObject({ authenticated: true, roomId: "", connection: "disconnected" });
    expect(h.createStream).toHaveBeenCalledOnce();
  });

  it("clears room, private draft, receipts, and transport on logout", async () => {
    const h = harness();
    await h.connected();
    h.session.patch({ text: "Private draft", reply: "m1" });
    h.session.configure("", false);
    expect(h.session.getSnapshot()).toMatchObject({ roomId: "", rooms: [], profiles: [], snapshot: { messages: [], outbox: [] }, text: "", reply: "", unread: 0, connection: "disconnected" });
    expect(h.streams[0].close).toHaveBeenCalledOnce();
    h.streams[0].emit("snapshot", snapshot(["private-after-logout"]));
    expect(h.session.getSnapshot().snapshot.messages).toEqual([]);
  });

  it.each(["logout", "room-switch"])("ignores a late successful POST after %s", async transition => {
    const h = harness();
    await h.connected();
    const accepted = deferred<WebOutbox>();
    h.api.send.mockReturnValueOnce(accepted.promise);
    h.session.patch({ text: "Old room draft" });
    const sending = h.session.send();
    const payload = h.api.send.mock.calls[0][1];
    if (transition === "logout") h.session.configure("", false);
    else {
      h.session.selectRoom("room-b");
      h.streams[1].emit("snapshot", snapshot(["b1"], "room-b"));
      h.session.patch({ text: "New room draft" });
    }
    accepted.resolve(receipt({ client_message_id: payload.client_message_id }));
    await sending;
    expect(h.session.getSnapshot().snapshot.outbox).toEqual([]);
    expect(h.session.getSnapshot().text).toBe(transition === "logout" ? "" : "New room draft");
    expect(h.session.getSnapshot().localSubmission).toBeNull();
  });

  it("ignores a late failed POST after a different account logs in", async () => {
    const h = harness();
    await h.connected();
    const accepted = deferred<WebOutbox>();
    h.api.send.mockReturnValueOnce(accepted.promise);
    h.session.patch({ text: "Old account message" });
    const sending = h.session.send();
    h.session.configure("account-b", false);
    h.session.patch({ text: "New account draft" });
    accepted.reject(new Error("late failure"));
    await sending;
    expect(h.session.getSnapshot()).toMatchObject({ text: "New account draft", localSubmission: null, error: "", busy: false, rooms: [] });
  });

  it("ignores stale room/profile loads after identity changes", async () => {
    const h = harness();
    const rooms = deferred<WebRoom[]>();
    h.api.rooms.mockReturnValueOnce(rooms.promise);
    const loading = h.session.ensureLoaded();
    h.session.configure("account-b", false);
    rooms.resolve([room("old-private-room")]);
    await loading;
    expect(h.session.getSnapshot().rooms).toEqual([]);
    expect(h.session.getSnapshot().profiles).toEqual([]);
    await h.session.ensureLoaded();
    expect(h.api.rooms).toHaveBeenCalledTimes(2);
    expect(h.session.getSnapshot().rooms[0].id).toBe("room-a");
  });

  it("closes the selected room when an authoritative rooms refresh removes it", async () => {
    const h = harness();
    await h.connected();
    h.session.patch({ text: "Lost room draft" });
    h.api.rooms.mockResolvedValueOnce([room("room-b")]);
    await h.session.refresh();
    expect(h.session.getSnapshot()).toMatchObject({ roomId: "", text: "", snapshot: { messages: [], outbox: [] }, connection: "disconnected" });
    expect(h.streams[0].close).toHaveBeenCalledOnce();
  });

  it("closes and clears revoked stream state", async () => {
    const h = harness();
    await h.connected();
    h.session.patch({ text: "Private", reply: "m1" });
    h.streams[0].emit("revoked", { reason: "membership_revoked" });
    expect(h.session.getSnapshot()).toMatchObject({ roomId: "", text: "", reply: "", snapshot: { messages: [], outbox: [] }, localSubmission: null });
    expect(h.session.getSnapshot().rooms.map(item => item.id)).toEqual(["room-b"]);
    expect(h.streams[0].close).toHaveBeenCalledOnce();
  });

  it("clears all account state when SSE explicitly reports a revoked session", async () => {
    const h = harness();
    await h.connected();
    h.streams[0].emit("revoked", { reason: "session_revoked" });
    expect(h.session.getSnapshot()).toMatchObject({ authenticated: false, roomId: "", rooms: [], profiles: [], snapshot: { messages: [], outbox: [] }, text: "" });
    expect(h.streams[0].close).toHaveBeenCalledOnce();
  });

  it("checks auth during reconnect and clears state on an explicit 401", async () => {
    const h = harness();
    await h.connected();
    h.api.rooms.mockRejectedValueOnce(new RoomRequestError(401, "Authenticated session required."));
    h.streams[0].fail();
    await vi.waitFor(() => expect(h.session.getSnapshot().rooms).toEqual([]));
    expect(h.session.getSnapshot()).toMatchObject({ roomId: "", profiles: [], snapshot: { messages: [], outbox: [] }, connection: "disconnected" });
    expect(h.streams[0].close).toHaveBeenCalledOnce();
  });

  it("distinguishes a definitive auth rejection from an unknown send result", async () => {
    const h = harness();
    await h.connected();
    h.api.send.mockRejectedValueOnce(new RoomRequestError(401, "Session revoked"));
    h.session.patch({ text: "No longer authorized" });
    await h.session.send();
    expect(h.session.getSnapshot()).toMatchObject({ rooms: [], profiles: [], roomId: "", localSubmission: null, snapshot: { messages: [], outbox: [] } });
    await h.session.retry();
    expect(h.api.send).toHaveBeenCalledOnce();
  });

  it("clears room state after a definitive room permission rejection without safe-retrying it", async () => {
    const h = harness();
    await h.connected();
    h.api.send.mockRejectedValueOnce(new RoomRequestError(404, "room_unavailable"));
    h.session.patch({ text: "Permission was revoked" });
    await h.session.send();
    expect(h.session.getSnapshot()).toMatchObject({ roomId: "", text: "", localSubmission: null, snapshot: { messages: [], outbox: [] }, busy: false });
    expect(h.streams[0].close).toHaveBeenCalledOnce();
    await h.session.retry();
    expect(h.api.send).toHaveBeenCalledOnce();
  });
});

describe("private attachment lifecycle", () => {
  it.each(["logout", "room-switch"])("drops a late uploaded artifact after %s", async transition => {
    const h = harness();
    await h.connected();
    const uploaded = deferred<WebUpload>();
    h.api.uploadAttachment.mockReturnValueOnce(uploaded.promise);
    const uploading = h.session.addAttachments([new File(["image"], "image.png", { type: "image/png" })]);
    if (transition === "logout") h.session.configure("", false);
    else h.session.selectRoom("room-b");
    const createPreview = vi.spyOn(URL, "createObjectURL");
    uploaded.resolve({ id: "old-private-upload", filename: "image.png", mime_type: "image/png", size_bytes: 5 });
    await uploading;
    expect(h.session.getSnapshot().attachments).toEqual([]);
    expect(createPreview).not.toHaveBeenCalled();
    expect(h.session.getSnapshot().busy).toBe(false);
  });

  it("keeps an in-flight private upload when only the same-room stream restarts", async () => {
    const h = harness();
    await h.connected();
    const uploaded = deferred<WebUpload>();
    h.api.uploadAttachment.mockReturnValueOnce(uploaded.promise);
    const uploading = h.session.addAttachments([new File(["notes"], "notes.pdf", { type: "application/pdf" })]);
    h.session.reconnect();
    h.streams[1].emit("snapshot", snapshot());
    uploaded.resolve({ id: "accepted-upload", filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 5 });
    await uploading;
    expect(h.session.getSnapshot().attachments.map(item => item.id)).toEqual(["accepted-upload"]);
    expect(h.session.getSnapshot().busy).toBe(false);
  });

  it("continues uploading the remaining selected files after an individual non-auth failure", async () => {
    const h = harness();
    await h.connected();
    h.api.uploadAttachment.mockRejectedValueOnce(new RoomRequestError(422, "unsupported_attachment_type"));
    h.api.uploadAttachment.mockResolvedValueOnce({ id: "good-file", filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 5 });
    await h.session.addAttachments([
      new File(["unsupported"], "bad.exe", { type: "application/octet-stream" }),
      new File(["notes"], "notes.pdf", { type: "application/pdf" })
    ]);
    expect(h.api.uploadAttachment).toHaveBeenCalledTimes(2);
    expect(h.session.getSnapshot().attachments.map(item => item.id)).toEqual(["good-file"]);
    expect(h.session.getSnapshot().error).toBe("unsupported_attachment_type");
    expect(h.session.getSnapshot().busy).toBe(false);
  });

  it("stops a file batch and clears private state after the upload loses authentication", async () => {
    const h = harness();
    await h.connected();
    h.api.uploadAttachment.mockRejectedValueOnce(new RoomRequestError(401, "Session revoked"));
    await h.session.addAttachments([
      new File(["one"], "one.pdf", { type: "application/pdf" }),
      new File(["two"], "two.pdf", { type: "application/pdf" })
    ]);
    expect(h.api.uploadAttachment).toHaveBeenCalledOnce();
    expect(h.session.getSnapshot()).toMatchObject({ roomId: "", rooms: [], profiles: [], attachments: [], busy: false });
  });

  it("revokes object URLs on removal and room loss and never transmits the preview URL", async () => {
    const h = harness();
    await h.connected();
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    h.session.patch({ attachments: [{ id: "private-upload", filename: "image.png", mime_type: "image/png", size_bytes: 5, preview_url: "blob:private" }], text: "With attachment" });
    await h.session.send();
    expect(h.api.send.mock.calls[0][1].attachment_ids).toEqual(["private-upload"]);
    expect(JSON.stringify(h.api.send.mock.calls[0][1])).not.toContain("blob:private");
    expect(revoke).toHaveBeenCalledWith("blob:private");
    h.session.patch({ attachments: [{ id: "remove", filename: "image.png", mime_type: "image/png", size_bytes: 5, preview_url: "blob:remove" }] });
    h.session.removeAttachment("remove");
    expect(revoke).toHaveBeenCalledWith("blob:remove");
    h.session.patch({ attachments: [{ id: "lost", filename: "image.png", mime_type: "image/png", size_bytes: 5, preview_url: "blob:lost" }] });
    h.session.selectRoom("");
    expect(revoke).toHaveBeenCalledWith("blob:lost");
    expect(h.session.getSnapshot().attachments).toEqual([]);
  });

  it("enforces four attachments before uploading additional bytes", async () => {
    const h = harness();
    await h.connected();
    h.session.patch({ attachments: ["1", "2", "3", "4"].map(id => ({ id, filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 3 })) });
    await h.session.addAttachments([new File(["extra"], "extra.pdf", { type: "application/pdf" })]);
    expect(h.api.uploadAttachment).not.toHaveBeenCalled();
    expect(h.session.getSnapshot().attachments).toHaveLength(4);
    expect(h.session.getSnapshot().error).toBe("attachment_limit_exceeded");
  });
});
