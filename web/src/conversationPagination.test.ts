import { describe, expect, it } from "vitest";

import { pageCount, pageItems } from "./conversationPagination";

describe("conversation pagination", () => {
  it("keeps page bounds safe for populated and empty boards", () => {
    expect(pageCount(13, 12)).toBe(2);
    expect(pageCount(0, 12)).toBe(1);
    expect(pageItems([1, 2, 3, 4, 5], 2, 2)).toEqual([3, 4]);
    expect(pageItems([1, 2], 0, 2)).toEqual([1, 2]);
  });
});
