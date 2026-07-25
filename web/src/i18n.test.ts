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
  });

  it("keeps English and Chinese test controls distinct", () => {
    expect(translate("en", "room.testEnglish")).toContain("English");
    expect(translate("zh-CN", "room.testChinese")).toContain("简体中文");
  });
});
