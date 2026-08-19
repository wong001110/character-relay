import { useEffect, useState } from "react";

import type { AuthUser } from "./api";
import { AccountSettingsPanel } from "./AccountSettingsPanel";
import { AdministrationSettingsPanel } from "./AdministrationSettingsPanel";
import { Button, FunctionalIcon, StickyLabel, StickyNote } from "./components/ui";
import { useI18n } from "./i18n";
import { serverAccessApi, type ServerAccessOverview } from "./serverAccessApi";
import { ServerAccessSettingsPanel } from "./ServerAccessSettingsPanel";
import "./settings-access.css";

interface Props {
  user: AuthUser;
  publicDemo: boolean;
  onAdmin: () => void;
  onLogout: () => Promise<void>;
  onAccountDeleted: () => void;
}

type SettingsTab = "account" | "server-access" | "administration";

export function SettingsWorkspace({
  user,
  publicDemo,
  onAdmin,
  onLogout,
  onAccountDeleted
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [tab, setTab] = useState<SettingsTab>("account");
  const [accessOverview, setAccessOverview] = useState<ServerAccessOverview | null>(null);

  useEffect(() => {
    let active = true;
    void serverAccessApi.overview()
      .then((overview) => {
        if (active) setAccessOverview(overview);
      })
      .catch(() => {
        if (active) setAccessOverview(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const superAdmin = accessOverview?.is_super_admin === true;

  return (
    <main className="settings-v2-page settings-v3-page settings-access-page">
      <aside className="settings-v2-note settings-v3-note settings-access-intro">
        <StickyLabel variant="neutral">SETTINGS / NOTEBOOK INDEX</StickyLabel>
        <h1>{zh ? "账户与 Server 权限" : "Account & server access"}</h1>
        <p>
          {zh
            ? "Account 只处理你自己；Server Access 决定账号能进入哪些 Discord Server；系统级 Users、Servers 与 Connector 只留给 Super Admin。"
            : "Account is only about you. Server Access controls which Discord servers an account can enter, while global Users, Servers, and Connector controls stay with the Super Admin."}
        </p>
        <StickyNote variant="temporary" size="sm">
          <strong>{zh ? "一个 Connector，全局共用" : "One connector, shared globally"}</strong>
          <p>
            {zh
              ? "普通账号不需要配置 Discord Bot；加入 Server 后直接使用现有 Character Relay 工作区。"
              : "Regular accounts never configure the Discord bot. Join a server, then use the existing Character Relay workspace."}
          </p>
        </StickyNote>
        {publicDemo && (
          <StickyNote variant="reference" size="sm">
            <strong>{zh ? "Demo 为只读" : "Demo is read-only"}</strong>
            <p>
              {zh
                ? "加入、删除与管理员操作会被阻止。"
                : "Join, delete, and administration mutations are blocked."}
            </p>
          </StickyNote>
        )}
      </aside>

      <section className="settings-v2-content settings-v3-content settings-access-content">
        <header className="settings-access-header">
          <div>
            <span className="settings-access-eyebrow">
              <FunctionalIcon name="settings" size={14} /> Character Relay Settings
            </span>
            <h2>
              {tab === "account" && (zh ? "我的 Account" : "My account")}
              {tab === "server-access" && (zh ? "我的 Server Access" : "My server access")}
              {tab === "administration" && (zh ? "系统管理" : "Administration")}
            </h2>
          </div>
          <span className="settings-account-tag">{user.email}</span>
        </header>

        <nav className="settings-index-tabs" aria-label="Settings sections">
          <button
            type="button"
            className={tab === "account" ? "is-active" : ""}
            onClick={() => setTab("account")}
          >
            <FunctionalIcon name="identity" size={16} /> Account
          </button>
          <button
            type="button"
            className={tab === "server-access" ? "is-active" : ""}
            onClick={() => setTab("server-access")}
          >
            <FunctionalIcon name="deployment" size={16} /> Server Access
          </button>
          {superAdmin && !publicDemo && (
            <button
              type="button"
              className={tab === "administration" ? "is-active" : ""}
              onClick={() => setTab("administration")}
            >
              <FunctionalIcon name="boundaries" size={16} /> Administration
            </button>
          )}
        </nav>

        <div className="settings-access-panel" role="region" aria-live="polite">
          {tab === "account" && (
            <AccountSettingsPanel
              user={user}
              onLogout={onLogout}
              onDeleted={onAccountDeleted}
            />
          )}

          {tab === "server-access" && (
            <ServerAccessSettingsPanel onOverviewChange={setAccessOverview} />
          )}

          {tab === "administration" && superAdmin && !publicDemo && (
            <>
              <div className="settings-runtime-strip">
                <div>
                  <strong>
                    {zh ? "Runtime 配置仍保持独立" : "Runtime configuration stays separate"}
                  </strong>
                  <span>
                    {zh
                      ? "这里管理人和 Server；模型、Judge 与 Runtime 继续使用原本的 Admin Runtime 面板。"
                      : "This page manages people and servers; model, Judge, and Runtime controls remain in the existing Admin Runtime panel."}
                  </span>
                </div>
                <Button variant="primary" type="button" onClick={onAdmin}>
                  {zh ? "打开 Runtime 设置" : "Open Runtime Settings"}
                </Button>
              </div>
              <AdministrationSettingsPanel user={user} />
            </>
          )}
        </div>
      </section>
    </main>
  );
}
