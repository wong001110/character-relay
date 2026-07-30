import { useEffect, useState, type FormEvent } from "react";

import {
  api,
  type AdminAccount,
  type AuditEventView,
  type AuthSession,
  type AuthUser,
  type InvitationView
} from "./api";
import { useI18n } from "./i18n";

interface Props {
  user: AuthUser;
  onClose: () => void;
  onLogout: () => Promise<void>;
  onDeleted: () => void;
}

type Tab = "sessions" | "data" | "admin";

const copy = {
  en: {
    title: "Account & security",
    sessions: "Sessions",
    data: "Data & account",
    admin: "Admin control",
    current: "Current",
    revoke: "Revoke",
    logout: "Sign out",
    export: "Export my workspace",
    exportHint:
      "Downloads a secret-free JSON archive of your Character Cards, tests, Runs, and evidence.",
    danger: "Delete account",
    dangerHint:
      "This permanently removes your workspace, sessions, and encrypted credentials. Audit references are anonymized and retained.",
    email: "Confirm email",
    confirmation: "Type DELETE MY ACCOUNT",
    delete: "Delete account permanently",
    invitations: "Invitations",
    inviteEmail: "Email (optional)",
    inviteRole: "Initial role",
    inviteDays: "Expires in days",
    createInvite: "Create invitation",
    newCode: "Invitation code — copy now",
    users: "Users",
    audit: "Audit events",
    claim: "Claim legacy local workspace",
    claimHint:
      "Moves pre-authentication local-user data into this Admin account. This is a one-time migration action.",
    rotate: "Rotate encrypted credentials",
    rotateHint:
      "Re-encrypts all Character and Runtime credentials with the current primary key.",
    active: "active",
    accepted: "accepted",
    revoked: "revoked",
    expired: "expired",
    working: "Working…",
    empty: "Nothing to show.",
    close: "Close",
    loadError: "Could not load account data."
  },
  "zh-CN": {
    title: "账户与安全",
    sessions: "登录设备",
    data: "数据与账户",
    admin: "管理员控制",
    current: "当前",
    revoke: "撤销",
    logout: "退出登录",
    export: "导出我的工作区",
    exportHint: "下载不含密钥的 JSON 备份，包含角色卡、测试、Run 与证据。",
    danger: "删除账户",
    dangerHint: "永久删除工作区、Session 与加密凭证。Audit 引用会匿名化后保留。",
    email: "确认邮箱",
    confirmation: "输入 DELETE MY ACCOUNT",
    delete: "永久删除账户",
    invitations: "邀请",
    inviteEmail: "邮箱（可选）",
    inviteRole: "初始角色",
    inviteDays: "有效天数",
    createInvite: "创建邀请",
    newCode: "邀请码——请立即复制",
    users: "用户",
    audit: "Audit 事件",
    claim: "认领旧版本地工作区",
    claimHint: "将认证上线前的 local-user 数据迁移到当前管理员账户。此操作只能执行一次。",
    rotate: "轮换加密凭证",
    rotateHint: "使用当前主密钥重新加密全部角色与 Runtime 凭证。",
    active: "有效",
    accepted: "已使用",
    revoked: "已撤销",
    expired: "已过期",
    working: "处理中…",
    empty: "暂无数据。",
    close: "关闭",
    loadError: "无法加载账户数据。"
  }
} as const;

