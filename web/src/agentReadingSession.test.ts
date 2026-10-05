import { afterEach, describe, expect, it, vi } from "vitest";
import { webRoomApi, type WebMessage, type WebRoom, type WebSnapshot } from "./webRoomApi";
import { WebRoomSession } from "./webRoomSession";

const room = (id = "r"): WebRoom => ({id, name: id, connection_id: "c", guild_id: "g", channel_id: "ch", thread_id: "", enabled: true, can_manage: false, can_post: true});
const message = (id: string, extra: Partial<WebMessage> = {}): WebMessage => ({id, author_id: "human", display_name: "Dots", avatar_url: "", actor_type: "discord_user", text: id, deleted: false, content_available: true, created_at: null, edited_at: null, reply_to_message_id: "", reply_preview: null, attachments: [], custom_emojis: [], stickers: [], mentions: [], embeds: [], poll: null, reactions: [], pinned: false, ...extra});
const snapshot = (messages: WebMessage[], roomId = "r"): WebSnapshot => ({room_id: roomId, messages, outbox: [], history_limit: 64});
class FakeStream {
  close = vi.fn(); onerror: EventSource["onerror"] = null;
  private handlers = new Map<string, EventListenerOrEventListenerObject[]>();
  addEventListener(type: string, listener: EventListenerOrEventListenerObject) { this.handlers.set(type, [...this.handlers.get(type) ?? [], listener]); }
  emit(type: string, data: unknown = {}) {
    const event = {data: JSON.stringify(data)} as MessageEvent<string>;
    for (const listener of this.handlers.get(type) ?? []) { if (typeof listener === "function") listener(event); else listener.handleEvent(event); }
  }
  fail() { this.onerror?.call(this as unknown as EventSource, new Event("error")); }
}
const sessions: WebRoomSession[] = [];
async function harness(initial = [message("old")], enable = true) {
  const api = {...webRoomApi, rooms: vi.fn(async () => [room(), room("other")]), profiles: vi.fn(async () => [{id: "p", display_name: "Dots", avatar_url: "", version: 1}, {id: "q", display_name: "Second", avatar_url: "", version: 1}])};
  const streams: FakeStream[] = [];
  const session = new WebRoomSession(api, () => { const stream = new FakeStream(); streams.push(stream); return stream as unknown as EventSource; });
  sessions.push(session); session.configure("user", false); await session.ensureLoaded(); session.selectRoom("r");
  streams[0].emit("snapshot", snapshot(initial)); if (enable) session.setAgentReading(true);
  return {session, streams, api, emit: (messages: WebMessage[]) => streams.at(-1)!.emit("snapshot", snapshot(messages)), count: () => session.getSnapshot().agentReading?.pendingCount};
}
afterEach(() => { sessions.splice(0).forEach(session => session.dispose()); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("frontend participation reminders", () => {
  it("starts at zero with 64 old messages and needs no status or batch API", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const h = await harness(Array.from({length: 64}, (_, i) => message(`old-${i}`)));
    expect(h.count()).toBe(0); expect(fetch).not.toHaveBeenCalled();
  });
  it("baselines the first snapshot if enabled before connection", async () => {
    const h = await harness([], false); h.session.selectRoom("other"); h.session.setAgentReading(true);
    h.streams.at(-1)!.emit("snapshot", snapshot([message("history")], "other"));
    expect(h.count()).toBe(0);
    h.streams.at(-1)!.emit("snapshot", snapshot([message("history"), message("new")], "other"));
    expect(h.count()).toBe(1);
  });
  it("counts each new live ID once, including unavailable content", async () => {
    const h = await harness(); const next = [message("old"), message("new"), message("unknown", {content_available: false})];
    h.emit(next); h.emit(next); expect(h.count()).toBe(2);
  });
  it("ignores edits, tombstones, reaction updates and a returning recent ID", async () => {
    const h = await harness(); h.emit([message("new")]); expect(h.count()).toBe(1);
    h.emit([message("old", {text: "edited", edited_at: "2026-10-05T01:00:00Z"}), message("new", {deleted: true}), message("tombstone", {deleted: true})]);
    expect(h.count()).toBe(1);
  });
  it("does not trust display names and suppresses only verified selected-participant echoes", async () => {
    const h = await harness();
    h.emit([message("own", {author_id: "web:p", actor_type: "web_participant"}), message("other", {author_id: "web:q", actor_type: "web_participant"}), message("same-name")]);
    expect(h.count()).toBe(2);
  });
  it("clears all current reminders synchronously, then counts later arrivals", async () => {
    const h = await harness(); h.emit([message("a"), message("b")]); expect(h.count()).toBe(2);
    h.session.clearAgentReminders(); expect(h.count()).toBe(0);
    h.emit([message("a"), message("b"), message("c")]); expect(h.count()).toBe(1);
  });
  it("is independent of human readers, focus acknowledgements and draft edits", async () => {
    const h = await harness(); h.session.setReader("full", true); h.emit([message("new")]);
    h.session.markRead(); h.session.patch({text: "Draft"});
    expect(h.count()).toBe(1); expect(h.session.getSnapshot().unread).toBe(0);
  });
  it("shares count and clear across presentations without another stream", async () => {
    const h = await harness(); const full = vi.fn(); const companion = vi.fn();
    const leave = h.session.subscribe(full); h.session.subscribe(companion);
    h.emit([message("new")]); expect(full).toHaveBeenCalledOnce(); expect(companion).toHaveBeenCalledOnce();
    leave(); h.session.clearAgentReminders(); expect(h.count()).toBe(0); expect(h.streams).toHaveLength(1);
  });
  it("starts at zero after disable/re-enable and participant changes", async () => {
    const h = await harness(); h.emit([message("new")]); h.session.setAgentReading(false); h.session.setAgentReading(true); expect(h.count()).toBe(0);
    h.emit([message("new"), message("later")]); h.session.patch({profileId: "q"}); expect(h.count()).toBe(0);
    h.emit([message("later"), message("after-switch")]); expect(h.count()).toBe(1);
  });
  it("clears on room/account changes and rejects stale room stream events", async () => {
    const h = await harness(); h.emit([message("new")]); h.session.selectRoom("other"); expect(h.count()).toBe(0);
    h.streams[0].emit("snapshot", snapshot([message("stale")])); expect(h.count()).toBe(0);
    h.session.configure("another-user", false); expect(h.session.getSnapshot().agentReading).toBeUndefined();
  });
  it("preserves counted reminders but baselines missed messages after unexpected reconnect", async () => {
    const h = await harness(); h.emit([message("before")]); h.streams[0].fail();
    expect(h.session.getSnapshot().connection).toBe("reconnecting"); expect(h.count()).toBe(1);
    h.emit([message("before"), message("missed")]); expect(h.count()).toBe(1);
    h.emit([message("before"), message("missed"), message("after")]); expect(h.count()).toBe(2);
  });
  it("baselines offline recovery without clearing prior reminders or draft", async () => {
    const h = await harness(); h.emit([message("before")]); h.session.patch({text: "Draft"}); h.session.setOnline(false);
    expect(h.session.getSnapshot().connection).toBe("disconnected"); h.session.clearAgentReminders();
    h.session.setOnline(true); h.emit([message("before"), message("missed")]); expect(h.count()).toBe(0);
    expect(h.session.getSnapshot().text).toBe("Draft"); expect(h.streams[0].close).toHaveBeenCalledOnce();
  });
  it("retains baseline across immediate natural rollover", async () => {
    const h = await harness(); h.streams[0].emit("rollover"); h.streams[0].fail();
    h.emit([message("old"), message("after-rollover")]); expect(h.count()).toBe(1);
  });
  it("baselines a failed natural rollover reopen", async () => {
    const h = await harness(); h.streams[0].emit("rollover"); h.streams[0].fail(); h.streams[0].fail();
    h.emit([message("old"), message("missed")]); expect(h.count()).toBe(0);
  });
  it("reconnects and baselines after silent heartbeat loss", async () => {
    vi.useFakeTimers(); const h = await harness(); h.emit([message("new")]);
    await vi.advanceTimersByTimeAsync(15_001); expect(h.session.getSnapshot().connection).toBe("connecting");
    h.emit([message("new"), message("missed")]); expect(h.count()).toBe(1); expect(h.streams).toHaveLength(2);
  });
  it("rejects activation without authentication or in demo", async () => {
    const h = await harness([], false); h.session.configure("user", true); h.session.setAgentReading(true);
    expect(h.session.getSnapshot().agentReading?.enabled).not.toBe(true);
    h.session.configure("", false); h.session.setAgentReading(true); expect(h.session.getSnapshot().agentReading).toBeUndefined();
  });
});
