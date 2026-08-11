import type { ReactNode } from "react";

import type { AuthUser } from "./api";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

export type PortalSection =
  | "dashboard"
  | "characters"
  | "deployments"
  | "toolbox"
  | "settings";

interface Props {
  active: PortalSection;
  user: AuthUser;
  publicDemo: boolean;
  onNavigate: (section: PortalSection) => void;
  children: ReactNode;
}

const navItems: Array<{
  id: PortalSection;
  icon: string;
  en: string;
  zh: string;
}> = [
  { id: "dashboard", icon: "⌂", en: "Dashboard", zh: "首页" },
  { id: "characters", icon: "▣", en: "Characters", zh: "角色" },
  { id: "deployments", icon: "◇", en: "Deployments", zh: "部署" },
  { id: "toolbox", icon: "⚒", en: "Toolbox", zh: "工具箱" },
  { id: "settings", icon: "⚙", en: "Settings", zh: "设置" }
];

export function PortalShell({
  active,
  user,
  publicDemo,
  onNavigate,
  children
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const initials = user.display_name.trim().slice(0, 1).toUpperCase() || "C";

  return (
    <div className="portal-v2-shell">
      <header className="portal-v2-topbar">
        <button
          type="button"
          className="portal-v2-brand"
          onClick={() => onNavigate("dashboard")}
          aria-label="Character Relay"
        >
          <img src="/assets/brand/character-relay-wordmark.png" alt="Character Relay" />
        </button>

        <nav className="portal-v2-main-nav" aria-label={zh ? "主要导航" : "Primary navigation"}>
          {navItems.map((item) => (
            <button
              type="button"
              key={item.id}
              className={active === item.id ? "is-active" : ""}
              onClick={() => onNavigate(item.id)}
            >
              <span aria-hidden="true">{item.icon}</span>
              {zh ? item.zh : item.en}
            </button>
          ))}
        </nav>

        <div className="portal-v2-account">
          <LanguageSwitcher />
          {publicDemo && <span className="portal-v2-demo-stamp">DEMO</span>}
          <button
            type="button"
            className="portal-v2-user-chip"
            onClick={() => onNavigate("settings")}
          >
            <span className="portal-v2-user-avatar" aria-hidden="true">{initials}</span>
            <span>
              <strong>{user.display_name}</strong>
              <small>{user.role === "admin" ? "Super Admin ✦" : "Creator"}</small>
            </span>
            <span aria-hidden="true">⌄</span>
          </button>
        </div>
      </header>

      <div className="portal-v2-page-frame">
        <div className="portal-v2-corner-tape portal-v2-corner-tape-left" aria-hidden="true" />
        <div className="portal-v2-corner-tape portal-v2-corner-tape-right" aria-hidden="true" />
        {children}
      </div>
    </div>
  );
}
