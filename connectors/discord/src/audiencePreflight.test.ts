import { describe, expect, it } from "vitest";

import {
  resolveExplicitAudiencePreflight,
  semanticScoringRequired
} from "./audiencePreflight.js";
import type { DiscordDeployment } from "./types.js";

function deployment(name: string): DiscordDeployment {
  return {
    deployment_id: `deployment-${name}`,
    connection_id: "connection-1",
    character_card_id: `character-${name}`,
    character_display_name: name,
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "general",
    thread_id: "",
    thread_name: "",
    category_id: "category-1",
    server_profile_id: "",
    channel_scope_mode: "exact",
    excluded_channel_ids: [],
    excluded_category_ids: [],
    participation_mode: "smart",
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: name,
    identity_avatar_url: "",
    address_aliases: [name],
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null,
    orchestration_mode: "off"
  };
}

describe("explicit audience preflight", () => {
  it("resolves a named Character before semantic scoring", () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    const result = resolveExplicitAudiencePreflight(
      [ann, ning],
      "Ann, what do you think?"
    );

    expect(result?.reason).toBe("selected_alias");
    expect(result?.deployments).toEqual([ann]);
    expect(result?.text).toBe("what do you think?");
    expect(semanticScoringRequired([ann, ning], result)).toBe(false);
  });

  it("resolves reply and group routes without invoking proactive participation", () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");

    const reply = resolveExplicitAudiencePreflight(
      [ann, ning],
      "Ning, this text must not override the reply route",
      ann.deployment_id
    );
    expect(reply?.reason).toBe("selected_reply");
    expect(reply?.deployments).toEqual([ann]);

    const group = resolveExplicitAudiencePreflight([ann, ning], "everyone, hello");
    expect(group?.reason).toBe("selected_all");
    expect(group?.deployments).toEqual([ann, ning]);
    expect(semanticScoringRequired([ann, ning], group)).toBe(false);
  });

  it("returns null for ordinary group chat so Smart Participation may continue", () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    const result = resolveExplicitAudiencePreflight(
      [ann, ning],
      "the weather changed again"
    );

    expect(result).toBeNull();
    expect(semanticScoringRequired([ann, ning], result)).toBe(true);
  });

  it("preserves original smart deployment objects after preflight cloning", () => {
    const ann = deployment("Ann");
    const result = resolveExplicitAudiencePreflight([ann], "Ann: hello");

    expect(result?.deployments[0]).toBe(ann);
    expect(result?.deployments[0]?.participation_mode).toBe("smart");
  });
});
