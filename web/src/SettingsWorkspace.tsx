import type { AuthUser } from "./api";
import { AccountPanel } from "./AccountPanel";
import { Button, StickyLabel, StickyNote } from "./components/ui";
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
    <main className="settings-v2-page settings-v3-page">
      <aside className="settings-v2-note settings-v3-note">
        <StickyLabel variant="neutral">SETTINGS / PRIVATE PAGE</StickyLabel>
        <h1>{zh ? "账户、Key 与 Runtime" : "Account, keys & runtime"}</h1>
        <p>
          {zh
            ? "这是手帐后页的私人资料袋：账户安全与系统级 Runtime 配置集中在这里，角色创作流程不再夹杂这些技术设置。"
            : "This is the private pocket at the back of the notebook: account security and system-level runtime controls live here instead of interrupting character authoring."}
        </p>
        {user.role === "admin" && !publicDemo && (
          <Button variant="primary" type="button" onClick={onAdmin}>
            {zh ? "打开管理员 Runtime 设置" : "Open Admin Runtime Settings"}
          </Button>
        )}
        <StickyNote variant="temporary" size="sm">
          <strong>{zh ? "私人空间" : "Private creator space"}</strong>
          <p>{zh ? "Credential、账户删除与管理员配置不会出现在角色档案里。" : "Credentials, account deletion, and admin controls never appear in character files."}</p>
        </StickyNote>
      </aside>
      <section className="settings-v2-content settings-v3-content">
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