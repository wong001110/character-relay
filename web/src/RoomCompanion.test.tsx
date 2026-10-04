import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "./i18n";
import { RoomCompanion, companionMessageText } from "./RoomCompanion";
import { WebRoomSession, type WebRoomSessionState } from "./webRoomSession";
import type { WebMessage, WebOutbox } from "./webRoomApi";

function message(next: Partial<WebMessage> = {}): WebMessage {
  return {
    id: "123", author_id: "author-1", display_name: "Visible author", avatar_url: "",
    actor_type: "web_participant", text: "Visible message", deleted: false,
    content_available: true, created_at: "2026-10-04T08:12:00Z", edited_at: null,
    reply_to_message_id: "", reply_preview: null, attachments: [], custom_emojis: [],
    stickers: [], mentions: [], embeds: [], poll: null, reactions: [], pinned: false,
    ...next
  };
}

function receipt(status: WebOutbox["status"], next: Partial<WebOutbox> = {}): WebOutbox {
  return {
    id: `receipt-${status}`, client_message_id: `client-${status}`, profile_id: "profile-1",
    display_name: "Writer", avatar_url: "", text: `${status} receipt body`,
    reply_to_message_id: "", sticker_resource_key: "", attachments: [], status,
    discord_message_id: "", reason: "", created_at: "2026-10-04T08:12:00Z",
    routing_status: "", ...next
  };
}

function state(next: Partial<WebRoomSessionState> = {}): WebRoomSessionState {
  return {
    authenticated: true, roomId: "room-1",
    rooms: [{ id: "room-1", name: "Test room", connection_id: "conn-1", guild_id: "guild-1", channel_id: "channel-1", thread_id: "", enabled: true, can_manage: false, can_post: true }],
    profiles: [{ id: "profile-1", display_name: "Writer", avatar_url: "", version: 1 }],
    profileId: "profile-1", snapshot: { room_id: "room-1", history_limit: 64, messages: [message()], outbox: [] },
    connection: "connected", unread: 3, text: "Shared draft", reply: "",
    attachments: [], stickerResourceKey: "", localSubmission: null,
    busy: false, error: "", demoMode: false, ...next
  };
}

function render(current = state(), language = "en", pip = true) {
  vi.stubGlobal("window", {
    location: { href: "https://relay.example/portal", origin: "https://relay.example" },
    localStorage: { getItem: () => language }
  });
  return renderToStaticMarkup(<I18nProvider><RoomCompanion state={current} session={new WebRoomSession()} onClose={vi.fn()} onOpenFull={vi.fn()} pip={pip} /></I18nProvider>);
}

function submitButton(markup: string): string {
  const buttons = [...markup.matchAll(/<button\b[^>]*type="submit"[^>]*>[\s\S]*?<\/button>/gu)];
  expect(buttons).toHaveLength(1);
  return buttons[0][0];
}

