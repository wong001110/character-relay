import { describe, expect, it } from "vitest";

import { settingsRoute, settingsRouteForSearch } from "./portalRoutes";

describe("settings deep links", () => {
  it("links directly to the existing Knowledge Fabric administration surface", () => {
    expect(settingsRoute("administration", "knowledge")).toBe(
      "/settings?tab=administration&admin=knowledge"
    );
    expect(settingsRouteForSearch("?tab=administration&admin=knowledge")).toEqual({
      tab: "administration",
      administrationTab: "knowledge"
    });
  });

  it("falls back to safe settings tabs for unknown query values", () => {
    expect(settingsRouteForSearch("?tab=unknown&admin=unknown")).toEqual({
      tab: "account",
      administrationTab: "users"
    });
  });
});
