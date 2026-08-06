import { useMemo, useState, type FormEvent } from "react";

import {
  deploymentApi,
  type DiscordCatalogChannel,
  type DiscordServerCatalog,
  type DiscordServerProfile,
  type PlatformConnection
} from "./deploymentApi";
import { PaperDrawer } from "./NotebookUI";
import { ServerStickerDictionary } from "./ServerStickerDictionary";

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
  const [guildId, setGuildId] = useState("");
  const [profileName, setProfileName] = useState("");
  const [excludedChannels, setExcludedChannels] = useState<Set<string>>(new Set());
  const [excludedCategories, setExcludedCategories] = useState<Set<string>>(new Set());

  const availableServers = useMemo(
    () => catalog.filter((server) => server.connection_id === connectionId),
    [catalog, connectionId]
  );
  const selectedServer = availableServers.find((server) => server.guild_id === guildId);
  const groups = useMemo(() => groupsFor(selectedServer), [selectedServer]);
  const selectedConnection = connections.find(
    (item) => item.id === selectedProfile?.connection_id
  );
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
    setProfileName(nextServer?.guild_name ?? "");
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
    setDrawerTab("settings");
  }

  function openNew() {
    resetForm();
    setDrawerOpen(true);
  }

  function openEdit(profile: DiscordServerProfile) {
    setEditing(profile);
    setConnectionId(profile.connection_id);
    setGuildId(profile.guild_id);
    setProfileName(profile.name);
    setExcludedChannels(new Set(profile.excluded_channel_ids));
    setExcludedCategories(new Set(profile.excluded_category_ids));
    setDrawerTab("settings");
    setDrawerOpen(true);
  }

  function closeDrawer() {
    setDrawerOpen(false);
    setEditing(null);
    setDrawerTab("settings");
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
    if (!profileName.trim() || (!editing && !selectedServer)) return;
    const guildName = selectedServer?.guild_name ?? editing?.guild_name ?? "";
    const serverGuildId = selectedServer?.guild_id ?? editing?.guild_id ?? "";
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
        : await deploymentApi.createDiscordServerProfile({
            connection_id: connectionId,
            name: profileName.trim(),
            guild_id: serverGuildId,
            guild_name: guildName,
            excluded_channel_ids: [...excludedChannels],
            excluded_category_ids: [...excludedCategories],
            thread_policy: "inherit_parent"
          });
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
                ? "Deployment、Interaction、Session 与 Sticker 都会自动限制在当前 Server。"
                : "Deployments, interactions, sessions, and Stickers are scoped automatically to this Server."}
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
                  <button className="paper-button" onClick={() => openEdit(selectedProfile)}>
                    {zh ? "编辑 Server" : "Edit Server"}
                  </button>
                </>
              )}
              <button
                className="ink-button"
                onClick={openNew}
                disabled={!discordConnections.length || !catalog.length}
              >
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
                  <small>
                    {selectedConnection?.display_name ?? "Discord"} · ID {selectedProfile.guild_id}
                  </small>
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
          </div>
        ) : (
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
                      ? "Server 身份由 Connector 同步；这里只调整名称、Channel 范围与 Sticker 语义。"
                      : "The Connector owns Server identity; edit only its label, Channel scope, and Sticker meanings."
                    : zh
                      ? "选择 Connector 已同步的 Server，不需要手动填写 Server ID。"
                      : "Choose a Server already synchronized by the Connector; no manual Server ID is required."}
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
                  <>
                    <label>
                      {zh ? "Discord Connector" : "Discord Connector"}
                      <select
                        value={connectionId}
                        onChange={(event) => changeConnection(event.currentTarget.value)}
                        required
                      >
                        {discordConnections.map((connection) => (
                          <option key={connection.id} value={connection.id}>
                            {connection.display_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {zh ? "已同步 Server" : "Synchronized Server"}
                      <select
                        value={guildId}
                        onChange={(event) => changeGuild(event.currentTarget.value)}
                        required
                      >
                        {availableServers.map((server) => (
                          <option key={server.guild_id} value={server.guild_id}>
                            {server.guild_name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </>
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
    </>
  );
}
