import { describe, expect, it } from "vitest";

import { nextGlobalCorpusGrantEnabled } from "./knowledgeFabricPanelPolicy";

describe("global Corpus grant transition", () => {
  it("enables an unavailable global Corpus and revokes an enabled one", () => {
    expect(nextGlobalCorpusGrantEnabled(false)).toBe(true);
    expect(nextGlobalCorpusGrantEnabled(true)).toBe(false);
  });
});
