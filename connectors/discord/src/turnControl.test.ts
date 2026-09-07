import { describe, expect, it } from "vitest";

import { parseTurnControl } from "./turnControl.js";

describe("parseTurnControl", () => {
  it("requires an anchored audience and control command", () => {
    expect(parseTurnControl("Ann cancel")).toEqual({ kind: "cancel", audienceText: "Ann" });
    expect(parseTurnControl("Ann replace: draw a cat instead")).toEqual({
      kind: "replace",
      audienceText: "Ann",
      replacementText: "draw a cat instead"
    });
  });

  it("does not turn ordinary wording or a bare keyword into cancellation", () => {
    expect(parseTurnControl("can you cancel that?")).toBeNull();
    expect(parseTurnControl("cancel")).toBeNull();
    expect(parseTurnControl("Ann please cancel this")).toBeNull();
  });
});
