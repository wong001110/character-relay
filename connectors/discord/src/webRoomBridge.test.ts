import { describe, expect, it, vi } from "vitest";
import { deliverWebMessage, webMessageText, webSendFailure, type WebBridgeTransport, type WebClaim } from "./webRoomBridge.js";
const claim: WebClaim = {id: "send1", room_id: "room1", claim_nonce: "nonce1234567890123", profile_id: "profile1", actor_id: "web:profile1", display_name: "Ann", avatar_url: "https://cdn.discordapp.com/a.png", text: "Hello @everyone", reply_to_message_id: "", guild_id: "guild1", channel_id: "channel1", thread_id: "", webhook_id: "hook1", discord_message_id: "", created_at: "2026-10-02T00:00:00Z"};
function fixture() {
 const transport: WebBridgeTransport = {webRooms: vi.fn(), registerWebRoomWebhook: vi.fn(), claimWebMessage: vi.fn(), preflightWebMessage: vi.fn().mockResolvedValue({allowed: true}), acknowledgeWebMessage: vi.fn().mockResolvedValue({}), webDispatch: vi.fn(), finishWebDispatch: vi.fn(), observeRoom: vi.fn()};
 const effects = {canSend: vi.fn().mockResolvedValue(true), send: vi.fn().mockResolvedValue({id: "discord1", webhook_id: "hook1", created_at: "2026-10-02T00:00:00Z"})};
 return {transport, effects};
}
describe("web participant one-shot send", () => {
 it("does not send before both current platform permission and backend grant pass", async () => {
   const {transport, effects} = fixture(); vi.mocked(transport.preflightWebMessage).mockResolvedValue({allowed: false});
   await deliverWebMessage(claim, transport, effects);
   expect(effects.send).not.toHaveBeenCalled(); expect(transport.acknowledgeWebMessage).toHaveBeenCalledWith(claim, {status:"cancelled",reason:"send_preflight_denied"});
 });
 it("never sends after the platform revokes access", async () => {
   const {transport, effects} = fixture(); effects.canSend.mockResolvedValue(false);
   await deliverWebMessage(claim, transport, effects); expect(effects.send).not.toHaveBeenCalled();
 });
 it("waits for one receipt, retries only identical acknowledgement", async () => {
   const {transport, effects} = fixture(); vi.mocked(transport.acknowledgeWebMessage).mockRejectedValueOnce(new Error("lost ack"));
   await deliverWebMessage(claim, transport, effects);
   expect(effects.send).toHaveBeenCalledTimes(1); expect(transport.acknowledgeWebMessage).toHaveBeenCalledTimes(2);
   expect(vi.mocked(transport.acknowledgeWebMessage).mock.calls[0]).toEqual(vi.mocked(transport.acknowledgeWebMessage).mock.calls[1]);
 });
 it("preserves uncertain network effects instead of issuing a second webhook send", async () => {
   const {transport, effects} = fixture(); effects.send.mockRejectedValue(new Error("socket closed"));
   await deliverWebMessage(claim, transport, effects); expect(effects.send).toHaveBeenCalledTimes(1);
   expect(transport.acknowledgeWebMessage).toHaveBeenCalledWith(claim, {status:"uncertain",reason:"discord_receipt_unavailable"});
 });
 it("rejects a mismatched webhook receipt as uncertainty", async () => {
   const {transport, effects} = fixture(); effects.send.mockResolvedValue({id:"one",webhook_id:"other",created_at:"2026-10-02T00:00:00Z"});
   await deliverWebMessage(claim, transport, effects); expect(vi.mocked(transport.acknowledgeWebMessage).mock.calls[0]?.[1].status).toBe("uncertain");
 });
 it("cannot repair permanent acknowledgement failure by re-sending", async () => {
   const {transport, effects} = fixture(); vi.mocked(transport.acknowledgeWebMessage).mockRejectedValue(new Error("db down"));
   await expect(deliverWebMessage(claim, transport, effects)).rejects.toThrow("db down"); expect(effects.send).toHaveBeenCalledTimes(1);
 });
 it("builds native-thread source links without pretending to issue a native Reply", () => {
   expect(webMessageText({...claim,thread_id:"thread1",reply_to_message_id:"target1"})).toBe("↪ https://discord.com/channels/guild1/thread1/target1\nHello @everyone");
   expect(() => webMessageText({...claim, text:"x".repeat(2001)})).toThrow();
 });
 it("distinguishes explicit HTTP rejection from an unknown 5xx effect", () => {
   expect(webSendFailure({status:429}).status).toBe("failed"); expect(webSendFailure({status:503}).status).toBe("uncertain");
 });
});
