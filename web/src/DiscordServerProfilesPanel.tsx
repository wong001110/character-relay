import { useMemo, useState, type FormEvent } from "react";

import {
  deploymentApi,
  type ConnectionMode,
  type DiscordCatalogChannel,
  type DiscordServerCatalog,
  type DiscordServerProfile,
  type PlatformConnection
} from "./deploymentApi";
import { PaperDrawer } from "./NotebookUI";
import { ServerStickerDictionary } from "./ServerStickerDictionary";
import { browserTimezone, serverRuntimeApi } from "./serverRuntimeApi";

interface Props {
  connections: PlatformConnection[];
  profiles: DiscordServerProfile[];
  catalog: DiscordServerCatalog[];
  selectedProfileId: string;
  demoMode: boolean;
  zh: boolean;
  onSelectProfile: (profileId: string) => void;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
  onOpenLogs: () => void;
}

interface ChannelGroup {
  id: string;
  name: string;
  channels: DiscordCatalogChannel[];
}

type DrawerTab = "settings" | "stickers";

function groupsFor(server: DiscordServerCatalog | undefined): ChannelGroup[] {
  if (!server) return [];
  const groups = new Map<string, ChannelGroup>();
  for (const channel of server.channels) {
    const key = channel.category_id || "@uncategorized";
    const current = groups.get(key) ?? {
      id: channel.category_id,
      name: channel.category_name || "Uncategorized",
      channels: []
    };
    current.channels.push(channel);
    groups.set(key, current);
  }
  return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name));
}

