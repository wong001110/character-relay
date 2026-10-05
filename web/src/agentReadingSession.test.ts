import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentReadingApi, type AgentReadingStatus } from "./agentReadingApi";
import { webRoomApi, type WebRoom, type WebSnapshot } from "./webRoomApi";
import { WebRoomSession } from "./webRoomSession";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return {promise, resolve};
}
const flush = async () => { for (let count = 0; count < 20; count++) await Promise.resolve(); };
const room = (id: string): WebRoom => ({id, name: id, connection_id: "connection", guild_id: "guild", channel_id: "channel", thread_id: "", enabled: true, can_manage: false, can_post: true});
const snapshot = (revision = 1, roomId = "a"): WebSnapshot => ({room_id: roomId, source_revision: revision, messages: [], outbox: [], history_limit: 64});
const status = (roomId = "a", profileId = "p", next: Partial<AgentReadingStatus> = {}): AgentReadingStatus => ({room_id: roomId, profile_id: profileId, cursor_revision: 0, observed_revision: 1, pending_count: 1, needs_reread: false, gap_generation: 0, history_scope: "recorded_current_state", batch: null, ...next});
const captured = (next: Partial<AgentReadingStatus> = {}) => status("a", "p", {needs_reread: true, gap_generation: 1, batch: {id: "captured", from_revision: 0, to_revision: 1, gap_generation: 1, needs_reread: true, items: []}, ...next});
class Stream {
  close = vi.fn();
  onerror: EventSource["onerror"] = null;
  listeners = new Map<string, EventListenerOrEventListenerObject[]>();
  addEventListener(type: string, callback: EventListenerOrEventListenerObject) { this.listeners.set(type, [...this.listeners.get(type) ?? [], callback]); }
  emit(type: string, value: unknown = {}) {
    const event = {data: JSON.stringify(value)} as MessageEvent<string>;
    for (const callback of this.listeners.get(type) ?? []) { if (typeof callback === "function") callback(event); else callback.handleEvent(event); }
  }
  fail() { this.onerror?.call(this as unknown as EventSource, new Event("error")); }
}
const sessions: WebRoomSession[] = [];
async function harness() {
  const states = new Map<string, AgentReadingStatus>();
  const current = (r: string, p: string) => states.get(`${r}:${p}`) ?? status(r, p);
  const api = {
    ...agentReadingApi,
    status: vi.fn(async (r: string, p: string) => current(r, p)),
    gap: vi.fn(async (r: string, p: string, _event: string) => {
      const previous = current(r, p);
      const next = {...previous, needs_reread: true, gap_generation: previous.gap_generation + 1};
      states.set(`${r}:${p}`, next);
      return next;
    }),
    batch: vi.fn(async (_r: string, _p: string) => captured()),
    complete: vi.fn(async (_r: string, _p: string, _id: string) => status("a", "p", {cursor_revision: 1, pending_count: 0, gap_generation: 1}))
  };
  const streams: Stream[] = [];
  const create = vi.fn(() => { const stream = new Stream(); streams.push(stream); return stream as unknown as EventSource; });
  const session = new WebRoomSession({...webRoomApi, rooms: async () => [room("a"), room("b")], profiles: async () => [{id: "p", display_name: "Dots", avatar_url: "", version: 1}, {id: "q", display_name: "Other", avatar_url: "", version: 1}]}, create, api);
  sessions.push(session);
  session.configure("account", false);
  await session.ensureLoaded();
  session.selectRoom("a");
  streams[0].emit("snapshot", snapshot());
  const activate = async () => { session.setAgentReading(true); await flush(); };
  return {session, api, streams, create, states, activate};
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => { for (const session of sessions.splice(0)) session.dispose(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("explicit Agent progress on the existing session", () => {
  it("is opt-in, shares one stream, reports activation as a durable gap and ignores human reading", async () => {
    const h = await harness();
    expect(h.api.gap).not.toHaveBeenCalled();
    await h.activate();
    expect(h.create).toHaveBeenCalledOnce();
    expect(h.api.gap).toHaveBeenCalledWith("a", "p", expect.any(String));
    expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
    h.session.setReader("full", true); h.session.markRead(); h.session.setReader("companion", true);
    expect(h.api.complete).not.toHaveBeenCalled();
    expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
  });
  it("refreshes same-ID edits by source revision and never polls status on a heartbeat", async () => {
    const h = await harness(); await h.activate();
    h.api.status.mockClear();
    h.streams[0].emit("snapshot", snapshot(2)); await flush();
    expect(h.api.status).toHaveBeenCalledOnce();
    h.streams[0].emit("snapshot", snapshot(2)); h.streams[0].emit("heartbeat"); await flush();
    expect(h.api.status).toHaveBeenCalledOnce();
  });
  it("coalesces concurrent presentation refresh requests and refreshes again if a revision arrived in flight", async () => {
    const h = await harness(); await h.activate();
    const pending = deferred<AgentReadingStatus>(); h.api.status.mockReturnValueOnce(pending.promise);
    h.session.refreshAgentReading();
    h.streams[0].emit("snapshot", snapshot(2)); h.streams[0].emit("snapshot", snapshot(3));
    expect(h.api.status).toHaveBeenCalledOnce();
    pending.resolve(status()); await flush();
    expect(h.api.status).toHaveBeenCalledTimes(2);
  });
  it("ignores a late response from a room that is no longer selected", async () => {
    const h = await harness(); const pending = deferred<AgentReadingStatus>(); h.api.gap.mockReturnValueOnce(pending.promise);
    h.session.setAgentReading(true); h.session.selectRoom("b"); h.streams[1].emit("snapshot", snapshot(1, "b")); await flush();
    pending.resolve(status("a", "p", {pending_count: 999})); await flush();
    expect(h.session.getSnapshot().agentReading?.status?.room_id).toBe("b");
    expect(h.session.getSnapshot().agentReading?.status?.pending_count).not.toBe(999);
  });
  it("isolates late responses by participant even within the same room", async () => {
    const h = await harness(); const pending = deferred<AgentReadingStatus>(); h.api.gap.mockReturnValueOnce(pending.promise);
    h.session.setAgentReading(true); h.session.patch({profileId: "q"}); await flush();
    pending.resolve(status("a", "p", {pending_count: 999})); await flush();
    expect(h.session.getSnapshot().agentReading?.status?.profile_id).toBe("q");
    expect(h.create).toHaveBeenCalledOnce();
  });
  it("cannot re-enable in demo or restore an in-flight result after logout", async () => {
    const h = await harness(); const pending = deferred<AgentReadingStatus>(); h.api.gap.mockReturnValueOnce(pending.promise);
    h.session.setAgentReading(true); h.session.configure("", false); pending.resolve(status()); await flush();
    expect(h.session.getSnapshot().agentReading?.status).toBeUndefined();
    h.session.configure("account", true); h.session.setAgentReading(true);
    expect(h.session.getSnapshot().agentReading?.enabled).not.toBe(true);
    expect(h.api.gap).toHaveBeenCalledOnce();
  });
  it("disables the shared opt-in before entering demo mode", async () => {
    const h = await harness(); await h.activate();
    h.session.configure("account", true); h.session.refreshAgentReading(); await flush();
    expect(h.session.getSnapshot().agentReading?.enabled).toBe(false);
    expect(h.api.status).not.toHaveBeenCalled();
  });
  it("completes only the captured server batch ID, leaving later changes pending", async () => {
    const h = await harness(); await h.activate(); await h.session.readAgentBatch();
    h.api.status.mockResolvedValue(captured({observed_revision: 2, pending_count: 2}));
    h.streams[0].emit("snapshot", snapshot(2)); await flush();
    h.api.complete.mockResolvedValue(status("a", "p", {cursor_revision: 1, observed_revision: 2, pending_count: 1, gap_generation: 1}));
    await h.session.completeAgentBatch();
    expect(h.api.complete).toHaveBeenCalledWith("a", "p", "captured");
    expect(h.session.getSnapshot().agentReading?.status?.cursor_revision).toBe(1);
    expect(h.session.getSnapshot().agentReading?.status?.pending_count).toBe(1);
  });
  it("queues a gap occurring while a batch is being captured and disables confirmation during recovery", async () => {
    const h = await harness(); await h.activate(); const pending = deferred<AgentReadingStatus>(); h.api.batch.mockReturnValueOnce(pending.promise);
    const batch = h.session.readAgentBatch(); h.streams[0].fail();
    await h.session.completeAgentBatch(); expect(h.api.complete).not.toHaveBeenCalled();
    h.states.set("a:p", captured()); pending.resolve(captured()); await batch; await flush();
    expect(h.api.gap).toHaveBeenCalledTimes(2);
    expect(h.session.getSnapshot().agentReading?.status?.gap_generation).toBe(2);
    expect(h.session.getSnapshot().agentReading?.status?.batch?.gap_generation).toBe(1);
  });
  it("reports a new gap after an in-flight completion without erasing it", async () => {
    const h = await harness(); await h.activate(); await h.session.readAgentBatch();
    const pending = deferred<AgentReadingStatus>(); h.api.complete.mockReturnValueOnce(pending.promise);
    const completion = h.session.completeAgentBatch(); h.streams[0].fail();
    pending.resolve(status("a", "p", {cursor_revision: 1, pending_count: 0, gap_generation: 1})); await completion; await flush();
    expect(h.api.gap).toHaveBeenCalledTimes(2);
    expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
  });
  it("keeps a lost gap response idempotent until explicit retry succeeds", async () => {
    const h = await harness(); h.api.gap.mockRejectedValueOnce(new Error("lost response")); await h.activate();
    expect(h.api.gap).toHaveBeenCalledOnce(); expect(h.session.getSnapshot().agentReading?.localGap).toBe(true);
    await h.session.completeAgentBatch(); expect(h.api.complete).not.toHaveBeenCalled();
    h.session.refreshAgentReading(); await flush();
    expect(h.api.gap.mock.calls[0][2]).toBe(h.api.gap.mock.calls[1][2]);
    expect(h.session.getSnapshot().agentReading?.localGap).toBe(false);
    expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
  });
  it.each(["status", "batch", "complete"] as const)("durably reports uncertainty after a lost %s response instead of resetting to idle", async operation => {
    const h = await harness(); await h.activate(); if (operation === "complete") await h.session.readAgentBatch();
    h.api[operation].mockRejectedValueOnce(new Error("network"));
    if (operation === "status") h.session.refreshAgentReading(); else if (operation === "batch") await h.session.readAgentBatch(); else await h.session.completeAgentBatch();
    await flush(); expect(h.session.getSnapshot().agentReading?.localGap).toBe(true); expect(h.api.gap).toHaveBeenCalledOnce();
    h.session.refreshAgentReading(); await flush();
    expect(h.api.gap).toHaveBeenCalledTimes(2); expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
  });
  it("treats malformed nested batch display data as uncertainty and reports a durable gap on retry", async () => {
    const h = await harness(); await h.activate();
    const malformed = captured(); malformed.batch!.items = [{message_id: "m", source_revision: 1, room_revision: 1, change: "new", state: "current", message: {
      id: "m", text: "Untrusted message", display_name: "Alice", avatar_url: "", actor_type: "discord_user", deleted: false, content_available: true,
      attachments: [], custom_emojis: [], mentions: [], stickers: [], embeds: [], poll: {question: {cannotRender: true}}, reply_preview: null
    }}] as never;
    h.api.batch.mockResolvedValueOnce(malformed); await h.session.readAgentBatch();
    expect(h.session.getSnapshot().agentReading?.status?.batch).toBeNull(); expect(h.session.getSnapshot().agentReading?.localGap).toBe(true);
    expect(h.session.getSnapshot().agentReading?.error).toBe("invalid_agent_reading_status");
    await h.session.completeAgentBatch(); expect(h.api.complete).not.toHaveBeenCalled();
    h.session.refreshAgentReading(); await flush(); expect(h.api.gap).toHaveBeenCalledTimes(2);
    expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
  });
  it("rejects malformed or foreign status and requires a durable recovery", async () => {
    const h = await harness(); h.api.gap.mockResolvedValueOnce(status("foreign")); await h.activate();
    expect(h.session.getSnapshot().agentReading?.status).toBeNull(); expect(h.session.getSnapshot().agentReading?.localGap).toBe(true);
    await h.session.readAgentBatch(); expect(h.api.batch).not.toHaveBeenCalled();
    h.session.refreshAgentReading(); await flush(); expect(h.session.getSnapshot().agentReading?.status?.room_id).toBe("a");
  });
});

describe("bounded transport gap detection", () => {
  it("closes a still-live socket on browser offline and durably reports the gap before online status recovery", async () => {
    const h = await harness(); await h.activate(); h.session.patch({text: "Preserved draft"});
    h.session.setOnline(false); expect(h.streams[0].close).toHaveBeenCalledOnce();
    h.streams[0].emit("heartbeat"); h.streams[0].emit("snapshot", snapshot(2)); await flush();
    expect(h.session.getSnapshot().connection).toBe("disconnected"); expect(h.session.getSnapshot().agentReading?.localGap).toBe(true);
    expect(h.api.gap).toHaveBeenCalledOnce(); expect(h.session.getSnapshot().text).toBe("Preserved draft");
    h.session.setOnline(true); await flush(); h.streams[1].emit("snapshot", snapshot(2)); await flush();
    expect(h.api.gap).toHaveBeenCalledTimes(2); expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
    expect(h.create).toHaveBeenCalledTimes(2); expect(h.session.getSnapshot().text).toBe("Preserved draft");
  });
  it("allows one immediate normal rollover without inventing a persistent gap", async () => {
    const h = await harness(); await h.activate(); h.streams[0].emit("rollover"); h.streams[0].fail();
    await vi.advanceTimersByTimeAsync(3000); h.streams[0].emit("snapshot", snapshot()); await flush();
    expect(h.api.gap).toHaveBeenCalledOnce(); expect(h.session.getSnapshot().agentReading?.localGap).toBe(false);
    await vi.advanceTimersByTimeAsync(2000); expect(h.api.gap).toHaveBeenCalledOnce();
  });
  it("treats a second failure within rollover grace as an actual gap", async () => {
    const h = await harness(); await h.activate(); h.streams[0].emit("rollover"); h.streams[0].fail(); h.streams[0].fail(); await flush();
    expect(h.api.gap).toHaveBeenCalledTimes(2);
  });
  it("bounds normal reopen grace to five seconds", async () => {
    const h = await harness(); await h.activate(); h.streams[0].emit("rollover"); h.streams[0].fail();
    await vi.advanceTimersByTimeAsync(5000); expect(h.api.gap).toHaveBeenCalledTimes(2);
    h.streams[0].emit("snapshot", snapshot()); await flush();
    expect(h.session.getSnapshot().agentReading?.status?.needs_reread).toBe(true);
  });
  it("detects silent transport loss within fifteen seconds, but never polls status on healthy heartbeats", async () => {
    const h = await harness(); await h.activate();
    for (let count = 0; count < 3; count++) { await vi.advanceTimersByTimeAsync(5000); h.streams[0].emit("heartbeat"); }
    expect(h.api.gap).toHaveBeenCalledOnce(); expect(h.api.status).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(15000); await flush();
    expect(h.api.gap).toHaveBeenCalledTimes(2); expect(h.create).toHaveBeenCalledTimes(2); expect(h.session.getSnapshot().connection).toBe("connecting");
  });
  it("does not suppress malformed snapshots even immediately after a normal rollover marker", async () => {
    const h = await harness(); await h.activate(); h.streams[0].emit("rollover"); h.streams[0].emit("snapshot", {room_id: "a", messages: [], outbox: [], source_revision: "not a revision"}); await flush();
    expect(h.session.getSnapshot().connection).toBe("unavailable"); expect(h.api.gap).toHaveBeenCalledTimes(2); expect(h.streams[0].close).toHaveBeenCalledOnce();
  });
  it("cancels watchdogs when the shared panel is disabled or the session is disposed", async () => {
    const h = await harness(); await h.activate(); h.session.setAgentReading(false); await vi.advanceTimersByTimeAsync(20000);
    expect(h.api.gap).toHaveBeenCalledOnce(); expect(h.create).toHaveBeenCalledOnce();
  });
});
