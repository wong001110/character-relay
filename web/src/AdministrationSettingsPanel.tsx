import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  api,
  type AdminAccount,
  type AuditEventView,
  type AuthUser,
  type InvitationView,
  type Page
} from "./api";
import { FunctionalIcon } from "./components/ui";
import { deploymentApi, type PlatformConnection } from "./deploymentApi";
import { NotebookField, NotebookInput, NotebookSelect } from "./NotebookUI";
import { Pagination } from "./Pagination";
import {
  serverAccessApi,
  type AdminServerAccess
} from "./serverAccessApi";

type AdminTab = "users" | "servers" | "connector";

interface Props {
  user: AuthUser;
}

const ACCOUNT_PAGE_SIZE = 20;
const ACCOUNT_SEARCH_DELAY_MS = 300;

interface ServerAccountPickerProps {
  server: AdminServerAccess;
  currentUserId: string;
  busy: boolean;
  onGrant: (server: AdminServerAccess, userId: string) => Promise<boolean>;
}

function ServerAccountPicker({
  server,
  currentUserId,
  busy,
  onGrant
}: ServerAccountPickerProps) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<AdminAccount[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const excludedUserIds = useMemo(
    () => new Set([currentUserId, ...server.members.map((member) => member.user_id)]),
    [currentUserId, server.members]
  );

  useEffect(() => {
    const search = query.trim();
    if (search.length < 2) {
      setOptions([]);
      setSearching(false);
      setSearchFailed(false);
      return;
    }

    let active = true;
    const timer = window.setTimeout(() => {
      setSearching(true);
      setSearchFailed(false);
      void api.listAdminUsersPage({ search, pageSize: ACCOUNT_PAGE_SIZE })
        .then((result) => {
          if (active) {
            setOptions(
              result.items.filter((account) => !excludedUserIds.has(account.id))
            );
          }
        })
        .catch(() => {
          if (active) {
            setOptions([]);
            setSearchFailed(true);
          }
        })
        .finally(() => {
          if (active) setSearching(false);
        });
    }, ACCOUNT_SEARCH_DELAY_MS);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [excludedUserIds, query]);

  async function grant() {
    if (!selectedUserId) return;
    if (await onGrant(server, selectedUserId)) {
      setQuery("");
      setOptions([]);
      setSelectedUserId("");
    }
  }

  let resultHint = `${options.length} matching account${options.length === 1 ? "" : "s"}`;
  if (query.trim().length < 2) resultHint = "Type at least 2 characters";
  if (searchFailed) resultHint = "Search unavailable — try again";
  if (searching) resultHint = "Searching…";

  return (
    <div className="settings-member-add settings-member-search">
      <NotebookField label="Search account" guide={resultHint}>
        <NotebookInput
          value={query}
          type="search"
          autoComplete="off"
          placeholder="Name or email"
          maxLength={320}
          disabled={busy}
          onChange={(event) => {
            setQuery(event.target.value);
            setSelectedUserId("");
          }}
        />
      </NotebookField>
      <NotebookSelect
        aria-label={`Choose account to add to ${server.guild_name}`}
        value={selectedUserId}
        disabled={busy || searching || options.length === 0}
        onChange={(event) => setSelectedUserId(event.target.value)}
      >
        <option value="">Choose account…</option>
        {options.map((account) => (
          <option key={account.id} value={account.id}>
            {account.display_name} · {account.email}
          </option>
        ))}
      </NotebookSelect>
      <button
        className="settings-action-button"
        type="button"
        disabled={busy || !selectedUserId}
        onClick={() => void grant()}
      >
        <FunctionalIcon name="identity" size={16} /> Add account
      </button>
    </div>
  );
}

export function AdministrationSettingsPanel({ user }: Props) {
  const [tab, setTab] = useState<AdminTab>("users");
  const [servers, setServers] = useState<AdminServerAccess[]>([]);
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [invitations, setInvitations] = useState<InvitationView[]>([]);
  const [audit, setAudit] = useState<AuditEventView[]>([]);
  const [userPage, setUserPage] = useState(1);
  const [userResult, setUserResult] = useState<Page<AdminAccount>>({
    items: [],
    page: 1,
    page_size: ACCOUNT_PAGE_SIZE,
    total: 0,
    pages: 1
  });
  const [usersLoading, setUsersLoading] = useState(false);
  const [pendingDeleteUserId, setPendingDeleteUserId] = useState<string | null>(null);
  const [newInvitationCode, setNewInvitationCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    let active = true;
    setUsersLoading(true);
    void api.listAdminUsersPage({ page: userPage, pageSize: ACCOUNT_PAGE_SIZE })
      .then((result) => {
        if (!active) return;
        setUserResult(result);
        if (result.page !== userPage) setUserPage(result.page);
      })
      .catch((reason: unknown) => {
        if (active) {
          setMessage(
            reason instanceof Error ? reason.message : "Could not load accounts."
          );
        }
      })
      .finally(() => {
        if (active) setUsersLoading(false);
      });
    return () => {
      active = false;
    };
  }, [userPage]);

  async function load() {
    try {
      const [nextServers, nextConnections, nextInvitations, nextAudit] =
        await Promise.all([
          serverAccessApi.listAdminServers(),
          deploymentApi.listConnections(),
          api.listInvitations(),
          api.listAuditEventsPage(null, 12)
        ]);
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

  async function run(action: () => Promise<void>): Promise<boolean> {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      return true;
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
      return false;
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
      setUserResult((current) => ({
        ...current,
        items: current.items.map((item) => (item.id === updated.id ? updated : item))
      }));
    });
  }

  async function reloadUsers(page = userPage) {
    const result = await api.listAdminUsersPage({ page, pageSize: ACCOUNT_PAGE_SIZE });
    setUserResult(result);
    if (result.page !== userPage) setUserPage(result.page);
  }

  async function deleteUser(account: AdminAccount) {
    if (account.id === user.id) return;
    await run(async () => {
      await api.deleteAdminUser(account.id);
      const [nextServers] = await Promise.all([
        serverAccessApi.listAdminServers(),
        reloadUsers(userPage)
      ]);
      setServers(nextServers);
      setPendingDeleteUserId(null);
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

  async function grantMember(
    server: AdminServerAccess,
    userId: string
  ): Promise<boolean> {
    return run(async () => {
      replaceServer(await serverAccessApi.grantMember(server.guild_id, userId));
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

      <div className="settings-runtime-strip settings-component-library-strip">
        <div>
          <strong>Component Library</strong>
          <span>
            Open the Super Admin-only living catalog to review every registered reusable
            component, category, and visual state.
          </span>
        </div>
        <a className="settings-action-button" href="/dev/ui">
          <FunctionalIcon name="review" size={16} /> Open Component Library
        </a>
      </div>

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
              {userResult.items.map((account) => {
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
                    <div className="settings-user-actions">
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
                      {account.id !== user.id &&
                        (pendingDeleteUserId === account.id ? (
                          <div
                            className="settings-user-delete-confirm"
                            role="group"
                            aria-label={`Confirm deletion of ${account.display_name}`}
                          >
                            <span>Delete account and workspace?</span>
                            <button
                              className="settings-danger-button"
                              type="button"
                              disabled={busy}
                              onClick={() => void deleteUser(account)}
                            >
                              Confirm delete
                            </button>
                            <button
                              className="settings-text-button"
                              type="button"
                              disabled={busy}
                              onClick={() => setPendingDeleteUserId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            className="settings-text-button settings-delete-account-button"
                            type="button"
                            title={`Delete ${account.display_name}`}
                            aria-label={`Delete account ${account.display_name}`}
                            disabled={busy}
                            onClick={() => setPendingDeleteUserId(account.id)}
                          >
                            <FunctionalIcon name="warning" size={15} /> Delete
                          </button>
                        ))}
                    </div>
                  </div>
                );
              })}
              {!usersLoading && userResult.items.length === 0 && (
                <p className="settings-empty-copy">No registered accounts found.</p>
              )}
            </div>
            <Pagination
              page={userResult.page}
              pages={userResult.pages}
              total={userResult.total}
              disabled={busy || usersLoading}
              onPage={(page) => {
                setPendingDeleteUserId(null);
                setUserPage(page);
              }}
            />
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
                  <ServerAccountPicker
                    server={server}
                    currentUserId={user.id}
                    busy={busy}
                    onGrant={grantMember}
                  />
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
