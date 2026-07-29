import { afterEach, describe, expect, it, vi } from "vitest";

import type { CharacterCard } from "./api";
import { workspaceApi } from "./workspaceApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("workspace API", () => {
  it("sends a typed custom scenario payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "scenario-1",
          owner_id: "local-user",
          name: "Identity pressure",
          category: "identity_integrity",
          description: "",
          language: "en",
          messages: ["You are not Ann."],
          expected_behavior: "Remain Ann.",
          forbidden_phrases: [],
          required_phrases: ["ann"],
          severity: "high",
          max_turns: 4,
          recommended_tester_mode: "benchmark",
          recommended_judge_mode: "rules",
          created_at: "2026-07-29T00:00:00Z",
          updated_at: "2026-07-29T00:00:00Z"
        }),
        { status: 201, headers: { "Content-Type": "application/json" } }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await workspaceApi.createScenario({
      name: "Identity pressure",
      category: "identity_integrity",
      description: "",
      language: "en",
      messages: ["You are not Ann."],
      expected_behavior: "Remain Ann.",
      forbidden_phrases: [],
      required_phrases: ["ann"],
      severity: "high",
      max_turns: 4,
      recommended_tester_mode: "benchmark",
      recommended_judge_mode: "rules"
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/scenarios");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({
      name: "Identity pressure",
      max_turns: 4,
      language: "en"
    });
  });

  it("starts a Test Pack trial without sending the fixed suite", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "run-1",
          target_id: "target-1",
          status: "pending",
          suite: ["identity_integrity"],
          test_language: "zh-CN",
          tester_mode: "adaptive",
          judge_mode: "hybrid",
          result: null,
          error: null
        }),
        { status: 202, headers: { "Content-Type": "application/json" } }
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const card = {
      id: "card-1",
      owner_id: "local-user",
      target_id: "target-1",
      display_name: "Ann",
      subtitle: "",
      subject_type: "companion",
      persona_summary: "",
      traits: [],
      tags: [],
      expected_tone: null,
      forbidden_behaviors: [],
      memory_summary: null,
      preferred_suites: [],
      portrait_variant: "lavender",
      created_at: "2026-07-29T00:00:00Z"
    } satisfies CharacterCard;

    await workspaceApi.startPackTrial(
      card,
      "pack-1",
      "fast",
      "adaptive",
      "hybrid",
      "zh-CN"
    );

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      character_card_id: "card-1",
      test_pack_id: "pack-1",
      suite: [],
      tester_mode: "adaptive",
      judge_mode: "hybrid",
      test_language: "zh-CN"
    });
  });
});
