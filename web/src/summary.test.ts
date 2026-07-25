import { describe, expect, it } from "vitest";
import { integrityLabel } from "./summary";

describe("integrityLabel", () => {
  it("maps scores to observation language", () => {
    expect(integrityLabel(100)).toBe("Intact");
    expect(integrityLabel(72)).toBe("Strained");
    expect(integrityLabel(45)).toBe("Fractured");
    expect(integrityLabel(20)).toBe("Collapsed");
  });
});
