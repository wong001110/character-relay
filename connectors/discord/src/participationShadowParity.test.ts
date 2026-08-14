import { describe, expect, it } from "vitest";

import { compareParticipationShadowPlan } from "./participationShadowParity.js";

const scores = [
  {
    deployment_id: "ann",
    deterministic_score: 4,
    semantic_points: 6,
    shadow_final_score: 10,
    shadow_selected: true
  }
];

describe("Participation shadow parity", () => {
  it("reports exact ordered parity", () => {
    const result = compareParticipationShadowPlan(
      [
        { deployment_id: "ann", turn_role: "primary", reason: "shadow" },
        { deployment_id: "ning", turn_role: "complement", reason: "shadow" }
      ],
      ["ann", "ning"],
      scores
    );

    expect(result.observed).toBe(true);
    expect(result.exactMatch).toBe(true);
    expect(result.setMatch).toBe(true);
    expect(result.missingFromShadow).toEqual([]);
    expect(result.extraInShadow).toEqual([]);
  });

  it("distinguishes ordering mismatch from set mismatch", () => {
    const reorder = compareParticipationShadowPlan(
      [
        { deployment_id: "ann", turn_role: "primary", reason: "shadow" },
        { deployment_id: "ning", turn_role: "complement", reason: "shadow" }
      ],
      ["ning", "ann"],
      scores
    );
    expect(reorder.exactMatch).toBe(false);
    expect(reorder.setMatch).toBe(true);

    const different = compareParticipationShadowPlan(
      [{ deployment_id: "ann", turn_role: "primary", reason: "shadow" }],
      ["ning"],
      scores
    );
    expect(different.exactMatch).toBe(false);
    expect(different.setMatch).toBe(false);
    expect(different.missingFromShadow).toEqual(["ning"]);
    expect(different.extraInShadow).toEqual(["ann"]);
  });

  it("treats an empty shadow plan as a real observed silent plan", () => {
    const result = compareParticipationShadowPlan([], [], []);
    expect(result.observed).toBe(true);
    expect(result.exactMatch).toBe(true);
    expect(result.setMatch).toBe(true);
  });

  it("does not claim parity when the resolver did not return shadow evidence", () => {
    const result = compareParticipationShadowPlan(undefined, ["ann"], undefined);
    expect(result.observed).toBe(false);
    expect(result.exactMatch).toBe(false);
    expect(result.setMatch).toBe(false);
  });
});
