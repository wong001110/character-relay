import { afterEach, describe, expect, it, vi } from "vitest";
import { WEB_ROOM_ATTACHMENT_ACCEPT, snapshotForRoomTransition, webRoomApi, webRoomCanSubmit, unmatchedOutbox, withAcceptedOutbox, type WebSnapshot } from "./webRoomApi";
describe("web room client contracts", () => {
 afterEach(() => vi.unstubAllGlobals());
 it("posts a stable idempotency key, owned profile and exact escaped room using the session", async () => {
  const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({status:"pending"})))); vi.stubGlobal("fetch", fetcher);
  const payload = {client_message_id:"stable-key",profile_id:"my-profile",text:"Hi",reply_to_message_id:"m1"};
  await webRoomApi.send("a/b", payload); await webRoomApi.send("a/b", payload);
  expect(fetcher.mock.calls[0][0]).toBe("/api/web-chat/rooms/a%2Fb/messages");
  expect(fetcher.mock.calls[0][1].credentials).toBe("same-origin");
  expect(fetcher.mock.calls[0][1].body).toBe(fetcher.mock.calls[1][1].body);
  expect(fetcher.mock.calls[0][1].body).not.toContain("webhook");
 });
 it("surfaces a successful POST immediately without waiting for SSE", () => {
  const snapshot = {room_id:"r",history_limit:64,messages:[],outbox:[{id:"old",client_message_id:"old"}]} as unknown as WebSnapshot;
  const accepted = {id:"new",client_message_id:"stable-key",status:"pending"} as unknown as WebSnapshot["outbox"][number];
  const next = withAcceptedOutbox(snapshot, "r", accepted);
  expect(next.outbox.map(item => item.id)).toEqual(["new","old"]);
  expect(withAcceptedOutbox(snapshot, "other", accepted)).toBe(snapshot);
 });
 it("uploads attachment bytes without routing them through the JSON helper", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({id:"a1",filename:"notes.pdf",mime_type:"application/pdf",size_bytes:3}),{status:201}));
  vi.stubGlobal("fetch", fetcher);
  const file = new File([new Uint8Array([1,2,3])], "notes.pdf", {type:"application/pdf"});
  const result = await webRoomApi.uploadAttachment("r/1", file);
  expect(result.id).toBe("a1");
  expect(fetcher.mock.calls[0][0]).toBe("/api/web-chat/rooms/r%2F1/attachments");
  expect(fetcher.mock.calls[0][1].body).toBe(file);
  expect(fetcher.mock.calls[0][1].headers["Content-Type"]).toBe("application/pdf");
  expect(WEB_ROOM_ATTACHMENT_ACCEPT).toContain(".pdf");
  expect(WEB_ROOM_ATTACHMENT_ACCEPT).toContain(".zip");
 });
 it("keeps unconfirmed sends but removes the receipt when its echo is present", () => {
  const snapshot = {room_id:"r",history_limit:64,messages:[{id:"discord1"}],outbox:[{id:"one",discord_message_id:"discord1",status:"delivered"},{id:"two",discord_message_id:"",status:"uncertain"}]} as unknown as WebSnapshot;
  expect(unmatchedOutbox(snapshot).map(item => item.id)).toEqual(["two"]);
 });
 it("preserves the current room while reconnecting but clears on a real room change", () => {
  const current = {room_id:"room-a",history_limit:64,messages:[{id:"m1"}],outbox:[]} as unknown as WebSnapshot;
  expect(snapshotForRoomTransition(current, "room-a")).toBe(current);
  expect(snapshotForRoomTransition(current, "room-b")).toEqual({
   room_id:"",history_limit:64,messages:[],outbox:[]
  });
 });
 it("uses a same-origin stream URL without a token in the URL", () => {
  expect(webRoomApi.eventsUrl("r/1")).toBe("/api/web-chat/rooms/r%2F1/events");
 });
 it("keeps REST send available during the normal SSE reconnect window", () => {
  expect(webRoomCanSubmit("connected")).toBe(true);
  expect(webRoomCanSubmit("reconnecting")).toBe(true);
  expect(webRoomCanSubmit("connecting")).toBe(false);
  expect(webRoomCanSubmit("disconnected")).toBe(false);
  expect(webRoomCanSubmit("unavailable")).toBe(false);
 });
 it("version-binds profile updates and escapes revocation identity", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null,{status:204})); vi.stubGlobal("fetch",fetcher);
  await webRoomApi.profile({display_name:"New",avatar_url:""},{id:"p/1",display_name:"Old",avatar_url:"",version:4});
  expect(JSON.parse(fetcher.mock.calls[0][1].body).expected_version).toBe(4);
  await webRoomApi.revoke("room","user/other"); expect(fetcher.mock.calls[1][0]).toBe("/api/web-chat/rooms/room/members/user%2Fother");
 });
});
