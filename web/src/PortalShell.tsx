import type { ReactNode } from "react";

import type { AuthUser } from "./api";
import { FunctionalIcon, StickyLabel, type FunctionalIconName } from "./components/ui";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import "./scrapbook-page-phase1.css";

export type PortalSection =
  | "dashboard"
  | "characters"
  | "deployments"
  | "toolbox"
  | "settings";

interface Props {
  active: PortalSection;
  theme: "light" | "dark";
  user: AuthUser;
  publicDemo: boolean;
  onNavigate: (section: PortalSection) => void;
  onThemeToggle: () => void;
  children: ReactNode;
}

const navItems: Array<{
  id: PortalSection;
  icon: FunctionalIconName;
  en: string;
  zh: string;
}> = [
  { id: "dashboard", icon: "home", en: "Dashboard", zh: "首页" },
  { id: "characters", icon: "characters", en: "Characters", zh: "角色" },
  { id: "deployments", icon: "deployment", en: "Deployments", zh: "部署" },
  { id: "toolbox", icon: "toolbox", en: "Toolbox", zh: "工具箱" },
  { id: "settings", icon: "settings", en: "Settings", zh: "设置" }
];

export function PortalShell({
  active,
  theme,
  user,
  publicDemo,
  onNavigate,
  onThemeToggle,
  children
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const initials = user.display_name.trim().slice(0, 1).toUpperCase() || "C";
  const activeItem = navItems.find((item) => item.id === active) ?? navItems[0];

  return (
    <div
      className={`portal-v2-shell portal-v3-shell portal-theme-${theme}`}
      data-theme={theme}
      data-section={active}
    >
      <header className="portal-v2-topbar">
        <button type="button" className="portal-v2-brand" onClick={() => onNavigate("dashboard")} aria-label="Character Relay">
          <img src="/assets/brand/character-relay-mark.png" alt="" aria-hidden="true" />
          <span className="portal-v2-brand-copy">
            <strong>Character Relay</strong>
            <small>{zh ? "角色研究工作室" : "AI Characters in the Real World"}</small>
          </span>
        </button>

        <nav className="portal-v2-main-nav" aria-label={zh ? "主要导航" : "Primary navigation"}>
          {navItems.map((item) => (
            <button type="button" key={item.id} className={active === item.id ? "is-active" : ""} onClick={() => onNavigate(item.id)} aria-current={active === item.id ? "page" : undefined}>
              <FunctionalIcon name={item.icon} size={17} />
              {zh ? item.zh : item.en}
            </button>
          ))}
        </nav>

        <div className="portal-v2-account">
          <span className="portal-v2-language-control"><LanguageSwitcher /></span>
          {publicDemo && <span className="portal-v2-demo-stamp">DEMO</span>}
          <button
            type="button"
            className="portal-v2-theme-toggle"
            onClick={onThemeToggle}
            aria-pressed={theme === "dark"}
            aria-label={theme === "dark" ? (zh ? "切换到浅色主题" : "Switch to light theme") : (zh ? "切换到深色主题" : "Switch to dark theme")}
            title={theme === "dark" ? (zh ? "切换到浅色主题" : "Switch to light theme") : (zh ? "切换到深色主题" : "Switch to dark theme")}
          >
            <FunctionalIcon name={theme === "dark" ? "sun" : "moon"} size={16} />
            <span>{theme === "dark" ? (zh ? "深色" : "Dark") : (zh ? "浅色" : "Light")}</span>
          </button>
          <button
            type="button"
            className="portal-v2-user-chip"
            onClick={() => onNavigate("settings")}
            aria-label={zh ? `打开 ${user.display_name} 的账户设置` : `Open account settings for ${user.display_name}`}
            title={user.display_name}
          >
            <span className="portal-v2-user-avatar" aria-hidden="true">{initials}</span>
            <span><strong>{user.display_name}</strong><small>{user.role === "admin" ? "Super Admin ✦" : "Creator"}</small></span>
            <FunctionalIcon name="chevron" size={15} />
          </button>
        </div>
      </header>

      <div className="portal-v2-page-frame" data-section={active}>
        <StickyLabel className="portal-v2-section-marker">
          {active === "dashboard"
            ? zh ? "创作研究桌" : "CREATOR DESK"
            : `NOTEBOOK / ${zh ? activeItem.zh : activeItem.en}`}
        </StickyLabel>
        <div className="portal-v2-corner-tape portal-v2-corner-tape-left" aria-hidden="true" />
        <div className="portal-v2-corner-tape portal-v2-corner-tape-right" aria-hidden="true" />
        {children}
      </div>
    </div>
  );
}