export function AccountPanel({ user, onClose, onLogout, onDeleted }: Props) {
  const { language } = useI18n();
  const t = copy[language];
  const [tab, setTab] = useState<Tab>("sessions");
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [invitations, setInvitations] = useState<InvitationView[]>([]);
  const [users, setUsers] = useState<AdminAccount[]>([]);
  const [audit, setAudit] = useState<AuditEventView[]>([]);
  const [newCode, setNewCode] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void loadSessions();
  }, []);

  useEffect(() => {
    if (tab === "admin" && user.role === "admin") void loadAdmin();
  }, [tab, user.role]);

  async function loadSessions() {
    try {
      setSessions(await api.listSessions());
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t.loadError);
    }
  }

  async function loadAdmin() {
    try {
      const [nextInvitations, nextUsers, nextAudit] = await Promise.all([
        api.listInvitations(),
        api.listAdminUsers(),
        api.listAuditEvents()
      ]);
      setInvitations(nextInvitations);
      setUsers(nextUsers);
      setAudit(nextAudit);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t.loadError);
    }
  }

  async function run(action: () => Promise<void>) {
    try {
      setWorking(true);
      setMessage(null);
      await action();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function exportWorkspace() {
    await run(async () => {
      const archive = await api.exportAccount();
      const blob = new Blob([JSON.stringify(archive, null, 2)], {
        type: "application/json"
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `echo-masque-workspace-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    });
  }

  async function submitDelete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await run(async () => {
      await api.deleteAccount(
        String(values.get("email") ?? ""),
        String(values.get("confirmation") ?? "")
      );
      onDeleted();
    });
  }

  async function submitInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await run(async () => {
      const created = await api.createInvitation({
        email: String(values.get("email") ?? "") || null,
        role: String(values.get("role") ?? "user") as "user" | "admin",
        expires_in_days: Number(values.get("days") ?? 7)
      });
      setNewCode(created.code);
      await loadAdmin();
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="account-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="close-button" onClick={onClose} aria-label={t.close}>
          ×
        </button>
        <p className="tape-label">{user.role === "admin" ? "ADMIN" : "ACCOUNT"}</p>
        <h2 id="account-title">{t.title}</h2>
        <p className="account-identity">
          <strong>{user.display_name}</strong>
          <span>{user.email}</span>
        </p>

        <div className="account-tabs" role="tablist">
          <button
            className={tab === "sessions" ? "active" : ""}
            onClick={() => setTab("sessions")}
          >
            {t.sessions}
          </button>
          <button
            className={tab === "data" ? "active" : ""}
            onClick={() => setTab("data")}
          >
            {t.data}
          </button>
          {user.role === "admin" && (
            <button
              className={tab === "admin" ? "active" : ""}
              onClick={() => setTab("admin")}
            >
              {t.admin}
            </button>
          )}
        </div>

        {message && (
          <p className="error-note" role="alert">
            {message}
          </p>
        )}

        {tab === "sessions" && (
          <div className="account-section">
            <div className="session-list">
              {sessions.length === 0 && <p>{t.empty}</p>}
              {sessions.map((session) => (
                <article key={session.id} className="session-row">
                  <div>
                    <strong>{new Date(session.last_seen_at).toLocaleString()}</strong>
                    <small>{new Date(session.expires_at).toLocaleDateString()}</small>
                  </div>
                  {session.current ? (
                    <span className="status-chip pass">{t.current}</span>
                  ) : (
                    <button
                      className="paper-button"
                      disabled={working || session.revoked_at !== null}
                      onClick={() =>
                        void run(async () => {
                          await api.revokeSession(session.id);
                          await loadSessions();
                        })
                      }
                    >
                      {t.revoke}
                    </button>
                  )}
                </article>
              ))}
            </div>
            <button
              className="paper-button danger-button"
              disabled={working}
              onClick={() => void onLogout()}
            >
              {t.logout}
            </button>
          </div>
        )}

        {tab === "data" && (
          <div className="account-section account-data-grid">
            <article className="account-action-card">
              <h3>{t.export}</h3>
              <p>{t.exportHint}</p>
              <button
                className="paper-button"
                disabled={working}
                onClick={() => void exportWorkspace()}
              >
                {t.export}
              </button>
            </article>
            <article className="account-action-card danger-zone">
              <h3>{t.danger}</h3>
              <p>{t.dangerHint}</p>
              <form onSubmit={submitDelete}>
                <label>
                  {t.email}
                  <input name="email" type="email" required />
                </label>
                <label>
                  {t.confirmation}
                  <input name="confirmation" required autoComplete="off" />
                </label>
                <button className="ink-button danger-button" disabled={working}>
                  {t.delete}
                </button>
              </form>
            </article>
          </div>
        )}

        {tab === "admin" && user.role === "admin" && (
          <div className="account-section admin-lifecycle-grid">
            <article className="account-action-card">
              <h3>{t.invitations}</h3>
              <form className="compact-form" onSubmit={submitInvitation}>
                <label>
                  {t.inviteEmail}
                  <input name="email" type="email" />
                </label>
                <label>
                  {t.inviteRole}
                  <select name="role">
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                </label>
                <label>
                  {t.inviteDays}
                  <input name="days" type="number" min="1" max="30" defaultValue="7" />
                </label>
                <button className="paper-button" disabled={working}>
                  {t.createInvite}
                </button>
              </form>
              {newCode && (
                <div className="invitation-code">
                  <strong>{t.newCode}</strong>
                  <code>{newCode}</code>
                  <button
                    className="paper-button"
                    onClick={() => void navigator.clipboard.writeText(newCode)}
                  >
                    Copy
                  </button>
                </div>
              )}
              <div className="compact-list">
                {invitations.map((item) => (
                  <div key={item.id}>
                    <span>
                      {item.email ?? "*"} · {item.role}
                    </span>
                    <span className="status-chip">{t[item.status]}</span>
                    {item.status === "active" && (
                      <button
                        onClick={() =>
                          void run(async () => {
                            await api.revokeInvitation(item.id);
                            await loadAdmin();
                          })
                        }
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </article>

            <article className="account-action-card">
              <h3>{t.users}</h3>
              <div className="compact-list">
                {users.map((item) => (
                  <div key={item.id}>
                    <span>
                      {item.display_name}
                      <small>{item.email}</small>
                    </span>
                    <select
                      value={item.role}
                      disabled={working || item.id === user.id}
                      onChange={(event) =>
                        void run(async () => {
                          await api.updateUserRole(
                            item.id,
                            event.target.value as "user" | "admin"
                          );
                          await loadAdmin();
                        })
                      }
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </div>
                ))}
              </div>
            </article>

            <article className="account-action-card">
              <h3>{t.claim}</h3>
              <p>{t.claimHint}</p>
              <button
                className="paper-button"
                disabled={working}
                onClick={() =>
                  void run(async () => {
                    const result = await api.claimLocalWorkspace();
                    setMessage(JSON.stringify(result.affected));
                  })
                }
              >
                {t.claim}
              </button>
              <h3>{t.rotate}</h3>
              <p>{t.rotateHint}</p>
              <button
                className="paper-button"
                disabled={working}
                onClick={() =>
                  void run(async () => {
                    const result = await api.rotateCredentialVault();
                    setMessage(`${result.rotated_count} · ${result.key_version}`);
                  })
                }
              >
                {t.rotate}
              </button>
            </article>

            <article className="account-action-card audit-card">
              <h3>{t.audit}</h3>
              <div className="audit-list">
                {audit.slice(0, 80).map((item) => (
                  <div key={item.id}>
                    <strong>{item.action}</strong>
                    <span>
                      {item.resource_type} · {new Date(item.created_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </article>
          </div>
        )}

        {working && <p className="working-note">{t.working}</p>}
      </section>
    </div>
  );
}
