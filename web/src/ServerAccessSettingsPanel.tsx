import { useEffect, useState, type FormEvent } from "react";

import { FunctionalIcon } from "./components/ui";
import { NotebookField, NotebookInput } from "./NotebookUI";
import {
  serverAccessApi,
  type ServerAccessOverview
} from "./serverAccessApi";

interface Props {
  onOverviewChange?: (overview: ServerAccessOverview) => void;
}

export function ServerAccessSettingsPanel({ onOverviewChange }: Props) {
  const [overview, setOverview] = useState<ServerAccessOverview | null>(null);
  const [joinCode, setJoinCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const next = await serverAccessApi.overview();
      setOverview(next);
      onOverviewChange?.(next);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Could not load server access.");
    }
  }

  async function join(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!joinCode.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const joined = await serverAccessApi.join(joinCode.trim());
      setJoinCode("");
      setMessage(`Joined ${joined.guild_name}.`);
      await load();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Could not join server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-panel-stack">
      {message && <p className="settings-inline-message" role="status">{message}</p>}

      {overview?.is_super_admin ? (
        <aside className="settings-sticky-note settings-sticky-note-mint">
          <FunctionalIcon name="boundaries" size={18} />
          <div>
            <strong>Super Admin access</strong>
            <span>You can open and manage every Discord server synchronized by the global connector.</span>
          </div>
        </aside>
      ) : (
        <section className="settings-paper-card settings-join-card">
          <div className="settings-card-heading">
            <span className="settings-card-icon"><FunctionalIcon name="provider" size={18} /></span>
            <div>
              <p className="settings-card-kicker">Join a server</p>
              <h3>Enter the server code</h3>
              <p>Ask the Character Relay server owner or Super Admin for its current join code.</p>
            </div>
          </div>
          <form className="settings-join-form" onSubmit={join}>
            <NotebookField label="Server join code" guide="Example: CR-8K3F2A7Q">
              <NotebookInput
                value={joinCode}
                onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
                placeholder="CR-XXXXXXXX"
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
              />
            </NotebookField>
            <button className="settings-action-button" type="submit" disabled={busy || !joinCode.trim()}>
              <FunctionalIcon name="provider" size={16} /> {busy ? "Joining…" : "Join server"}
            </button>
          </form>
        </section>
      )}

      <section className="settings-paper-card">
        <div className="settings-card-heading">
          <span className="settings-card-icon settings-card-icon-mint"><FunctionalIcon name="deployment" size={18} /></span>
          <div>
            <p className="settings-card-kicker">Server access</p>
            <h3>{overview?.is_super_admin ? "All servers" : "Your servers"}</h3>
            <p>
              {overview?.is_super_admin
                ? "Global access is inherited from the Super Admin role."
                : "Servers listed here are the Discord workspaces your account can use."}
            </p>
          </div>
        </div>

        <div className="settings-server-grid">
          {overview?.servers.map((server) => (
            <article className="settings-server-card" key={`${server.connection_id}:${server.guild_id}`}>
              <div className="settings-server-pin" aria-hidden />
              <div className="settings-server-card-title">
                <span className="settings-server-icon"><FunctionalIcon name="deployment" size={16} /></span>
                <div>
                  <strong>{server.guild_name}</strong>
                  <small>Discord server</small>
                </div>
              </div>
              <dl>
                <div><dt>Server ID</dt><dd>{server.guild_id}</dd></div>
                <div>
                  <dt>Access</dt>
                  <dd>{server.access_source === "super_admin" ? "Super Admin" : "Member"}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>

        {overview && overview.servers.length === 0 && (
          <aside className="settings-sticky-note">
            <FunctionalIcon name="deployment" size={18} />
            <div>
              <strong>No server joined yet</strong>
              <span>Use a join code above. You do not need to configure a Discord connector.</span>
            </div>
          </aside>
        )}
      </section>
    </div>
  );
}
