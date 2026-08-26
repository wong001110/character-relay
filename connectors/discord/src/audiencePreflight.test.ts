import { afterEach, describe, expect, it, vi } from "vitest";

import {
  resolveExplicitAudiencePreflight,
  semanticScoringRequired
} from "./audiencePreflight.js";
import type { AudienceResolution } from "./routing.js";
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
  afterEach(() => {
    vi.doUnmock("./routing.js");
    vi.resetModules();
  });

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

  it("passes smart candidates to routing as mention-only without changing other candidates", async () => {
    const smart = deployment("Ann");
    const mentionOnly = { ...deployment("Ning"), participation_mode: "mention_only" as const };
    const resolveAudience = vi.fn<
      (
        candidates: DiscordDeployment[],
        text: string,
        replyDeploymentId: string | null,
        groupAliases: string[]
      ) => AudienceResolution
    >(() => ({ deployments: [smart], reason: "selected_alias", text: "hello", options: [] }));
    vi.doMock("./routing.js", async () => {
      const actual = await vi.importActual<typeof import("./routing.js")>("./routing.js");
      return { ...actual, resolveAudience };
    });
    const { resolveExplicitAudiencePreflight: resolveWithSpy } = await import("./audiencePreflight.js");

    const result = resolveWithSpy([smart, mentionOnly], "Ann, hello");

    expect(result?.deployments).toEqual([smart]);
    const routedCandidates = resolveAudience.mock.calls[0]?.[0];
    expect(routedCandidates).toHaveLength(2);
    expect(routedCandidates?.[0]).toMatchObject({
      deployment_id: smart.deployment_id,
      participation_mode: "mention_only"
    });
    expect(routedCandidates?.[0]).not.toBe(smart);
    expect(routedCandidates?.[1]).toBe(mentionOnly);
  });

  it("does not invent a group alias when callers use the default aliases", () => {
    const result = resolveExplicitAudiencePreflight(
      [deployment("Ann")],
      "Stryker was here, hello"
    );

    expect(result).toBeNull();
  });

  it("short-circuits an empty candidate list before routing", async () => {
    const resolveAudience = vi.fn<
      (
        candidates: DiscordDeployment[],
        text: string,
        replyDeploymentId: string | null,
        groupAliases: string[]
      ) => AudienceResolution
    >();
    vi.doMock("./routing.js", async () => {
      const actual = await vi.importActual<typeof import("./routing.js")>("./routing.js");
      return { ...actual, resolveAudience };
    });
    const { resolveExplicitAudiencePreflight: resolveWithSpy } = await import("./audiencePreflight.js");

    expect(resolveWithSpy([], "Ann, hello")).toBeNull();
    expect(resolveAudience).not.toHaveBeenCalled();
  });

  it("requires semantic scoring only when no explicit route leaves a smart candidate", () => {
    const smart = deployment("Ann");
    const mentionOnly = { ...deployment("Ning"), participation_mode: "mention_only" as const };

    expect(semanticScoringRequired([smart, mentionOnly], null)).toBe(true);
    expect(semanticScoringRequired([mentionOnly], null)).toBe(false);
  });
});
