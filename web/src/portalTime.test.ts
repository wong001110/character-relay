import { describe, expect, it } from "vitest";

import { formatPortalTimestamp, parsePortalTimestamp } from "./portalTime";

describe("Portal Malaysia time", () => {
  it("treats timezone-less API timestamps as UTC before displaying MYT", () => {
    expect(parsePortalTimestamp("2026-08-09T04:57:20").toISOString()).toBe(
      "2026-08-09T04:57:20.000Z"
    );
    const display = formatPortalTimestamp("2026-08-09T04:57:20", true);
    expect(display).toContain("12:57:20");
    expect(display).toContain("MYT");
  });

  it("preserves timestamps that already contain an explicit offset", () => {
    expect(parsePortalTimestamp("2026-08-09T12:57:20+08:00").toISOString()).toBe(
      "2026-08-09T04:57:20.000Z"
    );
  });
});
