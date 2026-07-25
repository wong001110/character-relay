import { describe, expect, it } from "vitest";

import { adaptiveTesterReady, defaultAdaptiveTesterConfig } from "./adaptiveTester";

describe("Adaptive Tester configuration", () => {
  it("requires a one-run API key", () => {
    const config = defaultAdaptiveTesterConfig();
    expect(adaptiveTesterReady(config)).toBe(false);
    expect(adaptiveTesterReady({ ...config, api_key: "secret" })).toBe(true);
  });

  it("uses bounded turns", () => {
    const config = defaultAdaptiveTesterConfig();
    expect(config.max_turns).toBeGreaterThanOrEqual(2);
    expect(config.max_turns).toBeLessThanOrEqual(8);
  });
});
