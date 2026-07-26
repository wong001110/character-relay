import { describe, expect, it } from "vitest";

import { normalizeLanguage, translate } from "./i18n";

describe("multilingual interface", () => {
  it("keeps English as the default and rejects unknown stored values", () => {
    expect(normalizeLanguage(null)).toBe("en");
    expect(normalizeLanguage("fr")).toBe("en");
    expect(normalizeLanguage("zh-CN")).toBe("zh-CN");
  });

  it("translates static copy and interpolates values", () => {
    expect(translate("en", "room.testLanguage")).toBe("Test language");
    expect(translate("zh-CN", "room.testLanguage")).toBe("测试语言");
    expect(translate("zh-CN", "room.replies", { count: 3 })).toBe("3 条回答");
    expect(translate("en", "shelf.page", { page: 2, pages: 4 })).toBe("Page 2 of 4");
    expect(translate("zh-CN", "shelf.page", { page: 2, pages: 4 })).toBe("第 2 / 4 页");
  });

  it("keeps English and Chinese test controls distinct", () => {
    expect(translate("en", "room.testEnglish")).toContain("English");
    expect(translate("zh-CN", "room.testChinese")).toContain("简体中文");
  });

  it("includes typed Admin Runtime and Hybrid Judge copy", () => {
    expect(translate("en", "admin.heading")).toContain("shared evaluation agents");
    expect(translate("zh-CN", "admin.heading")).toContain("共用评估");
    expect(translate("en", "judge.hybrid")).toBe("Hybrid");
    expect(translate("zh-CN", "judge.review")).toBe("需要人工复核");
    expect(translate("en", "creator.saveChanges")).toBe("Save changes");
  });
});
