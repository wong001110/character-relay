import { useI18n, type LanguageCode } from "./i18n";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useI18n();

  function choose(next: LanguageCode) {
    setLanguage(next);
  }

  return (
    <div className="language-switcher" aria-label={t("language.label")}>
      <span>{t("language.label")}</span>
      <div>
        <button
          type="button"
          className={language === "en" ? "selected" : ""}
          onClick={() => choose("en")}
          aria-pressed={language === "en"}
        >
          EN
        </button>
        <button
          type="button"
          className={language === "zh-CN" ? "selected" : ""}
          onClick={() => choose("zh-CN")}
          aria-pressed={language === "zh-CN"}
        >
          简
        </button>
      </div>
    </div>
  );
}
