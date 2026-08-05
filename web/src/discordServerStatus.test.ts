import { describe, expect, it } from "vitest";

import type {
  DiscordServerCatalog,
  DiscordServerProfile,
  PlatformConnection
} from "./deploymentApi";
import { buildDiscordServerStatuses } from "./discordServerStatus";

const NOW = Date.parse("2026-08-05T13:00:00Z");

function connection(
  status: PlatformConnection["status"],
  lastSeenAt = "2026-08-05T12:59:30Z"
): PlatformConnection {
  return {
    id: "connection-1",
    platform: "discord",
    display_name: "Character Relay Discord",
    connection_mode: "managed",
    external_account_id: "bot-1",
    status,
    metadata: {
      connector_display_name: "CharacterRelayBot#0001",
      replica_region: "asia-southeast1-eqsg3a",
      gateway_ready: true,
      state_synchronized: true,
      visible_server_count: 2
    },
    last_seen_at: lastSeenAt,
    created_at: "2026-08-05T12:00:00Z",
    updated_at: "2026-08-05T12:59:30Z"
  };
}

const profile: DiscordServerProfile = {
  id: "profile-1",
  connection_id: "connection-1",
  name: "Test server",
  guild_id: "guild-1",
  guild_name: "Guild One",
  channel_scope_mode: "all_except",
  excluded_channel_ids: [],
  excluded_category_ids: [],
  thread_policy: "inherit_parent",
  created_at: "2026-08-05T12:00:00Z",
  updated_at: "2026-08-05T12:00:00Z"
};

const catalog: DiscordServerCatalog = {
  connection_id: "connection-1",
  guild_id: "guild-1",
  guild_name: "Guild One",
  channels: [],
  synced_at: "2026-08-05T12:59:20Z"
};

describe("buildDiscordServerStatuses", () => {
  it("reports a fresh heartbeat and catalog as connected", () => {
    const [result] = buildDiscordServerStatuses(
      [profile],
      [connection("connected")],
      [catalog],
      NOW
    );
    expect(result?.state).toBe("connected");
    expect(result?.replicaRegion).toBe("asia-southeast1-eqsg3a");
  });

  it("reports a live connector that cannot see a configured server", () => {
    const [result] = buildDiscordServerStatuses(
      [profile],
      [connection("connected")],
      [],
      NOW
    );
    expect(result?.state).toBe("server_not_seen");
  });

  it("reports stale heartbeat data", () => {
    const [result] = buildDiscordServerStatuses(
      [profile],
      [connection("connected", "2026-08-05T12:50:00Z")],
      [catalog],
      NOW
    );
    expect(result?.state).toBe("stale");
  });

  it("preserves explicit connector error and offline states", () => {
    expect(
      buildDiscordServerStatuses([profile], [connection("error")], [catalog], NOW)[0]
        ?.state
    ).toBe("connector_error");
    expect(
      buildDiscordServerStatuses(
        [profile],
        [connection("disconnected")],
        [catalog],
        NOW
      )[0]?.state
    ).toBe("connector_offline");
  });
});