export function DiscordServerProfilesPanel({
  connections,
  profiles,
  catalog,
  selectedProfileId,
  demoMode,
  zh,
  onSelectProfile,
  onChanged,
  onError,
  onOpenLogs
}: Props) {
  const discordConnections = connections.filter((item) => item.platform === "discord");
  const selectedProfile = profiles.find((item) => item.id === selectedProfileId) ?? null;
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<DiscordServerProfile | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("settings");
  const [working, setWorking] = useState(false);
  const [connectionId, setConnectionId] = useState(discordConnections[0]?.id ?? "");
  const [claimGuildId, setClaimGuildId] = useState("");
  const [guildId, setGuildId] = useState("");
  const [profileName, setProfileName] = useState("");
  const [serverTimezone, setServerTimezone] = useState(browserTimezone());
  const [excludedChannels, setExcludedChannels] = useState<Set<string>>(new Set());
  const [excludedCategories, setExcludedCategories] = useState<Set<string>>(new Set());
  const [connectionEditorOpen, setConnectionEditorOpen] = useState(false);
  const [connectionDisplayName, setConnectionDisplayName] = useState("");
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("managed");
  const [connectionExternalAccountId, setConnectionExternalAccountId] = useState("");

  const availableServers = useMemo(
    () => catalog.filter((server) => server.connection_id === connectionId),
    [catalog, connectionId]
  );
  const selectedServer = availableServers.find((server) => server.guild_id === guildId);
  const groups = useMemo(() => groupsFor(selectedServer), [selectedServer]);
  const selectedConnection = connections.find(
    (item) => item.id === selectedProfile?.connection_id
  );
  const workspaceConnection = selectedConnection ?? discordConnections[0];
  const connectionShared = workspaceConnection?.metadata.shared_connection === true;
  const canEditConnection = Boolean(workspaceConnection && !demoMode && !connectionShared);
  const selectedServerCatalog = selectedProfile
    ? catalog.find(
        (item) =>
          item.connection_id === selectedProfile.connection_id &&
          item.guild_id === selectedProfile.guild_id
      )
    : undefined;

  function resetForm() {
    const nextConnection = discordConnections[0]?.id ?? "";
    const nextServer = catalog.find((item) => item.connection_id === nextConnection);
    setEditing(null);
    setConnectionId(nextConnection);
    setGuildId(nextServer?.guild_id ?? "");
    setClaimGuildId("");
    setProfileName("");
    setServerTimezone(browserTimezone());
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
    setDrawerTab("settings");
  }

  function openNew() {
    resetForm();
    setDrawerOpen(true);
  }

  async function openEdit(profile: DiscordServerProfile) {
    setEditing(profile);
    setConnectionId(profile.connection_id);
    setGuildId(profile.guild_id);
    setProfileName(profile.name);
    setServerTimezone(browserTimezone());
    setExcludedChannels(new Set(profile.excluded_channel_ids));
    setExcludedCategories(new Set(profile.excluded_category_ids));
    setDrawerTab("settings");
    setDrawerOpen(true);
    try {
      const runtime = await serverRuntimeApi.getTimezone(profile.id);
      setServerTimezone(runtime.timezone);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  function closeDrawer() {
    setDrawerOpen(false);
    setEditing(null);
    setDrawerTab("settings");
  }

  function openConnectionEditor() {
    if (!workspaceConnection || !canEditConnection) return;
    setConnectionDisplayName(workspaceConnection.display_name);
    setConnectionMode(workspaceConnection.connection_mode);
    setConnectionExternalAccountId(workspaceConnection.external_account_id);
    setConnectionEditorOpen(true);
  }

  function closeConnectionEditor() {
    setConnectionEditorOpen(false);
  }

  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceConnection || !canEditConnection) return;
    try {
      setWorking(true);
      onError("");
      await deploymentApi.updateConnection(workspaceConnection.id, {
        display_name: connectionDisplayName.trim() || "Character Relay Discord Bot",
        connection_mode: connectionMode,
        external_account_id: connectionExternalAccountId.trim()
      });
      closeConnectionEditor();
      await onChanged();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  function changeConnection(nextConnectionId: string) {
    const first = catalog.find((item) => item.connection_id === nextConnectionId);
    setConnectionId(nextConnectionId);
    setGuildId(first?.guild_id ?? "");
    setProfileName(first?.guild_name ?? "");
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
  }

  function changeGuild(nextGuildId: string) {
    const server = availableServers.find((item) => item.guild_id === nextGuildId);
    setGuildId(nextGuildId);
    setProfileName(server?.guild_name ?? "");
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
  }

  function toggle(
    source: Set<string>,
    value: string,
    setter: (next: Set<string>) => void
  ) {
    const next = new Set(source);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (editing && !profileName.trim()) return;
    if (!editing && !claimGuildId.trim()) return;
    const guildName = selectedServer?.guild_name ?? editing?.guild_name ?? "";
    try {
      setWorking(true);
      onError("");
      const saved = editing
        ? await deploymentApi.updateDiscordServerProfile(editing.id, {
            name: profileName.trim(),
            guild_name: guildName,
            excluded_channel_ids: [...excludedChannels],
            excluded_category_ids: [...excludedCategories],
            thread_policy: "inherit_parent"
          })
        : await deploymentApi.claimDiscordServerProfile({
            guild_id: claimGuildId.trim(),
            name: profileName.trim()
          });
      await serverRuntimeApi.updateTimezone(saved.id, serverTimezone.trim());
      closeDrawer();
      onSelectProfile(saved.id);
      await onChanged();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function remove(profile: DiscordServerProfile) {
    const confirmed = window.confirm(
      zh
        ? `删除 Discord Server 配置“${profile.name}”？`
        : `Delete the Discord server profile “${profile.name}”?`
    );
    if (!confirmed) return;
    try {
      setWorking(true);
      onError("");
      await deploymentApi.deleteDiscordServerProfile(profile.id);
      if (selectedProfileId === profile.id) onSelectProfile("");
      closeDrawer();
      await onChanged();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <>
      <section className="paper-sheet server-workspace-panel">
        <div className="server-workspace-heading">
          <div>
            <p className="tape-label">SERVER WORKSPACE</p>
            <h2>
              {selectedProfile
                ? zh
                  ? `${selectedProfile.guild_name} 工作区`
                  : `${selectedProfile.guild_name} workspace`
                : zh
                  ? "选择要管理的 Discord Server"
                  : "Choose the Discord Server to manage"}
            </h2>
            <p>
              {zh
                ? "Deployment、Interaction、Session、Sticker 与时间语义都会自动限制在当前 Server。"
                : "Deployments, interactions, sessions, Stickers, and time semantics are scoped automatically to this Server."}
            </p>
          </div>
          {!demoMode && (
            <div className="server-workspace-actions">
              {selectedProfile && (
                <>
                  <button
                    className="paper-button server-log-launcher"
                    type="button"
                    onClick={onOpenLogs}
                  >
                    {zh ? "查看 Server 日志" : "View Server logs"}
                  </button>
                  <button
                    className="paper-button"
                    onClick={() => void openEdit(selectedProfile)}
                  >
                    {zh ? "编辑 Server" : "Edit Server"}
                  </button>
                </>
              )}
              <button className="ink-button" onClick={openNew}>
                {zh ? "+ 添加 Server" : "+ Add Server"}
              </button>
            </div>
          )}
        </div>

        {profiles.length ? (
          <div className="server-workspace-selector-row">
            <label>
              {zh ? "当前 Server" : "Current Server"}
              <select
                value={selectedProfile?.id ?? ""}
                onChange={(event) => onSelectProfile(event.currentTarget.value)}
              >
                <option value="" disabled>
                  {zh ? "选择 Server…" : "Choose a Server…"}
                </option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.guild_name} · {profile.name}
                  </option>
                ))}
              </select>
            </label>
            {selectedProfile ? (
              <div className="server-workspace-current-card">
                <div className="server-workspace-icon" aria-hidden="true">#</div>
                <div>
                  <strong>{selectedProfile.guild_name}</strong>
                  <span>{selectedProfile.name}</span>
                  <small>ID {selectedProfile.guild_id}</small>
                </div>
                <div className="server-workspace-stats">
                  <div className="server-workspace-stat">
                    <strong>{selectedServerCatalog?.channels.length ?? 0}</strong>
                    <span>{zh ? "可见 Channel" : "visible channels"}</span>
                  </div>
                  <div className="server-workspace-stat">
                    <strong>
                      {selectedProfile.excluded_channel_ids.length +
                        selectedProfile.excluded_category_ids.length}
                    </strong>
                    <span>{zh ? "排除位置" : "exclusions"}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="server-workspace-placeholder">
                {zh ? "选择 Server 后才会显示运行配置。" : "Select a Server to open its runtime workspace."}
              </div>
            )}

            <div className="server-workspace-connection-note">
              <div className="server-workspace-connection-icon" aria-hidden="true">D</div>
              <div className="server-workspace-connection-copy">
                <strong>Discord</strong>
                <span>{workspaceConnection?.display_name ?? "Character Relay Discord Bot"}</span>
                <small>
                  {workspaceConnection
                    ? `${workspaceConnection.connection_mode} · ${workspaceConnection.last_seen_at ? (zh ? "已连接运行" : "connector seen") : (zh ? "等待 Connector" : "waiting for connector")}`
                    : zh
                      ? "固定托管连接"
                      : "Fixed managed connection"}
                </small>
              </div>
              {workspaceConnection && (
                <span className={`server-workspace-connection-status status-${workspaceConnection.status}`}>
                  {workspaceConnection.status.replaceAll("_", " ")}
                </span>
              )}
              <div className="server-workspace-connection-policy">
                <small>
                  {connectionShared
                    ? zh
                      ? "固定 Discord 连接 · 由 Super Admin 管理"
                      : "Fixed Discord connection · managed by Super Admin"
                    : zh
                      ? "固定 Discord 连接 · 不需要为每个 Server 新增"
                      : "Fixed Discord connection · shared across Server workspaces"}
                </small>
                {canEditConnection && (
                  <button type="button" onClick={openConnectionEditor}>
                    {zh ? "编辑连接" : "Edit connection"}
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="server-workspace-placeholder large">
              <strong>{zh ? "还没有 Server 配置" : "No Server profiles yet"}</strong>
              <p>
                {!catalog.length
                  ? zh
                    ? "等待 Discord Connector 上线并同步可见 Server。"
                    : "Bring the Discord Connector online so visible Servers can be synchronized."
                  : zh
                    ? "添加一个已同步 Server，之后所有功能都会以它为范围。"
                    : "Add a synchronized Server; it becomes the scope for every runtime feature."}
              </p>
            </div>
            {workspaceConnection && (
              <div className="server-workspace-connection-note">
                <div className="server-workspace-connection-icon" aria-hidden="true">D</div>
                <div className="server-workspace-connection-copy">
                  <strong>Discord</strong>
                  <span>{workspaceConnection.display_name}</span>
                  <small>{workspaceConnection.connection_mode}</small>
                </div>
                <span className={`server-workspace-connection-status status-${workspaceConnection.status}`}>
                  {workspaceConnection.status.replaceAll("_", " ")}
                </span>
                <div className="server-workspace-connection-policy">
                  <small>
                    {connectionShared
                      ? zh
                        ? "固定 Discord 连接 · 由 Super Admin 管理"
                        : "Fixed Discord connection · managed by Super Admin"
                      : zh
                        ? "固定 Discord 连接"
                        : "Fixed Discord connection"}
                  </small>
                  {canEditConnection && (
                    <button type="button" onClick={openConnectionEditor}>
                      {zh ? "编辑连接" : "Edit connection"}
                    </button>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {drawerOpen && !demoMode && (
        <PaperDrawer
          onClose={closeDrawer}
          ariaLabel={editing
            ? zh
              ? `编辑 ${editing.guild_name}`
              : `Edit ${editing.guild_name}`
            : zh
              ? "添加 Discord Server"
              : "Add Discord Server"}
          className="server-profile-drawer"
        >
          <div className="server-drawer">
            <header className="server-drawer-header">
              <div>
                <p className="tape-label">{editing ? "EDIT SERVER" : "NEW SERVER"}</p>
                <h2>
                  {editing
                    ? zh
                      ? `管理 ${editing.guild_name}`
                      : `Manage ${editing.guild_name}`
                    : zh
                      ? "建立 Server Workspace"
                      : "Create Server Workspace"}
                </h2>
                <p>
                  {editing
                    ? zh
                      ? "Server 身份由 Connector 同步；这里调整名称、默认时区、Channel 范围与 Sticker 语义。"
                      : "The Connector owns Server identity; edit its label, default timezone, Channel scope, and Sticker meanings here."
                    : zh
                      ? "先把 Character Relay Bot 加入 Discord Server，再输入该 Server ID 认领到当前账号。"
                      : "Add the Character Relay Bot to Discord first, then enter the Server ID to claim it for this account."}
                </p>
              </div>
              <button className="drawer-close-button" type="button" onClick={closeDrawer}>
                {zh ? "关闭" : "Close"}
              </button>
            </header>

            {editing && (
              <nav className="server-drawer-tabs" aria-label="Server settings">
                <button
                  type="button"
                  className={drawerTab === "settings" ? "active" : ""}
                  onClick={() => setDrawerTab("settings")}
                >
                  {zh ? "Server 设置" : "Server settings"}
                </button>
                <button
                  type="button"
                  className={drawerTab === "stickers" ? "active" : ""}
                  onClick={() => setDrawerTab("stickers")}
                >
                  Expression Dictionary
                </button>
              </nav>
            )}

            {drawerTab === "settings" && (
              <form className="server-drawer-form" onSubmit={save}>
                {editing ? (
                  <div className="server-readonly-identity drawer-form-wide">
                    <div className="server-workspace-icon" aria-hidden="true">#</div>
                    <div>
                      <strong>{editing.guild_name}</strong>
                      <span>ID {editing.guild_id}</span>
                    </div>
                    <small>{connections.find((item) => item.id === editing.connection_id)?.display_name}</small>
                  </div>
                ) : (
                  <label className="drawer-form-wide">
                    Discord Server ID
                    <input
                      value={claimGuildId}
                      onChange={(event) =>
                        setClaimGuildId(event.currentTarget.value.replace(/\D+/gu, ""))
                      }
                      required
                      inputMode="numeric"
                      pattern="[0-9]+"
                      maxLength={200}
                      placeholder="123456789012345678"
                    />
                    <small>
                      {zh
                        ? "只会精确查找这个 ID。其他账号无法看到 Super Admin 的完整 Server 清单。"
                        : "Only this exact ID is checked. Other accounts cannot browse the Super Admin Server catalog."}
                    </small>
                  </label>
                )}

                <label className={editing ? "drawer-form-wide" : ""}>
                  {zh ? "Workspace 名称" : "Workspace name"}
                  <input
                    value={profileName}
                    onChange={(event) => setProfileName(event.currentTarget.value)}
                    required
                    maxLength={120}
                    placeholder={zh ? "例如：私人 Companion Server" : "e.g. Private companion server"}
                  />
                </label>

                <label className="drawer-form-wide">
                  {zh ? "默认时区" : "Default timezone"}
                  <input
                    value={serverTimezone}
                    onChange={(event) => setServerTimezone(event.currentTarget.value)}
                    required
                    maxLength={120}
                    list="server-timezone-options"
                    placeholder="Asia/Kuala_Lumpur"
                  />
                  <datalist id="server-timezone-options">
                    <option value="Asia/Kuala_Lumpur" />
                    <option value="Asia/Singapore" />
                    <option value="Asia/Tokyo" />
                    <option value="Asia/Shanghai" />
                    <option value="Europe/London" />
                    <option value="America/New_York" />
                    <option value="America/Los_Angeles" />
                    <option value="UTC" />
                  </datalist>
                  <small>
                    {zh
                      ? "使用 IANA 时区。未特别说明地点时，角色回答时间、Current Time Tool 与 Reminder 都以这个时区为准。"
                      : "Use an IANA timezone. Unqualified time answers, Current Time, and Reminder scheduling all use this timezone."}
                  </small>
                </label>

                <section className="server-channel-picker drawer-form-wide">
                  <div>
                    <strong>{zh ? "全局排除 Channel" : "Global Channel exclusions"}</strong>
                    <small>
                      {zh
                        ? "未勾选的位置默认允许当前 Server 中的全部角色。"
                        : "Unchecked destinations remain available to every character in this Server."}
                    </small>
                  </div>
                  {groups.map((group) => (
                    <fieldset key={group.id || "uncategorized"}>
                      <legend>
                        {group.id && (
                          <input
                            type="checkbox"
                            checked={excludedCategories.has(group.id)}
                            onChange={() =>
                              toggle(excludedCategories, group.id, setExcludedCategories)
                            }
                          />
                        )}
                        {group.name}
                      </legend>
                      {group.channels.map((channel) => (
                        <label key={channel.id} className="server-channel-option">
                          <input
                            type="checkbox"
                            checked={excludedChannels.has(channel.id)}
                            onChange={() =>
                              toggle(excludedChannels, channel.id, setExcludedChannels)
                            }
                          />
                          <span>#{channel.name}</span>
                          <small>{channel.type}</small>
                        </label>
                      ))}
                    </fieldset>
                  ))}
                  {selectedServer && groups.length === 0 && (
                    <small>
                      {zh
                        ? "Connector 当前没有同步到可用文字 Channel。"
                        : "The Connector has not reported any readable text Channels."}
                    </small>
                  )}
                </section>

                <div className="server-drawer-footer drawer-form-wide">
                  {editing && (
                    <button
                      type="button"
                      className="text-button danger-text"
                      onClick={() => void remove(editing)}
                      disabled={working}
                    >
                      {zh ? "删除 Server 配置" : "Delete Server profile"}
                    </button>
                  )}
                  <button className="ink-button" disabled={working || (!editing && !selectedServer)}>
                    {working
                      ? zh
                        ? "保存中…"
                        : "Saving…"
                      : editing
                        ? zh
                          ? "保存 Server 设置"
                          : "Save Server settings"
                        : zh
                          ? "建立 Server Workspace"
                          : "Create Server Workspace"}
                  </button>
                </div>
              </form>
            )}

            {drawerTab === "stickers" && editing && (
              <ServerStickerDictionary
                profile={editing}
                demoMode={demoMode}
                zh={zh}
                onError={onError}
              />
            )}
          </div>
        </PaperDrawer>
      )}

      {connectionEditorOpen && workspaceConnection && canEditConnection && (
        <PaperDrawer
          onClose={closeConnectionEditor}
          ariaLabel={zh ? "编辑固定 Discord 连接" : "Edit fixed Discord connection"}
          className="discord-connection-drawer"
        >
          <div className="server-drawer discord-connection-editor">
            <header className="server-drawer-header">
              <div>
                <p className="tape-label">DISCORD CONNECTION</p>
                <h2>{zh ? "固定托管连接" : "Fixed managed connection"}</h2>
                <p>
                  {zh
                    ? "Character Relay 只使用这一条 Discord Bot 连接；这里只允许 Super Admin 调整连接元数据。"
                    : "Character Relay uses one Discord Bot connection. Only the Super Admin can edit its connection metadata."}
                </p>
              </div>
              <button className="drawer-close-button" type="button" onClick={closeConnectionEditor}>
                {zh ? "关闭" : "Close"}
              </button>
            </header>
            <form className="server-drawer-form" onSubmit={saveConnection}>
              <div className="discord-connection-readonly drawer-form-wide">
                <div className="server-workspace-connection-icon" aria-hidden="true">D</div>
                <div>
                  <strong>Discord</strong>
                  <span>{workspaceConnection.id}</span>
                </div>
                <small>{workspaceConnection.status}</small>
              </div>
              <label className="drawer-form-wide">
                {zh ? "连接显示名称" : "Connection display name"}
                <input
                  value={connectionDisplayName}
                  onChange={(event) => setConnectionDisplayName(event.currentTarget.value)}
                  maxLength={120}
                  required
                />
              </label>
              <label className="drawer-form-wide">
                {zh ? "运行方式" : "Run mode"}
                <select
                  value={connectionMode}
                  onChange={(event) => setConnectionMode(event.currentTarget.value as ConnectionMode)}
                >
                  <option value="managed">{zh ? "托管" : "Managed"}</option>
                  <option value="local">{zh ? "本地" : "Local"}</option>
                </select>
              </label>
              <label className="drawer-form-wide">
                {zh ? "Discord Bot / 外部账号 ID" : "Discord Bot / external account ID"}
                <input
                  value={connectionExternalAccountId}
                  onChange={(event) => setConnectionExternalAccountId(event.currentTarget.value)}
                  maxLength={200}
                />
              </label>
              <div className="server-drawer-footer drawer-form-wide">
                <small>
                  {zh
                    ? "不提供新增或删除 Connection；Server 只会复用这条固定 Discord 连接。"
                    : "Connections cannot be added or deleted here; Server workspaces reuse this fixed Discord connection."}
                </small>
                <button className="ink-button" disabled={working}>
                  {working ? (zh ? "保存中…" : "Saving…") : zh ? "保存连接" : "Save connection"}
                </button>
              </div>
            </form>
          </div>
        </PaperDrawer>
      )}
    </>
  );
}