describe("Room Companion presentation contracts", () => {
  afterEach(() => vi.unstubAllGlobals());

  it.each(["connected", "reconnecting"])("allows a plain-text Send while %s", connection => {
    const button = submitButton(render(state({ connection })));
    expect(button).toContain(">Send</button>");
    expect(button).not.toMatch(/\sdisabled(?:=|\s|>)/u);
  });

  it.each([
    ["demo", { demoMode: true }],
    ["no authentication", { authenticated: false }],
    ["read-only room", { rooms: state().rooms.map(room => ({ ...room, can_post: false })) }],
    ["paused room", { rooms: state().rooms.map(room => ({ ...room, enabled: false })) }],
    ["unavailable", { connection: "unavailable" }],
    ["connecting", { connection: "connecting" }],
    ["no profile", { profiles: [] }],
    ["busy", { busy: true }],
    ["blank draft", { text: " \n " }],
    ["hidden attachment", { attachments: [{ id: "a", filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 1 }] }],
    ["hidden sticker", { stickerResourceKey: "sticker:1" }]
  ] satisfies [string, Partial<WebRoomSessionState>][])("blocks Quick Send for %s", (_name, overrides) => {
    expect(submitButton(render(state(overrides)))).toMatch(/\sdisabled=""/u);
  });

  it("explains a hidden payload and retains the same draft and structured reply", () => {
    const markup = render(state({ reply: "123", stickerResourceKey: "sticker:1", attachments: [{ id: "a", filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 1 }] }));
    expect(markup).toContain("The shared draft contains attachments or a sticker");
    expect(markup).toContain("Review full draft");
    expect(markup).toContain("Shared draft</textarea>");
    expect(markup).toContain("Replying to");
    expect(markup).toContain("Cancel reply");
  });

  it("exposes room, unread, connection and structured author/actor/reply IDs while showing latest five", () => {
    const messages = Array.from({ length: 7 }, (_, index) => message({ id: String(index), text: `Message ${index}`, reply_to_message_id: index === 6 ? "5" : "" }));
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages, outbox: [] } }));
    expect(markup).toContain('data-room-id="room-1"');
    expect(markup).toContain('data-connection-state="connected"');
    expect(markup).toContain('data-latest-message-id="6"');
    expect(markup).toContain('data-unread-count="3"');
    expect(markup).toContain('data-author-id="author-1"');
    expect(markup).toContain('data-actor-type="web_participant"');
    expect(markup).toContain('data-reply-to-message-id="5"');
    expect([...markup.matchAll(/data-message-id=/gu)]).toHaveLength(5);
    expect(markup).not.toContain("Message 0");
    expect(markup).not.toContain("Message 1");
    expect(markup).toContain("Message 6");
  });

  it("clears stale room presentation and disables sending after room loss", () => {
    const markup = render(state({ roomId: "", rooms: [], connection: "disconnected" }));
    expect(markup).not.toContain("Visible message");
    expect(markup).toContain("Choose a room in Rooms");
    expect(submitButton(markup)).toMatch(/\sdisabled=""/u);
  });

  it.each([
    ["deleted", { deleted: true }, "Message deleted"],
    ["unavailable", { content_available: false }, "Message content unavailable"]
  ] satisfies [string, Partial<WebMessage>, string][])("withholds %s body and attachments", (_name, flags, label) => {
    const hidden = message({ ...flags, text: "PRIVATE BODY", attachments: [{ attachment_id: "a", url: "https://example.com/private.png", proxy_url: "", filename: "PRIVATE FILE.png", description: "PRIVATE DESCRIPTION", content_type: "image/png", size_bytes: 1, width: 1, height: 1 }] });
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [hidden], outbox: [] } }));
    expect(markup).toContain(label);
    expect(markup).not.toContain("PRIVATE BODY");
    expect(markup).not.toContain("PRIVATE FILE");
    expect(markup).not.toContain("private.png");
    expect(markup).not.toContain('class="room-companion-reply-action"');
  });

  it("renders safe thumbnails and files without turning unsafe media into links", () => {
    const base = { attachment_id: "a", proxy_url: "", description: "", size_bytes: 1, width: 1, height: 1 };
    const withAttachments = message({ attachments: [
      { ...base, attachment_id: "image", url: "https://cdn.example/image.png", filename: "image.png", content_type: "image/png" },
      { ...base, attachment_id: "file", url: "/api/private/file", filename: "report.pdf", content_type: "application/pdf" },
      { ...base, attachment_id: "unsafe", url: "javascript:alert(1)", filename: "unsafe.png", content_type: "image/png" }
    ] });
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [withAttachments], outbox: [] } }));
    expect(markup).toContain('src="https://cdn.example/image.png"');
    expect(markup).toContain('href="https://relay.example/api/private/file"');
    expect(markup).toContain("report.pdf");
    expect(markup).toContain("unsafe.png");
    expect(markup).not.toContain("javascript:");
    expect(markup).toContain('referrerPolicy="no-referrer"');
  });

  it("keeps all six delivery states and distinguishes unknown acceptance with explicit safe retry", () => {
    const statuses: WebOutbox["status"][] = ["pending", "claimed", "delivered", "failed", "uncertain", "cancelled"];
    const current = state({
      snapshot: { room_id: "room-1", history_limit: 64, messages: [], outbox: statuses.map(status => receipt(status)) },
      localSubmission: { room: "room-1", payload: { client_message_id: "same-id", profile_id: "profile-1", text: "Original immutable payload", reply_to_message_id: "123", attachment_ids: [] }, phase: "unknown", displayName: "Writer", avatarUrl: "", attachments: [] }
    });
    const markup = render(current);
    for (const status of statuses) expect(markup).toContain(`data-delivery-status="${status}"`);
    expect(markup).toContain('data-delivery-status="unknown"');
    expect(markup).toContain('data-client-message-id="same-id"');
    expect(markup).toContain("same client message ID and original payload");
    expect(markup).toContain("Check / retry safely");
    expect(markup).toContain("It will not be resent automatically");
    expect(submitButton(markup)).toMatch(/\sdisabled=""/u);
  });

  it("suppresses echoed delivery receipts and prioritizes unresolved receipts in the bound", () => {
    const finalReceipts = Array.from({ length: 8 }, (_, index) => receipt("delivered", { id: `final-${index}`, client_message_id: `final-client-${index}` }));
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [message()], outbox: [receipt("delivered", { id: "echoed", discord_message_id: "123" }), ...finalReceipts, receipt("uncertain", { id: "unresolved" })] } }));
    expect(markup).not.toContain('data-outbox-id="echoed"');
    expect(markup).toContain('data-outbox-id="unresolved"');
    expect([...markup.matchAll(/data-outbox-id=/gu)]).toHaveLength(8);
    expect(markup).toContain("View more delivery receipts in full room");
  });

  it("localizes controls and explains the in-app fallback", () => {
    const markup = render(state(), "zh-CN", false);
    expect(markup).toContain("打开完整房间");
    expect(markup).toContain("关闭房间伴随窗口");
    expect(markup).toContain("最小化房间伴随窗口");
    expect(markup).toContain("应用内伴随面板");
    expect(submitButton(markup)).toContain("发送");
  });

  it("removes only a leading transport URL that matches an already displayed structured reply", () => {
    const reply_preview = { message_id: "456", available: true, in_snapshot: true, display_name: "Original author", summary: "Original summary" };
    const original = message({ text: "↪ https://discord.com/channels/1/2/456\n\nActual reply", reply_to_message_id: "456", reply_preview });
    expect(companionMessageText(original)).toBe("Actual reply");
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [original], outbox: [] } }));
    expect(markup).toContain("Original summary");
    expect(markup).toContain("Actual reply");
    expect(markup).not.toContain("discord.com/channels");
    expect(companionMessageText({ ...original, reply_to_message_id: "789" })).toBe(original.text);
    expect(companionMessageText({ ...original, reply_preview: null })).toBe(original.text);
    expect(companionMessageText({ ...original, text: `User prose\n${original.text}` })).toBe(`User prose\n${original.text}`);
  });
});
