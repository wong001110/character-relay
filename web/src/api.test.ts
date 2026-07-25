import { describe, expect, it } from "vitest";

import { pollIntervalForMode } from "./api";

describe("live polling cadence", () => {
  it("uses a low-frequency Watch cadence", () => {
    expect(pollIntervalForMode("watch")).toBe(1200);
  });

  it("keeps Fast responsive without 180ms request spam", () => {
    expect(pollIntervalForMode("fast")).toBe(450);
  });
});
