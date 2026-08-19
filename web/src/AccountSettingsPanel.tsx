import { Download, LogOut, ShieldCheck, Trash2, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api, type AuthSession, type AuthUser } from "./api";
import { NotebookField, NotebookInput } from "./NotebookUI";

interface Props {
  user: AuthUser;
  onSignedOut: () => void;
}

export function AccountSettingsPanel({ user, onSignedOut }: Props) {
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void loadSessions();
  }, []);

  async function loadSessions() {
    try {
      setSessions(await api.listSessions());
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Could not load sessions.");
    }
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
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
      anchor.download = `character-relay-workspace-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    });
  }

  async function signOut() {
    await run(async () => {
      await api.logout();
      onSignedOut();
    });
  }

  async function revokeSession(sessionId: string) {
    await run(async () => {
      await api.revokeSession(sessionId);
      await loadSessions();
    });
  }

  async function deleteAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await run(async () => {
      await api.deleteAccount(
        String(values.get("email") ?? ""),
        String(values.get("confirmation") ?? "")
      );
      onSignedOut();
    });
  }

  return (
    <div className="settings-panel-stack">
      {message && <p className="settings-inline-message" role="status">{message}</p>}

      <section className="settings-paper-card settings-profile-card">
        <div className="settings-card-heading">
          <span className="settings-card-icon"><UserRound size={18} aria-hidden /></span>
          <div>
            <p className="settings-card-kicker">Profile</p>
            <h3>Your account</h3>
            <p>This is your Character Relay identity. Server access is managed separately.</p>
          </div>
        </div>
        <dl className="settings-detail-grid">
          <div><dt>Display name</dt><dd>{user.display_name}</dd></div>
          <div><dt>Email</dt><dd>{user.email}</dd></div>
          <div><dt>Global role</dt><dd>{user.role === "admin" ? "Admin" : "User"}</dd></div>
        </dl>
      </section>

      <section className="settings-paper-card">
        <div className="settings-card-heading">
          <span className="settings-card-icon settings-card-icon-mint"><ShieldCheck size={18} aria-hidden /></span>
          <div>
            <p className="settings-card-kicker">Security</p>
            <h3>Sessions</h3>
            <p>Review active sign-ins without mixing them with user administration.</p>
          </div>
        </div>
        <div className="settings-list">
          {sessions.map((session) => (
            <div className="settings-list-row" key={session.id}>
              <div>
                <strong>{session.current ? "Current session" : "Signed-in session"}</strong>
                <span>Last seen {new Date(session.last_seen_at).toLocaleString()}</span>
                <small>Expires {new Date(session.expires_at).toLocaleString()}</small>
              </div>
              {!session.current && !session.revoked_at && (
                <button
                  className="settings-text-button"
                  type="button"
                  disabled={busy}
                  onClick={() => void revokeSession(session.id)}
                >
                  Revoke
                </button>
              )}
            </div>
          ))}
          {sessions.length === 0 && <p className="settings-empty-copy">No session details available.</p>}
        </div>
        <button className="settings-action-button" type="button" disabled={busy} onClick={() => void signOut()}>
          <LogOut size={16} aria-hidden /> Sign out
        </button>
      </section>

      <section className="settings-paper-card">
        <div className="settings-card-heading">
          <span className="settings-card-icon settings-card-icon-peach"><Download size={18} aria-hidden /></span>
          <div>
            <p className="settings-card-kicker">Data</p>
            <h3>Workspace data</h3>
            <p>Export your account-owned Character Relay data as a secret-free JSON archive.</p>
          </div>
        </div>
        <button className="settings-action-button" type="button" disabled={busy} onClick={() => void exportWorkspace()}>
          <Download size={16} aria-hidden /> Export my workspace
        </button>
      </section>

      <details className="settings-danger-note">
        <summary><Trash2 size={15} aria-hidden /> Delete account</summary>
        <p>This permanently removes your account-owned workspace and credentials.</p>
        <form className="settings-danger-form" onSubmit={deleteAccount}>
          <NotebookField label="Confirm email">
            <NotebookInput name="email" type="email" required placeholder={user.email} />
          </NotebookField>
          <NotebookField label="Confirmation" guide="Type DELETE MY ACCOUNT">
            <NotebookInput name="confirmation" required autoComplete="off" />
          </NotebookField>
          <button className="settings-danger-button" type="submit" disabled={busy}>
            Delete account permanently
          </button>
        </form>
      </details>
    </div>
  );
}
