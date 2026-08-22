import { ChannelType } from "discord.js";
import { describe, expect, it, vi } from "vitest";

import {
  collectDiscordServerCatalog,
  refreshCatalogThenDeployments,
  type DiscordCatalogGuild
} from "./serverCatalog.js";

function guild(
  id: string,
  options: {
    channels?: Map<string, object | null>;
    channelError?: Error;
    emojis?: Map<string, object>;
    emojiError?: Error;
    stickers?: Map<string, object>;
    stickerError?: Error;
  } = {}
): DiscordCatalogGuild {
  return {
    id,
    name: `Guild ${id}`,
    channels: {
      fetch: async () => {
        if (options.channelError) throw options.channelError;
        return options.channels ?? new Map();
      }
    },
    emojis: {
      fetch: async () => {
        if (options.emojiError) throw options.emojiError;
        return options.emojis ?? new Map();
      }
    },
    stickers: {
      fetch: async () => {
        if (options.stickerError) throw options.stickerError;
        return options.stickers ?? new Map();
      }
    }
  } as DiscordCatalogGuild;
}

function textChannel(id: string): object {
  return {
    id,
    name: id,
    parentId: null,
    type: ChannelType.GuildText,
    viewable: true
  };
}

describe("Discord server catalog collection", () => {
  it("keeps successful guild snapshots when one guild channel fetch fails", async () => {
    const secret = "private Discord message and token";
    const logs: Record<string, unknown>[] = [];
    const catalog = await collectDiscordServerCatalog(
      [
        guild("guild-a", { channels: new Map([["a-channel", textChannel("a-channel")]]) }),
        guild("guild-b", { channelError: new Error(secret) }),
        guild("guild-c", { channels: new Map([["c-channel", textChannel("c-channel")]]) })
      ],
      (_, details) => logs.push(details)
    );

    expect(catalog.visible_guild_ids).toEqual(["guild-a", "guild-b", "guild-c"]);
    expect(catalog.failed_guild_ids).toEqual(["guild-b"]);
    expect(catalog.servers.map((server) => server.guild_id)).toEqual(["guild-a", "guild-c"]);
    expect(JSON.stringify(logs)).not.toContain(secret);
  });

  it("omits only failed media inventories instead of sending an empty replacement", async () => {
    const catalog = await collectDiscordServerCatalog(
      [
        guild("guild-media", {
          channels: new Map([["media-channel", textChannel("media-channel")]]),
          emojiError: new Error("private emoji failure"),
          stickers: new Map([
            [
              "sticker-1",
              {
                id: "sticker-1",
                name: "Wave",
                description: null,
                tags: "hello,wave",
                format: 1,
                url: "https://cdn.example/sticker-1.png"
              }
            ]
          ])
        })
      ],
      () => undefined
    );

    expect(catalog.servers[0]).not.toHaveProperty("emojis");
    expect(catalog.servers[0]?.stickers).toEqual([
      expect.objectContaining({ sticker_id: "sticker-1" })
    ]);
  });

  it("continues deployment refresh when catalog delivery fails", async () => {
    const refreshDeployments = vi.fn(async () => undefined);
    const onCatalogError = vi.fn();

    await refreshCatalogThenDeployments(
      async () => {
        throw new Error("catalog endpoint unavailable");
      },
      refreshDeployments,
      onCatalogError
    );

    expect(onCatalogError).toHaveBeenCalledOnce();
    expect(refreshDeployments).toHaveBeenCalledOnce();
  });
});
