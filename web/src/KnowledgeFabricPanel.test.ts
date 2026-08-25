import { describe, expect, it } from "vitest";

import { scopeMatchesProfile } from "./KnowledgeFabricPanel";
import type { DiscordServerProfile } from "./deploymentApi";
import type { KnowledgeFabricScope } from "./knowledgeFabricApi";

const profile: DiscordServerProfile = {
  id: "profile-a",
  connection_id: "connection-a",
  name: "Server A",
  guild_id: "guild-a",
  guild_name: "Guild A",
  channel_scope_mode: "all_except",
  excluded_channel_ids: [],
  excluded_category_ids: [],
  thread_policy: "inherit_parent",
  created_at: "2026-08-26T00:00:00Z",
  updated_at: "2026-08-26T00:00:00Z"
};

const scope: KnowledgeFabricScope = {
  id: "scope-a",
  platform: "discord",
  connection_id: "connection-a",
  workspace_id: "guild-a",
  created_at: "2026-08-26T00:00:00Z",
  updated_at: "2026-08-26T00:00:00Z"
};

describe("Knowledge Fabric Server scope selection", () => {
  it("requires the exact Discord connection and guild tuple", () => {
    expect(scopeMatchesProfile(scope, profile)).toBe(true);
    expect(scopeMatchesProfile({ ...scope, platform: "telegram" }, profile)).toBe(false);
    expect(scopeMatchesProfile({ ...scope, connection_id: "connection-b" }, profile)).toBe(false);
    expect(scopeMatchesProfile({ ...scope, workspace_id: "guild-b" }, profile)).toBe(false);
  });
});
