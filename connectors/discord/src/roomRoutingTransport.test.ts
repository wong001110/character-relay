import { afterEach, describe, expect, it, vi } from "vitest";
import { RelayClient } from "./relayClient.js";
import { loadConfig } from "./config.js";
import type { RoomRoutingRequest } from "./roomEvidence.js";

const request: RoomRoutingRequest = {
  guild_id: "guild", channel_id: "channel", thread_id: "private-thread", category_id: "",
  request_id: "request", trigger_message_id: "message", deployment_ids: ["ann"],
  explicit_deployment_ids: ["ann"], ambient_requested: false, readable: true,
  permission_checked_at: "2026-10-02T00:00:00Z", messages: []
};
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
describe("one Room Routing transport", () => {
  it("refreshes deployments without querying retired profile or semantic APIs", async () => {
    const fetch = vi.fn(async (_input: unknown) => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    expect(await new RelayClient("https://relay.test", "test-token", "conn").listDeployments()).toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(fetch.mock.calls[0]?.[0])).toBe("https://relay.test/api/connectors/discord/deployments?connection_id=conn");
  });
  it("preserves room/source/actor data on the only route request", async () => {
    const result={outcome:"none",reason:"nothing_to_contribute",choices:[],attempts:[],route_id:"route",snapshot_revision:1,prompt_version:"v1",input_fingerprint:"hash"};
    const calls: Array<{url:string; body:Record<string,unknown>}> = [];
    vi.stubGlobal("fetch",vi.fn(async (url:string,init?:RequestInit)=>{
      calls.push({url,body:JSON.parse(String(init?.body))});return new Response(JSON.stringify(result),{status:200});
    }));
    const reply=await new RelayClient("https://relay.test","test-token","conn").resolveRoom(request);
    expect(reply).toEqual(result);
    expect(calls).toEqual([{url:"https://relay.test/api/connectors/discord/rooms/resolve",body:{...request,connection_id:"conn"}}]);
  });
  it("does not replace an unavailable Director with a retired Planner request", async () => {
    const fetch=vi.fn(async()=>new Response("unavailable",{status:503}));vi.stubGlobal("fetch",fetch);
    await expect(new RelayClient("https://relay.test","test-token","conn").resolveRoom(request)).rejects.toThrow("HTTP 503");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
describe("bounded room configuration",()=>{
  const base=()=>{vi.stubEnv("DISCORD_BOT_TOKEN","test-token");vi.stubEnv("CHARACTER_RELAY_API_URL","https://relay.test");vi.stubEnv("CHARACTER_RELAY_CONNECTOR_TOKEN","test-token");vi.stubEnv("CHARACTER_RELAY_CONNECTION_ID","conn");};
  it("defaults to no ambient participation and finite continuation",()=>{
    base();const config=loadConfig();expect(config.ambientParticipationEnabled).toBe(false);
    expect(config.conversationMaxResponses).toBe(6);
    expect(config).not.toHaveProperty("smartParticipationProfiles");
  });
  it.each(["1.5","12ms","Infinity","0"])("rejects malformed room budget %s",raw=>{
    base();vi.stubEnv("DISCORD_CONVERSATION_MAX_RESPONSES",raw);expect(()=>loadConfig()).toThrow();
  });
  it("does not read old profile JSON or implicitly enable ambient",()=>{
    base();vi.stubEnv("DISCORD_SMART_PARTICIPATION_ENABLED","true");vi.stubEnv("DISCORD_SMART_PARTICIPATION_PROFILES_JSON","{broken}");
    expect(loadConfig().ambientParticipationEnabled).toBe(false);
  });
});
