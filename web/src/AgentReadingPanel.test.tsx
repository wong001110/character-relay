import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentReadingPanel } from "./AgentReadingPanel";
import { WebRoomSession, type WebRoomSessionState } from "./webRoomSession";

const state = (next: Partial<WebRoomSessionState> = {}): WebRoomSessionState => ({
  authenticated: true, demoMode: false, roomId: "r", rooms: [{id: "r", name: "Room", connection_id: "c", guild_id: "g", channel_id: "ch", thread_id: "", enabled: true, can_manage: false, can_post: true}],
  profiles: [{id: "p", display_name: "Dots", avatar_url: "", version: 1}], profileId: "p", snapshot: {room_id: "r", messages: [], outbox: [], history_limit: 64},
  connection: "connected", unread: 0, text: "", reply: "", attachments: [], stickerResourceKey: "", localSubmission: null, busy: false, error: "",
  agentReading: {enabled: true, pendingCount: 2}, ...next
});
const render = (next = state()) => renderToStaticMarkup(<AgentReadingPanel state={next} session={new WebRoomSession()} tx={english => english} />);

describe("session counter HTML", () => {
  it("exposes readable room, participant, count and clear without a batch or processing ledger", () => {
    const html = render();
    expect(html).toContain('data-status="pending"'); expect(html).toContain('data-pending-count="2"');
    expect(html).toContain('data-agent-summary="true"'); expect(html).toContain("Room: Room (r)"); expect(html).toContain("Participant: Dots (p)");
    expect(html).toContain("New messages this session: 2"); expect(html).toContain("Done · clear reminders");
    expect(html).not.toContain("Read batch"); expect(html).not.toContain("Completed through revision");
    expect(html).toContain("Refreshing or rejoining starts at zero");
  });
  it.each(["connecting", "reconnecting", "disconnected", "unavailable"])("shows %s independently of a zero count", connection => {
    const html = render(state({connection, agentReading: {enabled: true, pendingCount: 0}}));
    expect(html).toContain('data-status="disconnected"'); expect(html).toContain(`data-connection="${connection}"`);
    expect(html).toContain("incoming messages may be missed"); expect(html).not.toContain("No new messages counted");
  });
  it("only calls a connected zero idle", () => {
    expect(render(state({agentReading: {enabled: true, pendingCount: 0}}))).toContain('data-status="idle"');
  });
  it("disables activation in demo mode and without a participant", () => {
    for (const next of [{demoMode: true}, {profileId: ""}]) {
      const html = render(state({...next, agentReading: undefined}));
      expect(html).toMatch(/<button[^>]*disabled=""[^>]*data-agent-toggle="true"/u);
      expect(html).not.toContain('data-agent-clear="true"');
    }
  });
});
