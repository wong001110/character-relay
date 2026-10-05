import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentReadingPanel } from "./AgentReadingPanel";
import { agentReadingApi, validateAgentReadingStatus, type AgentReadingStatus } from "./agentReadingApi";
import type { WebMessage } from "./webRoomApi";
import { WebRoomSession, type WebRoomSessionState } from "./webRoomSession";

const tx = (english: string) => english;
const message = (next: Partial<WebMessage> = {}): WebMessage => ({id: "m", author_id: "author", display_name: "Alice", avatar_url: "", actor_type: "discord_user", text: "Visible batch body <script>untrusted()</script>", deleted: false, content_available: true, created_at: "2026-10-05T00:00:00Z", edited_at: null, reply_to_message_id: "", reply_preview: null, attachments: [], custom_emojis: [], stickers: [], mentions: [], embeds: [], poll: null, reactions: [], pinned: false, ...next});
const status = (next: Partial<AgentReadingStatus> = {}): AgentReadingStatus => ({room_id: "r", profile_id: "p", cursor_revision: 1, observed_revision: 5, pending_count: 2, needs_reread: false, gap_generation: 1, history_scope: "recorded_current_state", batch: {id: "batch-one", from_revision: 1, to_revision: 4, needs_reread: false, gap_generation: 1, items: [{message_id: "m", source_revision: 1, room_revision: 4, change: "new", state: "current", message: message()}]}, ...next});
const state = (next: Partial<WebRoomSessionState> = {}): WebRoomSessionState => ({authenticated: true, demoMode: false, roomId: "r", rooms: [{id: "r", name: "Room", connection_id: "connection", guild_id: "guild", channel_id: "channel", thread_id: "", enabled: true, can_manage: false, can_post: true}], profiles: [{id: "p", display_name: "Dots", avatar_url: "", version: 1}], profileId: "p", snapshot: {room_id: "r", messages: [], outbox: [], history_limit: 64, source_revision: 5}, connection: "connected", unread: 0, text: "", reply: "", attachments: [], stickerResourceKey: "", localSubmission: null, busy: false, error: "", agentReading: {enabled: true, busy: false, localGap: false, error: "", status: status()}, ...next});
const render = (next = state()) => renderToStaticMarkup(<AgentReadingPanel state={next} session={new WebRoomSession()} tx={tx} />);
const button = (html: string, attribute: string) => new RegExp(`<button[^>]*${attribute}="true"[^>]*>[\\s\\S]*?<\\/button>`, "u").exec(html)?.[0];
afterEach(() => vi.unstubAllGlobals());

describe("Agent reading HTML for low-frequency browser checks", () => {
  it("exposes a lightweight readable summary without importing batch text into it", () => {
    const html = render();
    const summary = /<div data-agent-summary="true">([\s\S]*?)<\/div>/u.exec(html)?.[1];
    expect(summary).toContain("Batch in progress"); expect(summary).toContain("Room: Room (r)"); expect(summary).toContain("Participant: Dots (p)");
    expect(summary).toContain("Observed revision: 5"); expect(summary).toContain("Pending changes: 2"); expect(summary).toContain("Completed through revision: 1");
    expect(summary).not.toContain("Visible batch body"); expect(summary).not.toContain("Complete this batch");
    expect(html).toContain('data-agent-batch-id="batch-one"'); expect(html).toContain('data-from-revision="1" data-to-revision="4"'); expect(html).toContain('data-agent-item-id="m"');
    expect(html).toContain("&lt;script&gt;untrusted()&lt;/script&gt;"); expect(html).not.toContain("<script>");
  });
  it("reports unknown instead of zero pending when the transport is disconnected and withholds stale bodies", () => {
    const html = render(state({connection: "reconnecting"}));
    expect(html).toContain('data-status="unknown"'); expect(html).toContain('data-pending-count="unknown"'); expect(html).toContain("Pending changes: unknown");
    expect(html).not.toContain("Visible batch body"); expect(button(html, "data-agent-complete")).toContain("disabled"); expect(button(html, "data-agent-retry")).not.toContain("disabled");
  });
  it("withholds cached batch content during status refresh so source deletion cannot flash stale text", () => {
    const original = state(); const html = render(state({agentReading: {...original.agentReading!, busy: true}}));
    expect(html).not.toContain("Visible batch body"); expect(html).toContain("Content withheld until fresh reading state is confirmed");
    expect(button(html, "data-agent-complete")).toContain("disabled");
  });
  it("makes a later recovery gap visible without changing the captured batch cutoff", () => {
    const original = state(); const html = render(state({agentReading: {...original.agentReading!, status: status({needs_reread: true, gap_generation: 2})}}));
    expect(html).toContain('data-status="needs_reread"'); expect(html).toContain('data-to-revision="4"'); expect(html).toContain("Reread required"); expect(html).toContain("Completion advances only through this batch");
  });
  it("uses processing for a batch that already captured the active reread generation", () => {
    const original = state(); const next = status({needs_reread: true}); next.batch!.needs_reread = true;
    const html = render(state({agentReading: {...original.agentReading!, status: next}}));
    expect(html).toContain('data-status="processing"'); expect(html).toContain("recovery context");
  });
  it("shows edited and removed placeholders with IDs and revisions instead of captured private bodies", () => {
    const original = state(); const next = status(); next.batch!.items = [
      {message_id: "edited", source_revision: 4, room_revision: 3, change: "edited", state: "changed", message: null},
      {message_id: "deleted", source_revision: 2, room_revision: 4, change: "deleted", state: "removed", message: null}
    ];
    const html = render(state({agentReading: {...original.agentReading!, status: next}}));
    expect(html).toContain("Message changed after this batch was captured"); expect(html).toContain("Message removed; its content is unavailable");
    expect(html).toContain('data-source-revision="4"'); expect(html).not.toContain("Visible batch body");
  });
  it("keeps supplied GIF descriptions readable and makes viewing explicit while blocking unsafe URLs", () => {
    vi.stubGlobal("window", {location: {href: "https://relay.example/portal", origin: "https://relay.example"}});
    const original = state(); const next = status();
    next.batch!.items[0].message = message({attachments: [
      {attachment_id: "gif", url: "https://cdn.discordapp.com/reaction.gif", proxy_url: "", filename: "reaction.gif", description: "A person waves hello", content_type: "image/gif", size_bytes: 10, width: 10, height: 10},
      {attachment_id: "unsafe", url: "javascript:alert(1)", proxy_url: "", filename: "unsafe.gif", description: "", content_type: "image/gif", size_bytes: 10, width: 10, height: 10}
    ], custom_emojis: [{resource_id: "123", resource_key: "emoji:123", resource_type: "emoji", name: "happy", animated: false, asset_url: "javascript:alert(2)", format_type: "", description: ""}], text: "Hello <:happy:123>"});
    const html = render(state({agentReading: {...original.agentReading!, status: next}}));
    expect(html).toContain("A person waves hello"); expect(html).toContain("View GIF"); expect(html).toContain('alt=":happy:"'); expect(html).not.toContain("javascript:");
    expect(html).toContain("Recorded current state only"); expect(html).toContain("every 60 seconds");
  });
  it("disallows activation in demo mode or without an owned participant selection", () => {
    expect(button(render(state({demoMode: true, agentReading: undefined})), "data-agent-toggle")).toContain("disabled");
    expect(button(render(state({profileId: "", agentReading: undefined})), "data-agent-toggle")).toContain("disabled");
  });
  it("cannot confirm local uncertainty even when a stale batch is present", () => {
    const original = state(); const html = render(state({agentReading: {...original.agentReading!, localGap: true}}));
    expect(html).toContain('data-status="unknown"'); expect(button(html, "data-agent-complete")).toContain("disabled"); expect(html).not.toContain("Visible batch body");
  });
  it("requires explicit completion even for an empty recovery batch", () => {
    const original = state(); const next = status(); next.batch!.items = [];
    const html = render(state({agentReading: {...original.agentReading!, status: next}}));
    expect(html).toContain("No recorded messages in this batch"); expect(button(html, "data-agent-complete")).not.toContain("disabled");
  });
});

