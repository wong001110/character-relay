import { afterEach, describe, expect, it, vi } from "vitest";

import { RelayClient } from "./relayClient.js";
import type { DiscordInboundMessage } from "./types.js";

const payload: Omit<DiscordInboundMessage, "connection_id"> = {
  deployment_id: "deployment-1",
  message_id: "message-1",
  guild_id: "guild-1",
  guild_name: "Guild",
  channel_id: "channel-1",
  channel_name: "general",
  category_id: "",
  thread_id: "",
  thread_name: "",
  author_id: "user-1",
  author_display_name: "Member",
  text: "look at this",
  emojis: [],
  mentioned_bot: true,
  replied_to_bot: false,
  smart_candidate: false,
  author_is_bot: false,
  stickers: [],
  available_characters: [],
  mentionable_participants: [],
  recent_messages: [],
  interaction_session_id: "",
  interaction_type: "",
  interaction_intensity: "",
  interaction_round: 0,
  interaction_total_rounds: 0,
  interaction_position: 0,
  interaction_participant_count: 0,
  interaction_target_user_id: "",
  interaction_target_display_name: "",
  expression_run_id: "",
  expression_candidates: []
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("RelayClient media enrichment", () => {
  it("adds attachments and Discord link previews while caching one message lookup", async () => {
    vi.stubEnv("DISCORD_BOT_TOKEN", "discord-token");
    const backendBodies: Array<Record<string, unknown>> = [];
    let discordCalls = 0;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        if (url.startsWith("https://discord.com/api/v10/")) {
          discordCalls += 1;
          expect(init?.headers).toEqual(
            expect.objectContaining({ Authorization: "Bot discord-token" })
          );
          return new Response(
            JSON.stringify({
              attachments: [
                {
                  id: "attachment-1",
                  url: "https://cdn.discordapp.com/attachments/a/b/cat.png",
                  proxy_url: "https://media.discordapp.net/attachments/a/b/cat.png",
                  filename: "cat.png",
                  content_type: "image/png",
                  size: 12345,
                  width: 640,
                  height: 480
                }
              ],
              embeds: [
                {
                  type: "video",
                  url: "https://www.bilibili.com/video/BV1abc/",
                  title: "Cherry Studio V2 来了，超详细攻略",
                  description: "真实使用场景分享",
                  provider: { name: "哔哩哔哩" },
                  author: { name: "技术爬爬虾" }
                }
              ]
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url === "https://relay.test/api/connectors/discord/messages") {
          const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
          backendBodies.push(body);
          return new Response(
            JSON.stringify({
              action: "silent",
              reason: "test",
              expression: { action: "none", reason: "test" },
              tool_calls: []
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        throw new Error(`Unexpected fetch: ${url}`);
      })
    );

    const client = new RelayClient("https://relay.test", "connector-token", "conn-1");
    await client.processMessage(payload);
    await client.processMessage(payload);

    expect(discordCalls).toBe(1);
    expect(backendBodies).toHaveLength(2);
    for (const body of backendBodies) {
      expect(body.connection_id).toBe("conn-1");
      expect(body.attachments).toEqual([
        {
          attachment_id: "attachment-1",
          url: "https://cdn.discordapp.com/attachments/a/b/cat.png",
          proxy_url: "https://media.discordapp.net/attachments/a/b/cat.png",
          filename: "cat.png",
          content_type: "image/png",
          size_bytes: 12345,
          width: 640,
          height: 480
        }
      ]);
      expect(body.embeds).toEqual([
        {
          embed_type: "video",
          url: "https://www.bilibili.com/video/BV1abc/",
          title: "Cherry Studio V2 来了，超详细攻略",
          description: "真实使用场景分享",
          provider_name: "哔哩哔哩",
          author_name: "技术爬爬虾"
        }
      ]);
    }
  });

  it("does not retry a generation POST after a transient response", async () => {
    const fetchMock = vi.fn(async () => new Response("unavailable", { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    const client = new RelayClient("https://relay.test", "connector-token", "conn-1");
    await expect(client.processMessage(payload)).rejects.toThrow("HTTP 503");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
