import { describe, expect, it } from "vitest";

import { getProviderPreset } from "./providerPresets";

describe("provider presets", () => {
  it("uses the current DeepSeek OpenAI-compatible defaults", () => {
    expect(getProviderPreset("deepseek")).toMatchObject({
      baseUrl: "https://api.deepseek.com",
      defaultModel: "deepseek-v4-flash"
    });
  });

  it("keeps custom endpoints empty for explicit user configuration", () => {
    expect(getProviderPreset("custom")).toMatchObject({
      baseUrl: "",
      defaultModel: ""
    });
  });
});
