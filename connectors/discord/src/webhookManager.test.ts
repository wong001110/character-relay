import { afterEach, describe, expect, it, vi } from "vitest";

import type { RelayClient } from "./relayClient.js";
import type { DiscordDeployment } from "./types.js";
import { DiscordWebhookManager } from "./webhookManager.js";

function deployment(): DiscordDeployment {
  return {
    deployment_id: "deployment-1",
    connection_id: "connection-1",
    character_card_id: "character-1",
    character_display_name: "Ann",
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "ann-room",
    thread_id: "thread-1",
    thread_name: "Scene",
    category_id: "category-1",
    server_profile_id: "",
    channel_scope_mode: "exact",
    excluded_channel_ids: [],
    excluded_category_ids: [],
    participation_mode: "mention_and_reply",
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: "Ann",
    identity_avatar_url: "https://example.com/ann.png",
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DiscordWebhookManager", () => {
  it("creates, registers, and executes a character webhook in a thread", async () => {
    const registerWebhook = vi.fn().mockResolvedValue({
      binding_id: "binding-1",
      webhook_id: "webhook-1",
      webhook_token: "token-1",
      status: "active"
    });
    const reportWebhookStatus = vi.fn().mockResolvedValue(undefined);
    const relay = {
      registerWebhook,
      reportWebhookStatus
    } as unknown as RelayClient;

    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "webhook-1",
            type: 1,
            token: "token-1",
            user: { id: "bot-1" }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "message-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      );

    const item = deployment();
    const manager = new DiscordWebhookManager("bot-token", relay);
    const messageIds = await manager.send(item, ["Hello from Ann"], "bot-1");

    expect(messageIds).toEqual(["message-1"]);
    expect(registerWebhook).toHaveBeenCalledWith({
      deployment_id: "deployment-1",
      workspace_id: "guild-1",
      channel_id: "channel-1",
      category_id: "category-1",
      thread_id: "thread-1",
      webhook_id: "webhook-1",
      webhook_token: "token-1"
    });
    expect(item.webhook_status).toBe("active");

    const executeCall = fetchMock.mock.calls[2];
    expect(String(executeCall?.[0])).toContain(
      "/webhooks/webhook-1/token-1?wait=true&thread_id=thread-1"
    );
    const init = executeCall?.[1] as RequestInit;
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      content: "Hello from Ann",
      username: "Ann",
      avatar_url: "https://example.com/ann.png",
      allowed_mentions: { parse: [] }
    });
  });

  it("returns every chunk message id for persistent reply routing", async () => {
    const relay = {
      reportWebhookStatus: vi.fn().mockResolvedValue(undefined)
    } as unknown as RelayClient;
    const item = deployment();
    item.webhook_id = "webhook-1";
    item.webhook_token = "token-1";
    item.webhook_status = "active";
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "message-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "message-2" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      );

    const manager = new DiscordWebhookManager("bot-token", relay);
    await expect(manager.send(item, ["one", "two"], "bot-1")).resolves.toEqual([
      "message-1",
      "message-2"
    ]);
  });
});
