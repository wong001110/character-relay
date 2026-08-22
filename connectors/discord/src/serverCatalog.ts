import { ChannelType } from "discord.js";

import { safeDiagnosticError } from "./safeDiagnosticError.js";
import type {
  DiscordCatalogEmoji,
  DiscordCatalogServer,
  DiscordCatalogSticker,
  DiscordServerCatalogSync
} from "./types.js";

type CatalogChannel = Readonly<{
  id: string;
  name: string;
  parentId: string | null;
  type: ChannelType;
  viewable: boolean;
}>;

type CatalogEmoji = Readonly<{
  id: string;
  name: string | null;
  animated: boolean | null;
  available: boolean | null;
  imageURL: (options: { extension: "gif" | "png"; size: number }) => string;
}>;

type CatalogSticker = Readonly<{
  id: string;
  name: string;
  description: string | null;
  tags: string | null;
  format: unknown;
  url: string;
}>;

type FetchableCollection<T> = Readonly<{ values: () => IterableIterator<T> }>;

export type DiscordCatalogGuild = Readonly<{
  id: string;
  name: string;
  channels: Readonly<{ fetch: () => Promise<FetchableCollection<CatalogChannel | null>> }>;
  emojis: Readonly<{ fetch: () => Promise<FetchableCollection<CatalogEmoji>> }>;
  stickers: Readonly<{ fetch: () => Promise<FetchableCollection<CatalogSticker>> }>;
}>;

export type CatalogLog = (message: string, details: Record<string, unknown>) => void;

const catalogChannelTypes = new Set([
  ChannelType.GuildText,
  ChannelType.GuildAnnouncement,
  ChannelType.GuildForum,
  ChannelType.GuildMedia
]);

export async function collectDiscordServerCatalog(
  guilds: Iterable<DiscordCatalogGuild>,
  log: CatalogLog
): Promise<Omit<DiscordServerCatalogSync, "connection_id">> {
  const visible_guild_ids: string[] = [];
  const failed_guild_ids: string[] = [];
  const servers: DiscordCatalogServer[] = [];

  for (const guild of guilds) {
    visible_guild_ids.push(guild.id);
    let fetchedChannels: FetchableCollection<CatalogChannel | null>;
    try {
      fetchedChannels = await guild.channels.fetch();
    } catch (error) {
      failed_guild_ids.push(guild.id);
      log("Unable to synchronize Discord Guild Channels.", {
        guildId: guild.id,
        ...safeDiagnosticError(error)
      });
      continue;
    }

    const categories = new Map(
      [...fetchedChannels.values()]
        .filter(
          (channel): channel is CatalogChannel =>
            channel !== null && channel.type === ChannelType.GuildCategory
        )
        .map((channel) => [channel.id, channel.name])
    );
    const channels = [...fetchedChannels.values()]
      .filter(
        (channel): channel is CatalogChannel =>
          channel !== null && catalogChannelTypes.has(channel.type) && channel.viewable
      )
      .map((channel) => ({
        id: channel.id,
        name: channel.name,
        category_id: channel.parentId ?? "",
        category_name: channel.parentId ? (categories.get(channel.parentId) ?? "") : "",
        type:
          channel.type === ChannelType.GuildForum
            ? "forum"
            : channel.type === ChannelType.GuildMedia
              ? "media"
              : channel.type === ChannelType.GuildAnnouncement
                ? "announcement"
                : "text"
      }))
      .sort((left, right) =>
        `${left.category_name}/${left.name}`.localeCompare(
          `${right.category_name}/${right.name}`
        )
      );
    const server: DiscordCatalogServer = {
      guild_id: guild.id,
      guild_name: guild.name,
      channels
    };

    try {
      const fetchedEmojis = await guild.emojis.fetch();
      server.emojis = [...fetchedEmojis.values()]
        .map(
          (emoji): DiscordCatalogEmoji => ({
            emoji_id: emoji.id,
            name: emoji.name || "emoji",
            animated: Boolean(emoji.animated),
            available: emoji.available !== false,
            asset_url: emoji.imageURL({ extension: emoji.animated ? "gif" : "png", size: 128 })
          })
        )
        .sort((left, right) => left.name.localeCompare(right.name));
    } catch (error) {
      log("Unable to synchronize Discord Guild Emojis.", {
        guildId: guild.id,
        ...safeDiagnosticError(error)
      });
    }

    try {
      const fetchedStickers = await guild.stickers.fetch();
      server.stickers = [...fetchedStickers.values()]
        .map(
          (sticker): DiscordCatalogSticker => ({
            sticker_id: sticker.id,
            name: sticker.name || "Sticker",
            description: sticker.description ?? "",
            tags: (sticker.tags ?? "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            format_type: String(sticker.format),
            asset_url: sticker.url
          })
        )
        .sort((left, right) => left.name.localeCompare(right.name));
    } catch (error) {
      log("Unable to synchronize Discord Guild Stickers.", {
        guildId: guild.id,
        ...safeDiagnosticError(error)
      });
    }
    servers.push(server);
  }

  return { visible_guild_ids, failed_guild_ids, servers };
}

export async function refreshCatalogThenDeployments(
  syncCatalog: () => Promise<void>,
  refreshDeployments: () => Promise<void>,
  onCatalogError: (error: unknown) => void
): Promise<void> {
  try {
    await syncCatalog();
  } catch (error) {
    onCatalogError(error);
  }
  await refreshDeployments();
}
