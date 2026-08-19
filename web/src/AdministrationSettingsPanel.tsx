import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  api,
  type AdminAccount,
  type AuditEventView,
  type AuthUser,
  type InvitationView
} from "./api";
import { FunctionalIcon } from "./components/ui";
import { deploymentApi, type PlatformConnection } from "./deploymentApi";
import { NotebookField, NotebookInput, NotebookSelect } from "./NotebookUI";
import {
  serverAccessApi,
  type AdminServerAccess
} from "./serverAccessApi";

type AdminTab = "users" | "servers" | "connector";

interface Props {
  user: AuthUser;
}

export function AdministrationSettingsPanel({ user }: Props) {
  const [tab, setTab] = useState<AdminTab>("users");
  const [users, setUsers] = useState<AdminAccount[]>([]);
  const [servers, setServers] = useState<AdminServerAccess[]>([]);
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [invitations, setInvitations] = useState<InvitationView[]>([]);
  const [audit, setAudit] = useState<AuditEventView[]>([]);
  const [selectedUsers, setSelectedUsers] = useState<Record<string, string>>({});
  const [newInvitationCode, setNewInvitationCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const [nextUsers, nextServers, nextConnections, nextInvitations, nextAudit] =
        await Promise.all([
          api.listAdminUsers(),
          serverAccessApi.listAdminServers(),
          deploymentApi.listConnections(),
          api.listInvitations(),
          api.listAuditEventsPage(null, 12)
        ]);
      setUsers(nextUsers);
      setServers(nextServers);
      setConnections(nextConnections);
      setInvitations(nextInvitations);
      setAudit(nextAudit.items);
    } catch (reason) {
      setMessage(
        reason instanceof Error
          ? reason.message
          : "Could not load administration settings."
      );
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

  function replaceServer(next: AdminServerAccess) {
    setServers((current) =>
      current.map((item) => (item.guild_id === next.guild_id ? next : item))
    );
  }

  function userServerCount(userId: string) {
    return servers.reduce(
      (count, server) =>
        count + (server.members.some((member) => member.user_id === userId) ? 1 : 0),
      0
    );
  }

  async function changeRole(account: AdminAccount, role: "user" | "admin") {
    if (account.id === user.id) return;
    await run(async () => {
      const updated = await api.updateUserRole(account.id, role);
      setUsers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
    });
  }

  async function submitInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await run(async () => {
      const created = await api.createInvitation({
        email: String(values.get("email") ?? "").trim() || null,
        role: String(values.get("role") ?? "user") as "user" | "admin",
        expires_in_days: Number(values.get("days") ?? 7)
      });
      setNewInvitationCode(created.code);
      setInvitations(await api.listInvitations());
      form.reset();
    });
  }

  async function revokeInvitation(invitationId: string) {
    await run(async () => {
      await api.revokeInvitation(invitationId);
      setInvitations(await api.listInvitations());
    });
  }

  async function toggleJoin(server: AdminServerAccess) {
    await run(async () => {
      replaceServer(
        await serverAccessApi.setJoinEnabled(server.guild_id, !server.join_enabled)
      );
    });
  }

  async function regenerateCode(server: AdminServerAccess) {
    await run(async () => {
      replaceServer(await serverAccessApi.regenerateJoinCode(server.guild_id));
    });
  }

  async function grantMember(server: AdminServerAccess) {
    const userId = selectedUsers[server.guild_id];
    if (!userId) return;
    await run(async () => {
      replaceServer(await serverAccessApi.grantMember(server.guild_id, userId));
      setSelectedUsers((current) => ({ ...current, [server.guild_id]: "" }));
    });
  }

  async function revokeMember(server: AdminServerAccess, userId: string) {
    await run(async () => {
      replaceServer(await serverAccessApi.revokeMember(server.guild_id, userId));
    });
  }

  const discordConnections = useMemo(
    () => connections.filter((connection) => connection.platform === "discord"),
    [connections]
  );

  return (
    <div className="settings-panel-stack">
      <aside className="settings-sticky-note settings-sticky-note-mint">
        <FunctionalIcon name="boundaries" size={18} />
        <div>
          <strong>Super Admin desk</strong>
          <span>
            Global users, Discord server access, and the shared connector are managed here.
          </span>
        </div>
      </aside>

      <nav className="settings-subtabs" aria-label="Administration sections">
        <button
          type="button"
          className={tab === "users" ? "is-active" : ""}
          onClick={() => setTab("users")}
        >
          <FunctionalIcon name="characters" size={15} /> Users
        </button>
        <button
          type="button"
          className={tab === "servers" ? "is-active" : ""}
          onClick={() => setTab("servers")}
        >
          <FunctionalIcon name="deployment" size={15} /> Servers
        </button>
        <button
          type="button"
          className={tab === "connector" ? "is-active" : ""}
          onClick={() => setTab("connector")}
        >
          <FunctionalIcon name="provider" size={15} /> Discord Connector
        </button>
      </nav>

      {message && (
        <p className="settings-inline-message" role="status">
          {message}
        </p>
      )}

      {tab === "users" && (
        <div className="settings-panel-stack">
          <section className="settings-paper-card">
            <div className="settings-card-heading">
              <span className="settings-card-icon">
                <FunctionalIcon name="characters" size={18} />
              </span>
              <div>
                <p className="settings-card-kicker">Users</p>
                <h3>Registered accounts</h3>
                <p>Global account role stays separate from Discord server access.</p>
              </div>
            </div>
            <div className="settings-list settings-user-list">
              {users.map((account) => {
                const serverCount = userServerCount(account.id);
                return (
                  <div className="settings-list-row" key={account.id}>
                    <div>
                      <strong>{account.display_name}</strong>
                      <span>{account.email}</span>
                      <small>
                        {serverCount} server{serverCount === 1 ? "" : "s"}
                      </small>
                    </div>
                    <NotebookSelect
                      aria-label={`Role for ${account.display_name}`}
                      value={account.role}
                      disabled={busy || account.id === user.id}
                      onChange={(event) =>
                        void changeRole(
                          account,
                          event.target.value as "user" | "admin"
                        )
                      }
                    >
                      <option value="user">User</option>
                      <option value="admin">Admin</option>
                    </NotebookSelect>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="settings-paper-card">
            <div className="settings-card-heading">
              <span className="settings-card-icon settings-card-icon-peach">
                <FunctionalIcon name="identity" size={18} />
              </span>
              <div>
                <p className="settings-card-kicker">Invitations</p>
                <h3>Invite an account</h3>
                <p>
                  Inviting a user does not automatically grant access to any Discord server.
                </p>
              </div>
            </div>
            <form
              className="settings-inline-form settings-invite-form"
              onSubmit={submitInvitation}
            >
              <NotebookField label="Email" guide="Optional">
                <NotebookInput
                  name="email"
                  type="email"
                  placeholder="person@example.com"
                />
              </NotebookField>
              <NotebookField label="Global role">
                <NotebookSelect name="role" defaultValue="user">
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </NotebookSelect>
              </NotebookField>
              <NotebookField label="Expires in days">
                <NotebookInput
                  name="days"
                  type="number"
                  min={1}
                  max={30}
                  defaultValue={7}
                />
              </NotebookField>
              <button
                className="settings-action-button"
                type="submit"
                disabled={busy}
              >
                Create invitation
              </button>
            </form>
            {newInvitationCode && (
              <aside className="settings-sticky-note">
                <FunctionalIcon name="provider" size={18} />
                <div>
                  <strong>Copy this invitation code now</strong>
                  <code>{newInvitationCode}</code>
                </div>
              </aside>
            )}
            <div className="settings-list">
              {invitations
                .filter((item) => item.status === "active")
                .map((invitation) => (
                  <div className="settings-list-row" key={invitation.id}>
                    <div>
                      <strong>{invitation.email || "Open invitation"}</strong>
                      <span>
                        {invitation.role.toUpperCase()} · expires{" "}
                        {new Date(invitation.expires_at).toLocaleDateString()}
                      </span>
                    </div>
                    <button
                      className="settings-text-button"
                      type="button"
                      disabled={busy}
                      onClick={() => void revokeInvitation(invitation.id)}
                    >
                      Revoke
                    </button>
                  </div>
                ))}
            </div>
          </section>

          <section className="settings-paper-card">
            <div className="settings-card-heading">
              <span className="settings-card-icon settings-card-icon-mint">
                <FunctionalIcon name="review" size={18} />
              </span>
              <div>
                <p className="settings-card-kicker">Audit</p>
                <h3>Recent account activity</h3>
                <p>
                  A small trace stays close to user administration without taking over the page.
                </p>
              </div>
            </div>
            <div className="settings-list settings-audit-list">
              {audit.map((event) => (
                <div className="settings-list-row" key={event.id}>
                  <div>
                    <strong>{event.action}</strong>
                    <span>{event.resource_type}</span>
                  </div>
                  <small>{new Date(event.created_at).toLocaleString()}</small>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {tab === "servers" && (
        <div className="settings-server-admin-list">
          {servers.map((server) => {
            const availableUsers = users.filter(
              (account) =>
                account.id !== user.id &&
                !server.members.some((member) => member.user_id === account.id)
            );
            return (
              <section
                className="settings-paper-card settings-admin-server-card"
                key={`${server.connection_id}:${server.guild_id}`}
              >
                <div className="settings-card-heading">
                  <span className="settings-card-icon settings-card-icon-mint">
                    <FunctionalIcon name="deployment" size={18} />
                  </span>
                  <div>
                    <p className="settings-card-kicker">Discord server</p>
                    <h3>{server.guild_name}</h3>
                    <p>
                      {server.members.length} assigned account
                      {server.members.length === 1 ? "" : "s"} · synced{" "}
                      {new Date(server.synced_at).toLocaleString()}
                    </p>
                  </div>
                </div>

                <div className="settings-code-strip">
                  <div>
                    <span>Join code</span>
                    <code>{server.join_code}</code>
                  </div>
                  <button
                    type="button"
                    className="settings-icon-button"
                    title="Copy join code"
                    aria-label="Copy join code"
                    onClick={() =>
                      void navigator.clipboard.writeText(server.join_code)
                    }
                  >
                    <FunctionalIcon name="archive" size={16} />
                  </button>
                  <button
                    type="button"
                    className="settings-icon-button"
                    title="Regenerate join code"
                    aria-label="Regenerate join code"
                    disabled={busy}
                    onClick={() => void regenerateCode(server)}
                  >
                    <FunctionalIcon name="refresh" size={16} />
                  </button>
                  <button
                    type="button"
                    className={`settings-toggle${server.join_enabled ? " is-on" : ""}`}
                    disabled={busy}
                    onClick={() => void toggleJoin(server)}
                  >
                    {server.join_enabled ? "Join enabled" : "Join disabled"}
                  </button>
                </div>

                <div className="settings-member-block">
                  <div className="settings-member-heading">
                    <strong>Server access</strong>
                    <span>Super Admin is implicit and is not repeated here.</span>
                  </div>
                  <div className="settings-list">
                    {server.members.map((member) => (
                      <div className="settings-list-row" key={member.user_id}>
                        <div>
                          <strong>{member.display_name}</strong>
                          <span>{member.email}</span>
                          <small>Member</small>
                        </div>
                        <button
                          className="settings-icon-button"
                          type="button"
                          title="Remove server access"
                          aria-label={`Remove ${member.display_name} from ${server.guild_name}`}
                          disabled={busy}
                          onClick={() => void revokeMember(server, member.user_id)}
                        >
                          <FunctionalIcon name="close" size={15} />
                        </button>
                      </div>
                    ))}
                    {server.members.length === 0 && (
                      <p className="settings-empty-copy">No accounts assigned yet.</p>
                    )}
                  </div>
                  {availableUsers.length > 0 && (
                    <div className="settings-member-add">
                      <NotebookSelect
                        aria-label={`Add account to ${server.guild_name}`}
                        value={selectedUsers[server.guild_id] ?? ""}
                        onChange={(event) =>
                          setSelectedUsers((current) => ({
                            ...current,
                            [server.guild_id]: event.target.value
                          }))
                        }
                      >
                        <option value="">Choose account…</option>
                        {availableUsers.map((account) => (
                          <option key={account.id} value={account.id}>
                            {account.display_name} · {account.email}
                          </option>
                        ))}
                      </NotebookSelect>
                      <button
                        className="settings-action-button"
                        type="button"
                        disabled={busy || !selectedUsers[server.guild_id]}
                        onClick={() => void grantMember(server)}
                      >
                        <FunctionalIcon name="identity" size={16} /> Add account
                      </button>
                    </div>
                  )}
                </div>
              </section>
            );
          })}
          {servers.length === 0 && (
            <aside className="settings-sticky-note">
              <FunctionalIcon name="deployment" size={18} />
              <div>
                <strong>No Discord servers synchronized</strong>
                <span>The connector has not reported a server yet.</span>
              </div>
            </aside>
          )}
        </div>
      )}

      {tab === "connector" && (
        <div className="settings-panel-stack">
          <section className="settings-paper-card settings-connector-card">
            <div className="settings-card-heading">
              <span className="settings-card-icon">
                <FunctionalIcon name="provider" size={18} />
              </span>
              <div>
                <p className="settings-card-kicker">Global infrastructure</p>
                <h3>Discord Connector</h3>
                <p>
                  One managed connector serves every Character Relay account. Only the Super
                  Admin can configure it.
                </p>
              </div>
            </div>
            {discordConnections.map((connection) => (
              <div className="settings-connector-status" key={connection.id}>
                <span
                  className={`settings-status-dot status-${connection.status}`}
                  aria-hidden
                />
                <div>
                  <strong>{connection.display_name}</strong>
                  <span>{connection.status}</span>
                </div>
                <dl>
                  <div>
                    <dt>Connected servers</dt>
                    <dd>{servers.length}</dd>
                  </div>
                  <div>
                    <dt>Mode</dt>
                    <dd>{connection.connection_mode}</dd>
                  </div>
                </dl>
              </div>
            ))}
            {discordConnections.length === 0 && (
              <p className="settings-empty-copy">
                No managed Discord connector is configured.
              </p>
            )}
            <button
              className="settings-action-button"
              type="button"
              disabled={busy}
              onClick={() => void run(load)}
            >
              <FunctionalIcon name="refresh" size={16} /> Refresh connector status
            </button>
          </section>
          <aside className="settings-sticky-note settings-sticky-note-peach">
            <FunctionalIcon name="provider" size={18} />
            <div>
              <strong>Accounts do not own connectors</strong>
              <span>
                Users only receive Server Access. Bot credentials stay global and Super
                Admin-controlled.
              </span>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
