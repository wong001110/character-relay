import type { AuthUser } from "./api";
import { AccountPanel } from "./AccountPanel";
import { useI18n } from "./i18n";

interface Props {
  user: AuthUser;
  publicDemo: boolean;
  onAdmin: () => void;
  onLogout: () => Promise<void>;
  onAccountDeleted: () => void;
}

export function SettingsWorkspace({
  user,
  publicDemo,
  onAdmin,
  onLogout,
  onAccountDeleted
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";

  return (
    <main className="settings-v2-page">
      <aside className="settings-v2-note">
        <span className="portal-v2-tape">SETTINGS</span>
        <h1>{zh ? "账户、Key 与 Runtime" : "Account, keys & runtime"}</h1>
        <p>
          {zh
            ? "把个人账户、安全边界和系统级 Runtime 配置放在同一页；普通创作流程不再需要从工具箱里找设置。"
            : "Account security and system-level runtime controls live here instead of being hidden inside the toolbox."}
        </p>
        {user.role === "admin" && !publicDemo && (
          <button className="ink-button" type="button" onClick={onAdmin}>
            {zh ? "打开管理员 Runtime 设置" : "Open Admin Runtime Settings"}
          </button>
        )}
        <div className="settings-v2-sticker">PRIVATE / CREATOR SPACE</div>
      </aside>
      <section className="settings-v2-content">
        <AccountPanel
          embedded
          user={user}
          onClose={() => undefined}
          onLogout={onLogout}
          onDeleted={onAccountDeleted}
        />
      </section>
    </main>
  );
}
