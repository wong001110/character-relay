import type {
  DiscordServerCatalog,
  DiscordServerProfile,
  PlatformConnection
} from "./deploymentApi";

export type DiscordServerLinkState =
  | "connected"
  | "stale"
  | "connector_error"
  | "connector_offline"
  | "server_not_seen";

export interface DiscordServerLinkStatus {
  profile: DiscordServerProfile;
  connection: PlatformConnection | null;
  catalog: DiscordServerCatalog | null;
  state: DiscordServerLinkState;
  heartbeatFresh: boolean;
  catalogFresh: boolean;
  replicaRegion: string;
  connectorDisplayName: string;
  lastError: string;
  gatewayReady: boolean | null;
  stateSynchronized: boolean | null;
  visibleServerCount: number | null;
}

export const SERVER_LINK_FRESHNESS_MS = 120_000;

function timestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fresh(value: string | null | undefined, now: number): boolean {
  const parsed = timestamp(value);
  return parsed !== null && now - parsed <= SERVER_LINK_FRESHNESS_MS;
}

function metadataString(
  connection: PlatformConnection | null,
  key: string
): string {
  const value = connection?.metadata[key];
  return typeof value === "string" ? value : "";
}

function metadataBoolean(
  connection: PlatformConnection | null,
  key: string
): boolean | null {
  const value = connection?.metadata[key];
  return typeof value === "boolean" ? value : null;
}

function metadataNumber(
  connection: PlatformConnection | null,
  key: string
): number | null {
  const value = connection?.metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function buildDiscordServerStatuses(
  profiles: DiscordServerProfile[],
  connections: PlatformConnection[],
  catalogs: DiscordServerCatalog[],
  now = Date.now()
): DiscordServerLinkStatus[] {
  const connectionMap = new Map(connections.map((item) => [item.id, item]));
  const catalogMap = new Map(
    catalogs.map((item) => [`${item.connection_id}:${item.guild_id}`, item])
  );

  return profiles.map((profile) => {
    const connection = connectionMap.get(profile.connection_id) ?? null;
    const catalog =
      catalogMap.get(`${profile.connection_id}:${profile.guild_id}`) ?? null;
    const heartbeatFresh = fresh(connection?.last_seen_at, now);
    const catalogFresh = fresh(catalog?.synced_at, now);

    let state: DiscordServerLinkState;
    if (!connection || connection.status === "offline" || connection.status === "disconnected") {
      state = "connector_offline";
    } else if (connection.status === "error") {
      state = "connector_error";
    } else if (!heartbeatFresh) {
      state = "stale";
    } else if (!catalog) {
      state = "server_not_seen";
    } else if (!catalogFresh) {
      state = "stale";
    } else {
      state = "connected";
    }

    return {
      profile,
      connection,
      catalog,
      state,
      heartbeatFresh,
      catalogFresh,
      replicaRegion: metadataString(connection, "replica_region"),
      connectorDisplayName: metadataString(connection, "connector_display_name"),
      lastError: metadataString(connection, "last_error"),
      gatewayReady: metadataBoolean(connection, "gateway_ready"),
      stateSynchronized: metadataBoolean(connection, "state_synchronized"),
      visibleServerCount: metadataNumber(connection, "visible_server_count")
    };
  });
}
