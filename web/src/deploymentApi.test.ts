import { describe, expect, it, vi } from "vitest";

import {
  deploymentApi,
  NEW_CONNECTION_PLATFORM,
  type PlatformConnectionCreate
} from "./deploymentApi";

function connectionPayload(platform: PlatformConnectionCreate["platform"]): PlatformConnectionCreate {
  return {
    platform,
    display_name: "Legacy connector",
    connection_mode: "managed",
    external_account_id: "",
    status: "disconnected",
    metadata: {}
  };
}

describe("deploymentApi connection creation", () => {
  it("keeps Discord as the only new Portal connection platform", async () => {
    expect(NEW_CONNECTION_PLATFORM).toBe("discord");
    await expect(deploymentApi.createConnection(connectionPayload("whatsapp"))).rejects.toThrow(
      "Only Discord connections can be created"
    );
    await expect(deploymentApi.createConnection(connectionPayload("telegram"))).rejects.toThrow(
      "Only Discord connections can be created"
    );
  });

  it("sends new Discord connections to the existing endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "discord-1" }), { status: 201 })
    );
    await deploymentApi.createConnection(connectionPayload("discord"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/connections",
      expect.objectContaining({ method: "POST" })
    );
    fetchMock.mockRestore();
  });
});
