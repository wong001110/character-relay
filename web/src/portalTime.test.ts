import { describe, expect, it } from "vitest";

import { formatPortalClock, formatPortalTimestamp, parsePortalTimestamp } from "./portalTime";

describe("Portal Malaysia time", () => {
  it("treats timezone-less API timestamps as UTC before displaying MYT", () => {
    expect(parsePortalTimestamp("2026-08-09T04:57:20").toISOString()).toBe(
      "2026-08-09T04:57:20.000Z"
    );
    const display = formatPortalTimestamp("2026-08-09T04:57:20", true);
    // ICU versions may render Chinese noon as either 下午12:57 or 下午0:57.
    // Both represent the same 12:57 MYT instant; keep the test focused on conversion.
    expect(display).toMatch(/(?:12|0):57:20/u);
    expect(display).toContain("MYT");
  });

  it("preserves timestamps that already contain an explicit offset", () => {
    expect(parsePortalTimestamp("2026-08-09T12:57:20+08:00").toISOString()).toBe(
      "2026-08-09T04:57:20.000Z"
    );
  });

  it("formats Web Room clock labels in MYT regardless of browser timezone", () => {
    expect(formatPortalClock("2026-10-03T15:37:00Z")).toBe("23:37 MYT");
    expect(formatPortalClock("2026-10-03T23:37:00+08:00")).toBe("23:37 MYT");
  });
});