describe("Agent status API boundary", () => {
  it.each([
    {room_id: "other"}, {profile_id: "other"}, {history_scope: "complete"}, {pending_count: -1}, {observed_revision: 0}, {batch: undefined}
  ])("rejects invalid status %j", fields => {
    expect(() => validateAgentReadingStatus({...status(), ...fields} as AgentReadingStatus, "r", "p")).toThrow("invalid_agent_reading_status");
  });
  it("rejects a changed item retaining body text and malformed media arrays", () => {
    const changed = status(); changed.batch!.items[0].state = "changed";
    expect(() => validateAgentReadingStatus(changed, "r", "p")).toThrow();
    const malformed = status(); malformed.batch!.items[0].message!.attachments = [null as never];
    expect(() => validateAgentReadingStatus(malformed, "r", "p")).toThrow();
  });
  it.each([
    {reply_preview: {message_id: "original", display_name: "Alice", summary: {html: "bad object"}, available: true, in_snapshot: false}},
    {reply_preview: {message_id: "original", display_name: {html: "bad object"}, summary: "Reply context", available: true, in_snapshot: false}},
    {reply_preview: {message_id: "original", display_name: "Alice", summary: "Reply context", available: "true", in_snapshot: false}},
    {poll: {question: {html: "bad object"}}}
  ])("rejects malformed nested display data before React can render it: %j", fields => {
    const malformed = status(); malformed.batch!.items[0].message = {...message(), ...fields} as unknown as WebMessage;
    expect(() => validateAgentReadingStatus(malformed, "r", "p")).toThrow("invalid_agent_reading_status");
  });
  it("retains valid reply context and poll text as readable escaped HTML", () => {
    const original = state(); const valid = status();
    valid.batch!.items[0].message = message({reply_preview: {message_id: "original", display_name: "Alice", summary: "Context <script>", available: true, in_snapshot: false}, poll: {question: "A choice <script>", answers: [], allow_multiselect: false, expires_at: null, results_finalized: false}});
    expect(validateAgentReadingStatus(valid, "r", "p")).toBe(valid);
    const html = render(state({agentReading: {...original.agentReading!, status: valid}}));
    expect(html).toContain("Context &lt;script&gt;"); expect(html).toContain("Poll: A choice &lt;script&gt;"); expect(html).not.toContain("<script>");
  });
  it("uses a finite, uncached same-origin GET and sends only batch ID on completion", async () => {
    const fetcher = vi.fn(async () => ({ok: true, status: 200, json: async () => status()})); vi.stubGlobal("fetch", fetcher);
    await agentReadingApi.status("r/a", "p b");
    expect(fetcher).toHaveBeenCalledWith("/api/web-chat/rooms/r%2Fa/agent-reading/p%20b", expect.objectContaining({credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal)}));
    await agentReadingApi.complete("r", "p", "batch-one");
    expect(fetcher).toHaveBeenLastCalledWith("/api/web-chat/rooms/r/agent-reading/p/complete", expect.objectContaining({method: "POST", body: JSON.stringify({batch_id: "batch-one"})}));
  });
});
