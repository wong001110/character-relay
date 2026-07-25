import { describe, expect, it } from "vitest";

import { formatReportContent, reportFilename } from "./report";

describe("report modal helpers", () => {
  it("pretty prints JSON reports", () => {
    expect(formatReportContent('{"score":81,"passed":false}', "json")).toBe(
      '{\n  "score": 81,\n  "passed": false\n}'
    );
  });

  it("leaves Lab Notes unchanged", () => {
    expect(formatReportContent("# Lab Note\n", "markdown")).toBe("# Lab Note\n");
  });

  it("uses stable export filenames", () => {
    expect(reportFilename("run-1", "markdown")).toBe("echo-masque-run-1.md");
    expect(reportFilename("run-1", "json")).toBe("echo-masque-run-1.json");
  });
});
