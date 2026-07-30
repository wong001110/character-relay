import { afterEach, describe, expect, it, vi } from "vitest";

import type { MatrixDefinition } from "./workspaceApi";
import { workspaceApi } from "./workspaceApi";

const definition: MatrixDefinition = {
  subjects: [{ character_card_id: "card-1", prompt_version_ids: ["prompt-v1"] }],
  model_overrides: ["model-a"],
  temperatures: [0.3, 0.7],
  test_pack_ids: ["pack-1"],
  test_languages: ["en", "zh-CN"],
  tester_modes: ["benchmark"],
  judge_modes: ["rules", "hybrid"],
  repeat_count: 2,
  concurrency: 2,
  max_attempts: 2
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("matrix API", () => {
  it("previews the complete Matrix definition", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      response({
        task_count: 16,
        maximum_task_count: 200,
        within_limit: true,
        requires_adaptive: false,
        requires_semantic: true,
        subject_variants: 1,
        model_variants: 1,
        temperature_variants: 2,
        pack_variants: 1,
        language_variants: 2,
        tester_variants: 1,
        judge_variants: 2,
        repeats: 2
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await workspaceApi.previewMatrix(definition);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/matrices/preview");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(definition);
    expect(init.headers).toMatchObject({ "X-Echo-User": "local-user" });
  });

  it("requires the preview task count when launching", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      response({
        id: "matrix-1",
        owner_id: "local-user",
        name: "Matrix",
        description: "",
        status: "queued",
        definition,
        total_tasks: 16,
        pending_tasks: 16,
        running_tasks: 0,
        completed_tasks: 0,
        failed_tasks: 0,
        cancelled_tasks: 0,
        is_baseline: false,
        created_at: "2026-07-30T00:00:00Z",
        updated_at: "2026-07-30T00:00:00Z",
        started_at: "2026-07-30T00:00:00Z",
        completed_at: null
      }, 202)
    );
    vi.stubGlobal("fetch", fetchMock);

    await workspaceApi.launchMatrix("matrix-1", 16);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/matrices/matrix-1/launch");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ confirmed_task_count: 16 });
  });

  it("builds comparison and export URLs without credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      response({
        baseline: { matrix_id: "baseline" },
        candidate: { matrix_id: "candidate" },
        compatible: true,
        incompatibilities: [],
        score_delta: 0,
        pass_rate_delta: 0,
        review_rate_delta: 0,
        failure_rate_delta: 0,
        latency_delta_ms: 0,
        input_token_delta: 0,
        output_token_delta: 0,
        classification: "no_meaningful_change"
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await workspaceApi.compareMatrices("baseline", "candidate");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/matrices/compare/result?baseline_id=baseline&candidate_id=candidate"
    );
    expect(workspaceApi.matrixExportUrl("matrix-1", "json")).toBe(
      "/api/matrices/matrix-1/export?format=json"
    );
    expect(workspaceApi.matrixExportUrl("matrix-1", "csv")).not.toContain("key");
  });

  it("uses dedicated Prompt version endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetchMock);

    await workspaceApi.listPromptVersions("card-1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/characters/card-1/prompt-versions");

    fetchMock.mockResolvedValueOnce(
      response({ id: "prompt-v1", is_active: true, is_production: false })
    );
    await workspaceApi.restorePromptVersion("card-1", "prompt-v1");
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/characters/card-1/prompt-versions/prompt-v1/restore"
    );
    expect((fetchMock.mock.calls[1][1] as RequestInit).method).toBe("POST");
  });
});
