import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "./i18n";
import { RoomCompanion, companionMessageText } from "./RoomCompanion";
import { RoomCompanionSizeControls, type RoomCompanionSizeOptions } from "./RoomCompanionSizeControls";
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

function render(current = state(), language = "en", pip = true, sizeControls?: RoomCompanionSizeOptions) {
  vi.stubGlobal("window", {
    location: { href: "https://relay.example/portal", origin: "https://relay.example" },
    localStorage: { getItem: () => language }
  });
  return renderToStaticMarkup(<I18nProvider><RoomCompanion state={current} session={new WebRoomSession()} onClose={vi.fn()} onOpenFull={vi.fn()} pip={pip} sizeControls={sizeControls} /></I18nProvider>);
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
    const hidden = message({
      ...flags, text: "PRIVATE BODY",
      attachments: [{ attachment_id: "a", url: "https://example.com/private.png", proxy_url: "", filename: "PRIVATE FILE.png", description: "PRIVATE DESCRIPTION", content_type: "image/png", size_bytes: 1, width: 1, height: 1 }],
      embeds: [{ embed_type: "gifv", url: "https://example.com/private.gif", title: "PRIVATE EMBED", description: "PRIVATE MEDIA DESCRIPTION", provider_name: "", author_name: "", image_url: "https://example.com/private.gif", image_proxy_url: "", thumbnail_url: "", thumbnail_proxy_url: "" }]
    });
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [hidden], outbox: [] } }));
    expect(markup).toContain(label);
    expect(markup).not.toContain("PRIVATE BODY");
    expect(markup).not.toContain("PRIVATE FILE");
    expect(markup).not.toContain("private.png");
    expect(markup).not.toContain("PRIVATE EMBED");
    expect(markup).not.toContain("PRIVATE MEDIA DESCRIPTION");
    expect(markup).not.toContain("private.gif");
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

  it("renders custom emoji and mentions like the full room, with readable names and safe assets", () => {
    const rich = message({
      text: "Hi <@42> <:wave:11> <a:dance:22> <script>bad</script>",
      mentions: [{ kind: "user", target_id: "42", label: "Alice" }],
      custom_emojis: [{ resource_key: "emoji:11", resource_type: "emoji", resource_id: "11", name: "hello", animated: false, asset_url: "javascript:bad()", format_type: "", description: "" }]
    });
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [rich], outbox: [] } }));
    expect(markup).toContain('src="https://cdn.discordapp.com/emojis/11.png"');
    expect(markup).toContain('alt=":hello:"');
    expect(markup).toContain('src="https://cdn.discordapp.com/emojis/22.gif"');
    expect(markup).toContain('alt=":dance:"');
    expect(markup).toContain("@Alice");
    expect(markup).not.toContain("javascript:");
    expect(markup).not.toContain("&lt;:wave:11&gt;");
    expect(markup).toContain("&lt;script&gt;bad&lt;/script&gt;");
  });

  it("exposes GIF descriptions and explicit viewing links for attachments and embeds", () => {
    const media = message({
      attachments: [{ attachment_id: "gif", url: "https://cdn.example/reaction.gif", proxy_url: "", filename: "reaction.gif", description: "A synthetic waving character", content_type: "image/gif", size_bytes: 10, width: 20, height: 20 }],
      embeds: [{ embed_type: "gifv", url: "https://example.com/gif", title: "Reaction", description: "A synthetic celebration", provider_name: "", author_name: "", image_url: "https://cdn.example/preview.png", image_proxy_url: "", thumbnail_url: "", thumbnail_proxy_url: "" }]
    });
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [media], outbox: [] } }));
    expect(markup).toContain("GIF · reaction.gif");
    expect(markup).toContain("<span>A synthetic waving character</span>");
    expect(markup).toContain("<span>A synthetic celebration</span>");
    expect(markup.match(/View GIF · opens a new tab/gu)).toHaveLength(2);
    expect(markup).toContain('href="https://example.com/gif" target="_blank" rel="noreferrer"');
    expect(markup).not.toContain("No description provided");
  });

  it("labels missing descriptions honestly and rejects unsafe embed media and links", () => {
    const embed = { embed_type: "gifv", url: "javascript:bad()", title: "Safe title", description: "", provider_name: "", author_name: "", image_url: "javascript:bad()", image_proxy_url: "", thumbnail_url: "", thumbnail_proxy_url: "" };
    const media = message({
      attachments: [{ attachment_id: "gif", url: "https://cdn.example/reaction.gif", proxy_url: "", filename: "reaction.gif", description: "", content_type: "image/gif", size_bytes: 1, width: 1, height: 1 }],
      embeds: [embed]
    });
    const markup = render(state({ snapshot: { room_id: "room-1", history_limit: 64, messages: [media], outbox: [] } }));
    expect(markup).toContain("No description provided");
    expect(markup).toContain("Safe title");
    expect(markup).not.toContain("javascript:");
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

  it("offers a collapsed size disclosure only for a native window with a resize callback", () => {
    const sizeControls = { size: { width: 380, height: 480 }, onResize: vi.fn(() => true) };
    const markup = render(state(), "en", true, sizeControls);
    expect(markup).toMatch(/<button[^>]*data-companion-size-toggle="true"[^>]*aria-expanded="false"[^>]*>Window size<\/button>/u);
    expect(markup).not.toContain('class="room-companion-size-controls"');
    expect(submitButton(markup)).toContain(">Send</button>");
    expect(render(state(), "en", false, sizeControls)).not.toContain("Window size");
    expect(render()).not.toContain("Window size");
    expect(render(state(), "zh-CN", true, sizeControls)).toContain("窗口尺寸");
  });

  it.each(["en", "zh-CN"])("offers a direct resize action only when the native actual size differs from the selection in %s", language => {
    const sizeControls = { size: { width: 1083, height: 781 }, preferredSize: { width: 380, height: 480 }, onResize: vi.fn(() => true) };
    const markup = render(state(), language, true, sizeControls);
    expect(markup).toMatch(/<button[^>]*data-companion-restore-size="true"/u);
    expect(markup).toContain(language === "en" ? ">Use 380×480</button>" : ">应用 380×480</button>");
    expect(markup).toContain(language === "en" ? "Browser kept a different size" : "浏览器窗口尺寸与所选不同");
    expect(markup).not.toContain('class="room-companion-size-controls"');
    expect(submitButton(markup)).toContain(language === "en" ? "Send" : "发送");
    expect(render(state(), language, true, { ...sizeControls, size: { ...sizeControls.preferredSize } })).not.toContain('data-companion-restore-size="true"');
    expect(render(state(), language, false, sizeControls)).not.toContain('data-companion-restore-size="true"');
    expect(render(state(), language, true, { size: sizeControls.size, onResize: sizeControls.onResize })).not.toContain('data-companion-restore-size="true"');
  });

  it.each(["en", "zh-CN"])("labels content dimensions, actual size and browser limits in %s", language => {
    render(state(), language);
    const markup = renderToStaticMarkup(<I18nProvider><RoomCompanionSizeControls id="size-panel" size={{ width: 612, height: 494 }} onResize={vi.fn(() => true)} /></I18nProvider>);
    expect(markup).toContain('id="size-panel"');
    expect(markup).toContain('data-companion-reader-ignore="true"');
    expect(markup).toContain('data-companion-size-current="true"');
    expect(markup).toContain("612×494");
    const widthInput = markup.match(/<input\b[^>]*name="width"[^>]*>/u)?.[0];
    const heightInput = markup.match(/<input\b[^>]*name="height"[^>]*>/u)?.[0];
    expect(widthInput).toContain('type="number"');
    expect(widthInput).toContain('min="320" max="2000" step="1"');
    expect(widthInput).toContain('value="612"');
    expect(heightInput).toContain('type="number"');
    expect(heightInput).toContain('min="320" max="1600" step="1"');
    expect(heightInput).toContain('value="494"');
    expect(markup).toContain("380×480");
    expect(markup).toContain("480×640");
    expect(markup).toContain(language === "en" ? "Width (content px)" : "宽度（内容区像素）");
    expect(markup).toContain(language === "en" ? "Height (content px)" : "高度（内容区像素）");
    expect(markup).toContain(language === "en" ? "Browser may limit size" : "浏览器可能限制尺寸");
    expect(submitButton(markup)).toContain(language === "en" ? "Apply size" : "应用尺寸");
    expect(markup).not.toContain("Shared draft");
    expect(markup).not.toContain("<textarea");
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
