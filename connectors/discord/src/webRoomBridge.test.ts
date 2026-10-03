import { describe, expect, it, vi } from "vitest";
import { deliverWebMessage, webMessageFiles, webMessageText, webSendFailure, type WebBridgeTransport, type WebClaim } from "./webRoomBridge.js";
const claim: WebClaim = {id: "send1", room_id: "room1", claim_nonce: "nonce1234567890123", profile_id: "profile1", actor_id: "web:profile1", display_name: "Ann", avatar_url: "https://cdn.discordapp.com/a.png", text: "Hello @everyone", reply_to_message_id: "", guild_id: "guild1", channel_id: "channel1", thread_id: "", webhook_id: "hook1", discord_message_id: "", created_at: "2026-10-02T00:00:00Z"};
function fixture() {
 const transport: WebBridgeTransport = {webRooms: vi.fn(), registerWebRoomWebhook: vi.fn(), claimWebMessage: vi.fn(), preflightWebMessage: vi.fn().mockResolvedValue({allowed: true}), acknowledgeWebMessage: vi.fn().mockResolvedValue({}), fetchWebAttachment: vi.fn().mockResolvedValue(Buffer.from("image")), webDispatch: vi.fn(), finishWebDispatch: vi.fn(), observeRoom: vi.fn()};
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
 it("uses a bounded readable reply fallback instead of a bare Discord URL", () => {
   const replyClaim = {...claim,thread_id:"thread1",reply_to_message_id:"target1"};
   expect(webMessageText(replyClaim,{display_name:"Bob",summary:"Earlier message"})).toBe("↪ Replying to Bob: Earlier message\nHello @everyone");
   expect(() => webMessageText(replyClaim)).toThrow("web_reply_context_required");
   expect(() => webMessageText({...claim, text:"x".repeat(2001)})).toThrow();
 });
 it("cancels a reply when the referenced source cannot be resolved", async () => {
   const {transport, effects} = fixture();
   const replyClaim = {...claim, reply_to_message_id:"target1"};
   const replyEffects = {...effects, resolveReply: vi.fn().mockResolvedValue(null)};
   await deliverWebMessage(replyClaim, transport, replyEffects);
   expect(replyEffects.send).not.toHaveBeenCalled();
   expect(transport.acknowledgeWebMessage).toHaveBeenCalledWith(replyClaim, {status:"cancelled",reason:"reply_source_unavailable"});
 });
 it("sends reply fallback text from the resolved parent context", async () => {
   const {transport, effects} = fixture();
   const replyClaim = {...claim, reply_to_message_id:"target1"};
   const replyEffects = {...effects, resolveReply: vi.fn().mockResolvedValue({display_name:"Bob",summary:"Earlier message"})};
   await deliverWebMessage(replyClaim, transport, replyEffects);
   expect(replyEffects.send).toHaveBeenCalledWith("↪ Replying to Bob: Earlier message\nHello @everyone", replyClaim);
 });
 it("supports an image-only message and binds its bytes to the claimed attachment metadata", async () => {
   const {transport} = fixture();
   const imageClaim = {
     ...claim,
     text:"",
     attachments:[{id:"artifact-1",filename:"cat.png",mime_type:"image/png",size_bytes:5}]
   };
   expect(webMessageText(imageClaim)).toBe("");
   const files = await webMessageFiles(imageClaim, transport);
   expect(transport.fetchWebAttachment).toHaveBeenCalledWith(imageClaim, "artifact-1");
   expect(files).toEqual([{attachment:Buffer.from("image"),name:"cat.png"}]);
 });
 it("rejects attachment byte lengths that do not match the server claim", async () => {
   const {transport} = fixture();
   const imageClaim = {
     ...claim,
     text:"",
     attachments:[{id:"artifact-1",filename:"cat.png",mime_type:"image/png",size_bytes:6}]
   };
   await expect(webMessageFiles(imageClaim, transport)).rejects.toThrow("web_attachment_size_mismatch");
 });
 it("supports a validated sticker-only webhook effect without inventing text", async () => {
   const {transport, effects} = fixture();
   const stickerClaim = {
     ...claim,
     text:"",
     sticker_resource_key:"sticker:1",
     sticker_name:"Smile",
     sticker_asset_url:"https://cdn.discordapp.com/stickers/1.png",
     sticker_format_type:"png"
   };
   expect(webMessageText(stickerClaim)).toBe("");
   await deliverWebMessage(stickerClaim, transport, effects);
   expect(effects.send).toHaveBeenCalledWith("", stickerClaim);
   expect(transport.acknowledgeWebMessage).toHaveBeenCalledWith(
     stickerClaim,
     expect.objectContaining({status:"delivered"})
   );
 });
 it("distinguishes explicit HTTP rejection from an unknown 5xx effect", () => {
   expect(webSendFailure({status:429}).status).toBe("failed"); expect(webSendFailure({status:503}).status).toBe("uncertain");
 });
});
