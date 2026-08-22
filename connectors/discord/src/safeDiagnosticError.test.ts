import { describe, expect, it } from "vitest";

import {
  formatSafeDiagnosticError,
  safeDiagnosticError
} from "./safeDiagnosticError.js";

describe("safeDiagnosticError", () => {
  it("keeps only a structured kind, code, and HTTP status", () => {
    const rawSecret = "Bot token and private Discord message";
    const error = Object.assign(new Error(rawSecret), {
      code: "ECONNRESET",
      status: 503,
      response: { body: rawSecret },
      cause: new Error(rawSecret)
    });

    expect(safeDiagnosticError(error)).toEqual({
      error_kind: "Error",
      error_code: "ECONNRESET",
      http_status: 503
    });
    expect(formatSafeDiagnosticError(error)).toBe(
      "kind=Error code=ECONNRESET status=503"
    );
    expect(JSON.stringify(safeDiagnosticError(error))).not.toContain(rawSecret);
    expect(formatSafeDiagnosticError(error)).not.toContain(rawSecret);
  });

  it("rejects arbitrary string fields and unsafe error names", () => {
    const rawSecret = "PRIVATE_MESSAGE_BODY";
    const error = Object.assign(new Error(rawSecret), {
      name: "SecretToken123",
      code: rawSecret,
      status: 700
    });

    expect(safeDiagnosticError(error)).toEqual({ error_kind: "Error" });
    expect(formatSafeDiagnosticError(error)).toBe("kind=Error");
  });
});
