import { useMemo, useState, type FormEvent } from "react";

import {
  deploymentApi,
  type DiscordCatalogChannel,
  type DiscordServerCatalog,
  type DiscordServerProfile,
  type PlatformConnection
} from "./deploymentApi";

interface Props {
  connections: PlatformConnection[];
  profiles: DiscordServerProfile[];
  catalog: DiscordServerCatalog[];
  demoMode: boolean;
  zh: boolean;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}

interface ChannelGroup {
  id: string;
  name: string;
  channels: DiscordCatalogChannel[];
}

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
  demoMode,
  zh,
  onChanged,
  onError
}: Props) {
  const discordConnections = connections.filter((item) => item.platform === "discord");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<DiscordServerProfile | null>(null);
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

  function resetForm() {
    const nextConnection = discordConnections[0]?.id ?? "";
    const nextServer = catalog.find((item) => item.connection_id === nextConnection);
    setEditing(null);
    setConnectionId(nextConnection);
    setGuildId(nextServer?.guild_id ?? "");
    setProfileName(nextServer?.guild_name ?? "");
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
  }

  function openNew() {
    resetForm();
    setOpen(true);
  }

  function openEdit(profile: DiscordServerProfile) {
    setEditing(profile);
    setConnectionId(profile.connection_id);
    setGuildId(profile.guild_id);
    setProfileName(profile.name);
    setExcludedChannels(new Set(profile.excluded_channel_ids));
    setExcludedCategories(new Set(profile.excluded_category_ids));
    setOpen(true);
  }

  function close() {
    setOpen(false);
    setEditing(null);
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
    if (!selectedServer || !profileName.trim()) return;
    try {
      setWorking(true);
      onError("");
      if (editing) {
        await deploymentApi.updateDiscordServerProfile(editing.id, {
          name: profileName.trim(),
          guild_name: selectedServer.guild_name,
          excluded_channel_ids: [...excludedChannels],
          excluded_category_ids: [...excludedCategories],
          thread_policy: "inherit_parent"
        });
      } else {
        await deploymentApi.createDiscordServerProfile({
          connection_id: connectionId,
          name: profileName.trim(),
          guild_id: selectedServer.guild_id,
          guild_name: selectedServer.guild_name,
          excluded_channel_ids: [...excludedChannels],
          excluded_category_ids: [...excludedCategories],
          thread_policy: "inherit_parent"
        });
      }
      close();
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
      await onChanged();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="paper-sheet connection-panel server-profile-panel">
      <div className="panel-heading-row">
        <div>
          <p className="tape-label">DISCORD SERVERS</p>
          <h2>{zh ? "Server 配置" : "Server profiles"}</h2>
        </div>
        {!demoMode && !open && (
          <button
            className="paper-button"
            onClick={openNew}
            disabled={!discordConnections.length || !catalog.length}
          >
            {zh ? "+ 添加" : "+ Add"}
          </button>
        )}
      </div>

      <p className="connection-note">
        {zh
          ? "Connector 会同步 Bot 可见的 Server 与 Channel。配置默认覆盖全部 Channel，只需排除不应让角色进入的位置。"
          : "The connector syncs visible servers and channels. Profiles cover every channel by default; exclude only the places characters should not enter."}
      </p>

      {open && !demoMode && (
        <form className="connection-form server-profile-form" onSubmit={save}>
          <div className="panel-heading-row">
            <strong>
              {editing
                ? zh
                  ? "编辑 Server 配置"
                  : "Edit server profile"
                : zh
                  ? "添加 Server 配置"
                  : "Add server profile"}
            </strong>
            <button type="button" className="text-button" onClick={close}>
              {zh ? "取消" : "Cancel"}
            </button>
          </div>
          <label>
            {zh ? "Discord 平台账户" : "Discord platform account"}
            <select
              value={connectionId}
              onChange={(event) => changeConnection(event.currentTarget.value)}
              disabled={Boolean(editing)}
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
            {zh ? "Discord Server" : "Discord server"}
            <select
              value={guildId}
              onChange={(event) => changeGuild(event.currentTarget.value)}
              disabled={Boolean(editing)}
              required
            >
              {availableServers.map((server) => (
                <option key={server.guild_id} value={server.guild_id}>
                  {server.guild_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {zh ? "配置名称" : "Profile name"}
            <input
              value={profileName}
              onChange={(event) => setProfileName(event.currentTarget.value)}
              required
              maxLength={120}
              placeholder={zh ? "例如：私人 Companion Server" : "e.g. Private companion server"}
            />
          </label>

          <div className="server-channel-picker">
            <div>
              <strong>{zh ? "全局排除 Channel" : "Global channel exclusions"}</strong>
              <small>
                {zh
                  ? "未勾选的位置默认允许所有使用此配置的角色。"
                  : "Unchecked destinations remain available to every character using this profile."}
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
                  : "The connector has not reported any readable text channels."}
              </small>
            )}
          </div>

          <button className="ink-button" disabled={working || !selectedServer}>
            {working
              ? zh
                ? "保存中…"
                : "Saving…"
              : editing
                ? zh
                  ? "保存配置"
                  : "Save profile"
                : zh
                  ? "建立配置"
                  : "Create profile"}
          </button>
        </form>
      )}

      <div className="server-profile-list">
        {profiles.map((profile) => (
          <article className="server-profile-card" key={profile.id}>
            <div>
              <strong>{profile.name}</strong>
              <span>{profile.guild_name}</span>
              <small>
                {zh ? "全部 Channel，排除" : "All channels, excluding"}{" "}
                {profile.excluded_channel_ids.length + profile.excluded_category_ids.length}
              </small>
            </div>
            {!demoMode && (
              <div className="server-profile-actions">
                <button
                  className="text-button"
                  onClick={() => openEdit(profile)}
                  disabled={working}
                >
                  {zh ? "编辑" : "Edit"}
                </button>
                <button
                  className="text-button danger-text"
                  onClick={() => void remove(profile)}
                  disabled={working}
                >
                  {zh ? "删除" : "Delete"}
                </button>
              </div>
            )}
          </article>
        ))}
        {!profiles.length && (
          <div className="deployment-empty compact-empty">
            <strong>{zh ? "还没有 Server 配置" : "No server profiles yet"}</strong>
            <p>
              {!catalog.length
                ? zh
                  ? "Discord Connector 上线并完成同步后，可直接选择 Server。"
                  : "Bring the Discord connector online so its servers can be selected."
                : zh
                  ? "建立一次配置，之后部署角色时直接选择。"
                  : "Create it once, then select it when deploying characters."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
