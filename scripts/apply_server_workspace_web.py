from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected snippet not found in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


# ---------------------------------------------------------------------------
# Portal API clients
# ---------------------------------------------------------------------------
interaction_api = '''export type InteractionStatus = "active" | "paused" | "stopped" | "completed";
export type InteractionIntensity = "light" | "playful" | "sharp";

export interface InteractionTemplate {
  id: string;
  server_profile_id: string;
  name: string;
  template_type: "roast";
  participant_character_card_ids: string[];
  participant_names: string[];
  rounds_per_trigger: number;
  maximum_triggers: number;
  maximum_replies_per_trigger: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  created_at: string;
  updated_at: string;
}

export interface InteractionTemplateCreate {
  server_profile_id: string;
  name: string;
  participant_character_card_ids: string[];
  rounds_per_trigger: number;
  maximum_triggers: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
}

export type InteractionTemplateUpdate = Partial<Omit<InteractionTemplateCreate, "server_profile_id">>;

export interface InteractionTemplateApply {
  channel_id: string;
  target_user_id: string;
  target_display_name: string;
  status: "active" | "paused";
}

export interface InteractionSession {
  id: string;
  connection_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  category_id: string;
  target_user_id: string;
  target_display_name: string;
  participant_deployment_ids: string[];
  participant_names: string[];
  session_type: "roast";
  rounds_per_trigger: number;
  maximum_triggers: number;
  completed_triggers: number;
  maximum_replies_per_trigger: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  status: InteractionStatus;
  started_at: string | null;
  expires_at: string | null;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InteractionSessionCreate {
  connection_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  category_id: string;
  target_user_id: string;
  target_display_name: string;
  participant_deployment_ids: string[];
  rounds_per_trigger: number;
  maximum_triggers: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  status: "active" | "paused";
}

export interface StickerSemantic {
  id: string;
  connection_id: string;
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export interface StickerSemanticCreate {
  connection_id: string;
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve raw response.
  }
  return raw || `Request failed with ${response.status}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const interactionApi = {
  listTemplates: (serverProfileId: string) =>
    request<InteractionTemplate[]>(
      `/api/interaction-templates?server_profile_id=${encodeURIComponent(serverProfileId)}`
    ),
  createTemplate: (payload: InteractionTemplateCreate) =>
    request<InteractionTemplate>("/api/interaction-templates", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateTemplate: (templateId: string, payload: InteractionTemplateUpdate) =>
    request<InteractionTemplate>(`/api/interaction-templates/${templateId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  applyTemplate: (templateId: string, payload: InteractionTemplateApply) =>
    request<InteractionSession>(`/api/interaction-templates/${templateId}/apply`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  deleteTemplate: (templateId: string) =>
    request<void>(`/api/interaction-templates/${templateId}`, { method: "DELETE" }),
  listSessions: (options: { connectionId?: string; guildId?: string } = {}) => {
    const query = new URLSearchParams();
    if (options.connectionId) query.set("connection_id", options.connectionId);
    if (options.guildId) query.set("guild_id", options.guildId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<InteractionSession[]>(`/api/interaction-sessions${suffix}`);
  },
  createSession: (payload: InteractionSessionCreate) =>
    request<InteractionSession>("/api/interaction-sessions", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateSessionStatus: (sessionId: string, status: InteractionStatus) =>
    request<InteractionSession>(`/api/interaction-sessions/${sessionId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status })
    }),
  deleteSession: (sessionId: string) =>
    request<void>(`/api/interaction-sessions/${sessionId}`, { method: "DELETE" }),
  listStickers: (connectionId?: string, guildId?: string) => {
    const query = new URLSearchParams();
    if (connectionId) query.set("connection_id", connectionId);
    if (guildId) query.set("guild_id", guildId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<StickerSemantic[]>(`/api/discord/sticker-dictionary${suffix}`);
  },
  saveSticker: (payload: StickerSemanticCreate) =>
    request<StickerSemantic>("/api/discord/sticker-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteSticker: (recordId: string) =>
    request<void>(`/api/discord/sticker-dictionary/${recordId}`, {
      method: "DELETE"
    })
};
'''
Path("web/src/interactionApi.ts").write_text(interaction_api, encoding="utf-8")

replace(
    "web/src/deploymentApi.ts",
    '''  listDeployments: (characterCardId?: string) =>
    request<CharacterDeployment[]>(
      characterCardId
        ? `/api/deployments?character_card_id=${encodeURIComponent(characterCardId)}`
        : "/api/deployments"
    ),
''',
    '''  listDeployments: (characterCardId?: string) =>
    request<CharacterDeployment[]>(
      characterCardId
        ? `/api/deployments?character_card_id=${encodeURIComponent(characterCardId)}`
        : "/api/deployments"
    ),
  listDeploymentsForServer: (serverProfileId: string) =>
    request<CharacterDeployment[]>(
      `/api/deployments?server_profile_id=${encodeURIComponent(serverProfileId)}`
    ),
''',
)
replace(
    "web/src/deploymentApi.ts",
    '''    status?: DeploymentStatus | "all";
  } = {}) => {
''',
    '''    status?: DeploymentStatus | "all";
    serverProfileId?: string;
  } = {}) => {
''',
)
replace(
    "web/src/deploymentApi.ts",
    '''    if (options.status && options.status !== "all") {
      query.set("status", options.status);
    }
''',
    '''    if (options.status && options.status !== "all") {
      query.set("status", options.status);
    }
    if (options.serverProfileId) {
      query.set("server_profile_id", options.serverProfileId);
    }
''',
)

# ---------------------------------------------------------------------------
# Server Sticker Dictionary is available only inside Edit Server.
# ---------------------------------------------------------------------------
server_stickers = '''import { useEffect, useState, type FormEvent } from "react";

import type { DiscordServerProfile } from "./deploymentApi";
import { interactionApi, type StickerSemantic } from "./interactionApi";

interface Props {
  profile: DiscordServerProfile;
  demoMode: boolean;
  zh: boolean;
  onError: (message: string) => void;
}

export function ServerStickerDictionary({ profile, demoMode, zh, onError }: Props) {
  const [stickers, setStickers] = useState<StickerSemantic[]>([]);
  const [editing, setEditing] = useState<StickerSemantic | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);

  async function load() {
    try {
      setLoading(true);
      setStickers(await interactionApi.listStickers(profile.connection_id, profile.guild_id));
      onError("");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setEditing(null);
    void load();
  }, [profile.connection_id, profile.guild_id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    try {
      setWorking(true);
      await interactionApi.saveSticker({
        connection_id: editing.connection_id,
        guild_id: editing.guild_id,
        sticker_id: editing.sticker_id,
        name: editing.name,
        description: editing.description,
        tags: editing.tags,
        format_type: editing.format_type,
        asset_url: editing.asset_url,
        semantic_intent:
          String(data.get("semantic_intent") ?? "sticker_reaction").trim() ||
          "sticker_reaction",
        semantic_emotion: String(data.get("semantic_emotion") ?? "").trim(),
        semantic_description: String(data.get("semantic_description") ?? "").trim()
      });
      setEditing(null);
      await load();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="server-sticker-section">
      <div className="server-drawer-section-heading">
        <div>
          <p className="tape-label">SERVER STICKERS</p>
          <h3>{zh ? "Sticker Dictionary" : "Sticker dictionary"}</h3>
          <p>
            {zh
              ? "Connector 会自动同步当前 Server 的自定义 Sticker。这里只编辑角色应理解的含义，不需要填写 Server ID 或 Sticker ID。"
              : "The connector synchronizes this Server's custom Stickers. Edit only the meaning supplied to characters; Server and Sticker IDs are automatic."}
          </p>
        </div>
        <span className="server-sticker-count">{stickers.length}</span>
      </div>

      {loading ? (
        <div className="server-sticker-empty">{zh ? "正在同步 Sticker…" : "Loading Stickers…"}</div>
      ) : stickers.length ? (
        <div className="server-sticker-grid">
          {stickers.map((item) => (
            <article className="server-sticker-card" key={item.id}>
              <div className="server-sticker-preview">
                {item.asset_url ? (
                  <img src={item.asset_url} alt="" loading="lazy" />
                ) : (
                  <span aria-hidden="true">✦</span>
                )}
              </div>
              <div className="server-sticker-copy">
                <div className="server-sticker-title-row">
                  <strong>{item.name}</strong>
                  <span className={`sticker-source source-${item.semantic_source}`}>
                    {item.semantic_source}
                  </span>
                </div>
                <small>{item.description || item.tags.join(", ") || `ID ${item.sticker_id}`}</small>
                <p>
                  {item.semantic_description ||
                    (zh ? "尚未配置角色语义。" : "No character meaning configured yet.")}
                </p>
                <div className="server-sticker-meta">
                  <span>{item.semantic_intent || "sticker_reaction"}</span>
                  <span>{item.semantic_emotion || "—"}</span>
                  <span>{Math.round(item.semantic_confidence * 100)}%</span>
                </div>
              </div>
              {!demoMode && (
                <button className="paper-button" type="button" onClick={() => setEditing(item)}>
                  {zh ? "编辑含义" : "Edit meaning"}
                </button>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="server-sticker-empty">
          <strong>{zh ? "这个 Server 暂时没有可用 Sticker" : "No available Stickers in this Server"}</strong>
          <p>
            {zh
              ? "Connector 下次同步 Server 时会自动获取，不需要先在聊天中发送。"
              : "The connector will fetch them during the next Server sync; they do not need to be sent first."}
          </p>
        </div>
      )}

      {editing && !demoMode && (
        <form className="sticker-meaning-editor" onSubmit={save} key={editing.id}>
          <div className="sticker-editor-identity">
            <div className="server-sticker-preview compact">
              {editing.asset_url ? <img src={editing.asset_url} alt="" /> : <span>✦</span>}
            </div>
            <div>
              <strong>{editing.name}</strong>
              <small>{profile.guild_name} · {editing.sticker_id}</small>
            </div>
            <button className="text-button" type="button" onClick={() => setEditing(null)}>
              {zh ? "取消" : "Cancel"}
            </button>
          </div>
          <div className="sticker-editor-fields">
            <label>
              Intent
              <input
                name="semantic_intent"
                defaultValue={editing.semantic_intent || "sticker_reaction"}
              />
            </label>
            <label>
              Emotion
              <input
                name="semantic_emotion"
                defaultValue={editing.semantic_emotion}
                placeholder="amused / shy / annoyed"
              />
            </label>
            <label className="drawer-form-wide">
              {zh ? "角色应理解的含义" : "Meaning supplied to characters"}
              <textarea
                name="semantic_description"
                rows={4}
                required
                defaultValue={editing.semantic_description}
              />
            </label>
          </div>
          <button className="ink-button" disabled={working}>
            {working ? (zh ? "保存中…" : "Saving…") : zh ? "保存角色语义" : "Save character meaning"}
          </button>
        </form>
      )}
    </section>
  );
}
'''
Path("web/src/ServerStickerDictionary.tsx").write_text(server_stickers, encoding="utf-8")

# ---------------------------------------------------------------------------
# Server Workspace selector and create/edit Drawer.
# ---------------------------------------------------------------------------
server_profiles = '''import { useMemo, useState, type FormEvent } from "react";

import {
  deploymentApi,
  type DiscordCatalogChannel,
  type DiscordServerCatalog,
  type DiscordServerProfile,
  type PlatformConnection
} from "./deploymentApi";
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
  onError
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
    if (!selectedServer || !profileName.trim()) return;
    try {
      setWorking(true);
      onError("");
      const saved = editing
        ? await deploymentApi.updateDiscordServerProfile(editing.id, {
            name: profileName.trim(),
            guild_name: selectedServer.guild_name,
            excluded_channel_ids: [...excludedChannels],
            excluded_category_ids: [...excludedCategories],
            thread_policy: "inherit_parent"
          })
        : await deploymentApi.createDiscordServerProfile({
            connection_id: connectionId,
            name: profileName.trim(),
            guild_id: selectedServer.guild_id,
            guild_name: selectedServer.guild_name,
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
            <h2>{zh ? "先选择要管理的 Discord Server" : "Choose the Discord Server to manage"}</h2>
            <p>
              {zh
                ? "Deployment、Interaction、Session 与 Sticker 都会自动限制在当前 Server。"
                : "Deployments, interactions, sessions, and Stickers are scoped automatically to this Server."}
            </p>
          </div>
          {!demoMode && (
            <div className="server-workspace-actions">
              {selectedProfile && (
                <button className="paper-button" onClick={() => openEdit(selectedProfile)}>
                  {zh ? "编辑 Server" : "Edit Server"}
                </button>
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
                <div className="server-workspace-stat">
                  <strong>
                    {selectedProfile.excluded_channel_ids.length +
                      selectedProfile.excluded_category_ids.length}
                  </strong>
                  <span>{zh ? "排除位置" : "exclusions"}</span>
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
        <div className="server-drawer-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeDrawer();
        }}>
          <aside className="server-drawer" role="dialog" aria-modal="true">
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
                  Sticker Dictionary
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
                  <button className="ink-button" disabled={working || !selectedServer}>
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
          </aside>
        </div>
      )}
    </>
  );
}
'''
Path("web/src/DiscordServerProfilesPanel.tsx").write_text(server_profiles, encoding="utf-8")

# ---------------------------------------------------------------------------
# Server-scoped Interaction Templates and applied Sessions.
# ---------------------------------------------------------------------------
interaction_panel = '''import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  deploymentApi,
  type CharacterDeployment,
  type DiscordServerCatalog,
  type DiscordServerProfile
} from "./deploymentApi";
import {
  interactionApi,
  type InteractionIntensity,
  type InteractionSession,
  type InteractionStatus,
  type InteractionTemplate
} from "./interactionApi";

interface Props {
  demoMode: boolean;
  zh: boolean;
  serverProfile: DiscordServerProfile;
  serverCatalog?: DiscordServerCatalog;
}

function discordUserId(value: string): string {
  return value.trim().replaceAll(/[<@!>]/gu, "");
}

function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}

export function InteractionSessionsPanel({
  demoMode,
  zh,
  serverProfile,
  serverCatalog
}: Props) {
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [templates, setTemplates] = useState<InteractionTemplate[]>([]);
  const [sessions, setSessions] = useState<InteractionSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [templateDrawerOpen, setTemplateDrawerOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<InteractionTemplate | null>(null);
  const [applyingTemplate, setApplyingTemplate] = useState<InteractionTemplate | null>(null);
  const [firstCharacterId, setFirstCharacterId] = useState("");
  const [secondCharacterId, setSecondCharacterId] = useState("");
  const [intensity, setIntensity] = useState<InteractionIntensity>("playful");

  const availableChannels = useMemo(
    () =>
      (serverCatalog?.channels ?? []).filter(
        (channel) =>
          !serverProfile.excluded_channel_ids.includes(channel.id) &&
          (!channel.category_id ||
            !serverProfile.excluded_category_ids.includes(channel.category_id))
      ),
    [serverCatalog, serverProfile]
  );

  const activeDeployments = useMemo(
    () => deployments.filter((item) => item.status === "active"),
    [deployments]
  );

  async function load() {
    try {
      setLoading(true);
      const [nextDeployments, nextTemplates, nextSessions] = await Promise.all([
        deploymentApi.listDeploymentsForServer(serverProfile.id),
        interactionApi.listTemplates(serverProfile.id),
        interactionApi.listSessions({
          connectionId: serverProfile.connection_id,
          guildId: serverProfile.guild_id
        })
      ]);
      setDeployments(nextDeployments);
      setTemplates(nextTemplates);
      setSessions(nextSessions);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setTemplateDrawerOpen(false);
    setEditingTemplate(null);
    setApplyingTemplate(null);
    void load();
  }, [serverProfile.id]);

  function openNewTemplate() {
    setEditingTemplate(null);
    setFirstCharacterId(activeDeployments[0]?.character_card_id ?? "");
    setSecondCharacterId(
      activeDeployments.find(
        (item) => item.character_card_id !== activeDeployments[0]?.character_card_id
      )?.character_card_id ?? ""
    );
    setIntensity("playful");
    setTemplateDrawerOpen(true);
  }

  function openEditTemplate(item: InteractionTemplate) {
    setEditingTemplate(item);
    setFirstCharacterId(item.participant_character_card_ids[0] ?? "");
    setSecondCharacterId(item.participant_character_card_ids[1] ?? "");
    setIntensity(item.intensity);
    setTemplateDrawerOpen(true);
  }

  async function saveTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = {
      name: String(data.get("name") ?? "").trim(),
      participant_character_card_ids: [firstCharacterId, secondCharacterId],
      rounds_per_trigger: Number(data.get("rounds_per_trigger") ?? 1),
      maximum_triggers: Number(data.get("maximum_triggers") ?? 1),
      cooldown_seconds: Number(data.get("cooldown_seconds") ?? 60),
      duration_seconds: Number(data.get("duration_minutes") ?? 10) * 60,
      intensity
    };
    try {
      setWorking(true);
      if (editingTemplate) {
        await interactionApi.updateTemplate(editingTemplate.id, payload);
      } else {
        await interactionApi.createTemplate({
          server_profile_id: serverProfile.id,
          ...payload
        });
      }
      setTemplateDrawerOpen(false);
      setEditingTemplate(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function applyTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!applyingTemplate) return;
    const data = new FormData(event.currentTarget);
    const targetUserId = discordUserId(String(data.get("target_user_id") ?? ""));
    try {
      setWorking(true);
      await interactionApi.applyTemplate(applyingTemplate.id, {
        channel_id: String(data.get("channel_id") ?? ""),
        target_user_id: targetUserId,
        target_display_name: String(data.get("target_display_name") ?? "").trim(),
        status: String(data.get("status")) === "active" ? "active" : "paused"
      });
      setApplyingTemplate(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeTemplate(item: InteractionTemplate) {
    if (!window.confirm(zh ? `删除 Template“${item.name}”？` : `Delete “${item.name}”?`)) return;
    try {
      setWorking(true);
      await interactionApi.deleteTemplate(item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function setStatus(item: InteractionSession, status: InteractionStatus) {
    try {
      setWorking(true);
      await interactionApi.updateSessionStatus(item.id, status);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeSession(item: InteractionSession) {
    if (!window.confirm(zh ? "删除这个 Server Session？" : "Delete this Server Session?")) {
      return;
    }
    try {
      setWorking(true);
      await interactionApi.deleteSession(item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="interaction-module">
      {error && <p className="error-note interaction-error">{error}</p>}
      <section className="paper-sheet interaction-panel">
        <div className="panel-heading-row interaction-heading-row">
          <div>
            <p className="tape-label">INTERACTION TEMPLATES</p>
            <h2>{zh ? "可复用的多角色互动规则" : "Reusable multi-character interaction rules"}</h2>
            <p>
              {zh
                ? `Template 属于 ${serverProfile.guild_name}。它保存角色顺序与轮次；Apply 时才选择 Channel 和目标用户。`
                : `Templates belong to ${serverProfile.guild_name}. They save character order and limits; Channel and target member are chosen when applied.`}
            </p>
          </div>
          {!demoMode && (
            <button
              className="ink-button"
              onClick={openNewTemplate}
              disabled={activeDeployments.length < 2}
            >
              {zh ? "+ 新 Template" : "+ New Template"}
            </button>
          )}
        </div>

        {activeDeployments.length < 2 && (
          <div className="interaction-server-warning">
            {zh
              ? "当前 Server 至少需要两个 Active Character Deployment，才能建立双角色 Template。"
              : "This Server needs at least two active Character Deployments before a two-character Template can be created."}
          </div>
        )}

        {loading ? (
          <p>{zh ? "读取 Template…" : "Loading Templates…"}</p>
        ) : (
          <div className="interaction-template-grid">
            {templates.map((item) => (
              <article className="interaction-template-card" key={item.id}>
                <div className="interaction-template-title">
                  <div>
                    <small>ROAST TEMPLATE</small>
                    <strong>{item.name}</strong>
                  </div>
                  <span className="interaction-intensity">{item.intensity}</span>
                </div>
                <div className="interaction-order-note">
                  {item.participant_names.join(" → ")}
                </div>
                <dl className="interaction-template-metrics">
                  <div><dt>{zh ? "轮次" : "Rounds"}</dt><dd>{item.rounds_per_trigger}</dd></div>
                  <div><dt>{zh ? "回复" : "Replies"}</dt><dd>{item.maximum_replies_per_trigger}</dd></div>
                  <div><dt>{zh ? "触发" : "Triggers"}</dt><dd>{item.maximum_triggers}</dd></div>
                  <div><dt>{zh ? "冷却" : "Cooldown"}</dt><dd>{item.cooldown_seconds}s</dd></div>
                </dl>
                {!demoMode && (
                  <div className="interaction-actions">
                    <button
                      className="ink-button compact-ink-button"
                      onClick={() => setApplyingTemplate(item)}
                      disabled={!availableChannels.length}
                    >
                      {zh ? "Apply 到 Server" : "Apply to Server"}
                    </button>
                    <button className="paper-button" onClick={() => openEditTemplate(item)}>
                      {zh ? "编辑" : "Edit"}
                    </button>
                    <button
                      className="text-button danger-text"
                      onClick={() => void removeTemplate(item)}
                    >
                      {zh ? "删除" : "Delete"}
                    </button>
                  </div>
                )}
              </article>
            ))}
            {!templates.length && (
              <div className="interaction-empty-card">
                <strong>{zh ? "还没有 Interaction Template" : "No Interaction Templates yet"}</strong>
                <p>
                  {zh
                    ? "先保存角色顺序和运行限制，之后可以重复 Apply 给不同 Channel 或目标用户。"
                    : "Save character order and limits once, then apply the Template repeatedly to different Channels or target members."}
                </p>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="paper-sheet interaction-panel">
        <div className="panel-heading-row interaction-heading-row">
          <div>
            <p className="tape-label">SERVER SESSIONS</p>
            <h2>{zh ? "当前 Server 正在运行的 Session" : "Sessions applied to this Server"}</h2>
            <p>
              {zh
                ? "运行计数、冷却、目标用户和状态属于 Session，不会修改原始 Template。"
                : "Trigger counts, cooldown state, target member, and status belong to the Session and do not change the Template."}
            </p>
          </div>
        </div>
        <div className="interaction-card-grid">
          {sessions.map((item) => (
            <article className="interaction-card" key={item.id}>
              <div className="interaction-card-heading">
                <strong>Roast Session</strong>
                <span className={`deployment-status status-${item.status}`}>{item.status}</span>
              </div>
              <p><b>{zh ? "目标" : "Target"}:</b> {item.target_display_name || item.target_user_id}</p>
              <p><b>{zh ? "角色" : "Characters"}:</b> {item.participant_names.join(" → ")}</p>
              <p><b>Channel:</b> #{item.channel_name}</p>
              <p><b>{zh ? "轮次" : "Rounds"}:</b> {item.rounds_per_trigger} · {item.maximum_replies_per_trigger} {zh ? "条回复/触发" : "replies/trigger"}</p>
              <p><b>{zh ? "触发" : "Triggers"}:</b> {item.completed_triggers} / {item.maximum_triggers}</p>
              <p><b>{zh ? "冷却" : "Cooldown"}:</b> {item.cooldown_seconds}s · {minutes(item.duration_seconds)}m</p>
              {!demoMode && (
                <div className="interaction-actions">
                  {item.status !== "active" && (
                    <button className="paper-button" disabled={working} onClick={() => void setStatus(item, "active")}>{zh ? "启用" : "Activate"}</button>
                  )}
                  {item.status === "active" && (
                    <button className="paper-button" disabled={working} onClick={() => void setStatus(item, "paused")}>{zh ? "暂停" : "Pause"}</button>
                  )}
                  {!['stopped', 'completed'].includes(item.status) && (
                    <button className="paper-button" disabled={working} onClick={() => void setStatus(item, "stopped")}>{zh ? "停止" : "Stop"}</button>
                  )}
                  <button className="text-button danger-text" disabled={working} onClick={() => void removeSession(item)}>{zh ? "删除" : "Delete"}</button>
                </div>
              )}
            </article>
          ))}
          {!loading && !sessions.length && (
            <div className="interaction-empty-card compact">
              <strong>{zh ? "当前 Server 没有 Session" : "No Sessions in this Server"}</strong>
              <p>{zh ? "从上方 Template 点击 Apply。" : "Apply a Template above to create one."}</p>
            </div>
          )}
        </div>
      </section>

      {templateDrawerOpen && !demoMode && (
        <div className="interaction-drawer-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setTemplateDrawerOpen(false);
        }}>
          <aside className="interaction-drawer" role="dialog" aria-modal="true">
            <header className="interaction-drawer-header">
              <div>
                <p className="tape-label">{editingTemplate ? "EDIT TEMPLATE" : "NEW TEMPLATE"}</p>
                <h2>{editingTemplate ? editingTemplate.name : zh ? "建立 Interaction Template" : "Create Interaction Template"}</h2>
                <p>{serverProfile.guild_name}</p>
              </div>
              <button className="drawer-close-button" onClick={() => setTemplateDrawerOpen(false)}>{zh ? "关闭" : "Close"}</button>
            </header>
            <form className="interaction-drawer-form" onSubmit={saveTemplate} key={editingTemplate?.id ?? "new-template"}>
              <label className="drawer-form-wide">
                {zh ? "Template 名称" : "Template name"}
                <input name="name" required defaultValue={editingTemplate?.name ?? "Ann + Ning Roast"} />
              </label>
              <label>
                {zh ? "第一位角色" : "First character"}
                <select value={firstCharacterId} onChange={(event) => setFirstCharacterId(event.currentTarget.value)} required>
                  {activeDeployments.map((item) => (
                    <option key={item.id} value={item.character_card_id}>{item.character_display_name}</option>
                  ))}
                </select>
              </label>
              <label>
                {zh ? "第二位角色" : "Second character"}
                <select value={secondCharacterId} onChange={(event) => setSecondCharacterId(event.currentTarget.value)} required>
                  {activeDeployments.filter((item) => item.character_card_id !== firstCharacterId).map((item) => (
                    <option key={item.id} value={item.character_card_id}>{item.character_display_name}</option>
                  ))}
                </select>
              </label>
              <div className="interaction-form-summary drawer-form-wide">
                <strong>{zh ? "固定顺序" : "Fixed order"}</strong>
                <span>
                  {activeDeployments.find((item) => item.character_card_id === firstCharacterId)?.character_display_name || "—"}
                  {" → "}
                  {activeDeployments.find((item) => item.character_card_id === secondCharacterId)?.character_display_name || "—"}
                </span>
                <small>{zh ? "每一轮两个角色各回复一次。" : "Each round gives both characters one turn."}</small>
              </div>
              <label>
                {zh ? "每次触发轮数" : "Rounds per trigger"}
                <input name="rounds_per_trigger" type="number" min="1" max="3" defaultValue={editingTemplate?.rounds_per_trigger ?? 1} />
              </label>
              <label>
                {zh ? "最多触发次数" : "Maximum triggers"}
                <input name="maximum_triggers" type="number" min="1" max="5" defaultValue={editingTemplate?.maximum_triggers ?? 1} />
              </label>
              <label>
                {zh ? "冷却秒数" : "Cooldown seconds"}
                <input name="cooldown_seconds" type="number" min="0" max="3600" defaultValue={editingTemplate?.cooldown_seconds ?? 60} />
              </label>
              <label>
                {zh ? "持续分钟" : "Duration minutes"}
                <input name="duration_minutes" type="number" min="1" max="1440" defaultValue={minutes(editingTemplate?.duration_seconds ?? 600)} />
              </label>
              <label className="drawer-form-wide">
                {zh ? "强度" : "Intensity"}
                <select value={intensity} onChange={(event) => setIntensity(event.currentTarget.value as InteractionIntensity)}>
                  <option value="light">Light</option>
                  <option value="playful">Playful</option>
                  <option value="sharp">Sharp</option>
                </select>
              </label>
              <button className="ink-button drawer-form-wide" disabled={working || !firstCharacterId || !secondCharacterId}>
                {working ? (zh ? "保存中…" : "Saving…") : zh ? "保存 Template" : "Save Template"}
              </button>
            </form>
          </aside>
        </div>
      )}

      {applyingTemplate && !demoMode && (
        <div className="interaction-drawer-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setApplyingTemplate(null);
        }}>
          <aside className="interaction-drawer compact-drawer" role="dialog" aria-modal="true">
            <header className="interaction-drawer-header">
              <div>
                <p className="tape-label">APPLY TEMPLATE</p>
                <h2>{applyingTemplate.name}</h2>
                <p>{applyingTemplate.participant_names.join(" → ")} · {serverProfile.guild_name}</p>
              </div>
              <button className="drawer-close-button" onClick={() => setApplyingTemplate(null)}>{zh ? "关闭" : "Close"}</button>
            </header>
            <form className="interaction-drawer-form" onSubmit={applyTemplate}>
              <label className="drawer-form-wide">
                Channel
                <select name="channel_id" required defaultValue={availableChannels[0]?.id ?? ""}>
                  {availableChannels.map((channel) => (
                    <option key={channel.id} value={channel.id}>#{channel.name}</option>
                  ))}
                </select>
              </label>
              <label className="drawer-form-wide">
                {zh ? "目标用户 ID 或 Mention" : "Target user ID or mention"}
                <input name="target_user_id" required placeholder="<@606232885489303603>" />
              </label>
              <label className="drawer-form-wide">
                {zh ? "目标显示名称" : "Target display name"}
                <input name="target_display_name" placeholder="501 Not Implemented" />
              </label>
              <label className="drawer-form-wide">
                {zh ? "建立后状态" : "Initial status"}
                <select name="status" defaultValue="paused">
                  <option value="paused">Paused</option>
                  <option value="active">Active</option>
                </select>
              </label>
              <small className="interaction-consent-note drawer-form-wide">
                {zh
                  ? "仅用于已明确同意参与的测试成员或你自己的测试账号。"
                  : "Use only with a consenting test member or your own test account."}
              </small>
              <button className="ink-button drawer-form-wide" disabled={working || !availableChannels.length}>
                {working ? (zh ? "Apply 中…" : "Applying…") : zh ? "建立 Server Session" : "Create Server Session"}
              </button>
            </form>
          </aside>
        </div>
      )}
    </section>
  );
}
'''
Path("web/src/InteractionSessionsPanel.tsx").write_text(interaction_panel, encoding="utf-8")

# ---------------------------------------------------------------------------
# Deployment Center: selected Server controls all runtime data.
# ---------------------------------------------------------------------------
replace(
    "web/src/DeploymentCenter.tsx",
    '''  const [error, setError] = useState<string | null>(null);

  const [connectionOpen, setConnectionOpen] = useState(false);
''',
    '''  const [error, setError] = useState<string | null>(null);
  const [selectedServerProfileId, setSelectedServerProfileId] = useState(() =>
    new URLSearchParams(window.location.search).get("server_profile") ?? ""
  );

  const [connectionOpen, setConnectionOpen] = useState(false);
''',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''          status: statusFilter
        }),
''',
    '''          status: statusFilter,
          serverProfileId: selectedServerProfileId || "__no_server_selected__"
        }),
''',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''      setServerProfiles(nextProfiles);
      setServerCatalog(nextCatalog);
''',
    '''      setServerProfiles(nextProfiles);
      setServerCatalog(nextCatalog);
      setSelectedServerProfileId((current) =>
        current && nextProfiles.some((item) => item.id === current)
          ? current
          : nextProfiles[0]?.id ?? ""
      );
''',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''  useEffect(() => {
    void load(1);
  }, [characterFilter, platformFilter, statusFilter]);
''',
    '''  useEffect(() => {
    void load(1);
  }, [characterFilter, platformFilter, selectedServerProfileId, statusFilter]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedServerProfileId) url.searchParams.set("server_profile", selectedServerProfileId);
    else url.searchParams.delete("server_profile");
    window.history.replaceState({}, "", url);
    setDeploymentOpen(false);
    setEditingDeployment(null);
    setDeploymentPage(1);
  }, [selectedServerProfileId]);
''',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''  const selectedConnection = connections.find((item) => item.id === draftConnectionId);
''',
    '''  const selectedWorkspaceProfile = profileMap.get(selectedServerProfileId);
  const selectedWorkspaceCatalog = selectedWorkspaceProfile
    ? serverCatalog.find(
        (server) =>
          server.connection_id === selectedWorkspaceProfile.connection_id &&
          server.guild_id === selectedWorkspaceProfile.guild_id
      )
    : undefined;
  const selectedConnection = connections.find((item) => item.id === draftConnectionId);
''',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''  function openNewDeployment() {
    const connectionId = connections[0]?.id ?? "";
''',
    '''  function openNewDeployment() {
    const connectionId = selectedWorkspaceProfile?.connection_id ?? "";
    if (!selectedWorkspaceProfile) return;
''',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''    setDraftServerProfileId(
      serverProfiles.find((profile) => profile.connection_id === connectionId)?.id ?? ""
    );
''',
    '''    setDraftServerProfileId(selectedWorkspaceProfile.id);
''',
    count=1,
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''  const canSaveDeployment =
    Boolean(draftCharacterId && draftConnectionId) &&
''',
    '''  const canSaveDeployment =
    Boolean(selectedWorkspaceProfile && draftCharacterId && draftConnectionId) &&
''',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''              disabled={!cards.length || !connections.length}
''',
    '''              disabled={!cards.length || !selectedWorkspaceProfile}
''',
)
# Insert Server Workspace before summary cards.
replace(
    "web/src/DeploymentCenter.tsx",
    '''      <section className="deployment-summary-grid">
''',
    '''      <DiscordServerProfilesPanel
        connections={connections}
        profiles={serverProfiles}
        catalog={serverCatalog}
        selectedProfileId={selectedServerProfileId}
        demoMode={demoMode}
        zh={zh}
        onSelectProfile={setSelectedServerProfileId}
        onChanged={load}
        onError={(message) => setError(message || null)}
      />

      <section className="deployment-summary-grid">
''',
)
# Remove old sidebar Server Profile panel.
replace(
    "web/src/DeploymentCenter.tsx",
    '''
          <DiscordServerProfilesPanel
            connections={connections}
            profiles={serverProfiles}
            catalog={serverCatalog}
            demoMode={demoMode}
            zh={zh}
            onChanged={load}
            onError={(message) => setError(message || null)}
          />
''',
    "\n",
)
# Keep the form context fixed to the selected Server.
replace(
    "web/src/DeploymentCenter.tsx",
    '''                    disabled={Boolean(editingDeployment)}
                    required
''',
    '''                    disabled={Boolean(editingDeployment) || Boolean(selectedWorkspaceProfile)}
                    required
''',
    count=1,
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''                        value={draftServerProfileId}
                        onChange={(event) => changeServerProfile(event.currentTarget.value)}
''',
    '''                        value={draftServerProfileId}
                        onChange={(event) => changeServerProfile(event.currentTarget.value)}
                        disabled={Boolean(selectedWorkspaceProfile)}
''',
)
# Selected server context note above deployment form.
replace(
    "web/src/DeploymentCenter.tsx",
    '''              <p className="deployment-foundation-note">
''',
    '''              {selectedWorkspaceProfile && (
                <div className="deployment-server-context">
                  <span>{zh ? "当前 Server" : "Current Server"}</span>
                  <strong>{selectedWorkspaceProfile.guild_name}</strong>
                  <small>{selectedWorkspaceProfile.name} · ID {selectedWorkspaceProfile.guild_id}</small>
                </div>
              )}
              <p className="deployment-foundation-note">
''',
)
# Interaction panel is rendered only within selected Server.
replace(
    "web/src/DeploymentCenter.tsx",
    '''      <InteractionSessionsPanel demoMode={demoMode} zh={zh} />
''',
    '''      {selectedWorkspaceProfile && (
        <InteractionSessionsPanel
          demoMode={demoMode}
          zh={zh}
          serverProfile={selectedWorkspaceProfile}
          serverCatalog={selectedWorkspaceCatalog}
        />
      )}
''',
)

# ---------------------------------------------------------------------------
# Theme-matching CSS for Server and Interaction drawers/cards.
# ---------------------------------------------------------------------------
server_css = '''.connection-card-actions {
  grid-column: 2 / -1;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.server-workspace-panel {
  display: grid;
  gap: 18px;
  margin-bottom: 24px;
  overflow: visible;
}

.server-workspace-heading,
.server-workspace-selector-row,
.server-workspace-actions,
.server-workspace-current-card,
.server-readonly-identity,
.server-drawer-header,
.server-drawer-footer,
.server-drawer-section-heading,
.server-sticker-title-row,
.sticker-editor-identity {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.server-workspace-heading {
  align-items: flex-start;
}

.server-workspace-heading h2,
.server-drawer-header h2,
.server-drawer-section-heading h3 {
  margin: 5px 0 7px;
}

.server-workspace-heading p,
.server-drawer-header p,
.server-drawer-section-heading p {
  margin: 0;
  color: rgba(41, 35, 48, 0.66);
}

.server-workspace-actions {
  flex: 0 0 auto;
  flex-wrap: wrap;
}

.server-workspace-selector-row {
  align-items: stretch;
}

.server-workspace-selector-row > label {
  display: grid;
  gap: 7px;
  min-width: min(360px, 100%);
  font-size: 0.8rem;
  font-weight: 800;
}

.server-workspace-current-card {
  flex: 1;
  justify-content: flex-start;
  min-width: 280px;
  padding: 13px 16px;
  border: 1px solid rgba(112, 86, 158, 0.18);
  border-radius: 15px;
  background:
    linear-gradient(120deg, rgba(155, 124, 245, 0.09), rgba(255, 255, 255, 0.58)),
    rgba(255, 255, 255, 0.5);
  box-shadow: 0 9px 28px rgba(68, 52, 83, 0.07);
}

.server-workspace-current-card > div:nth-child(2),
.server-readonly-identity > div:nth-child(2),
.sticker-editor-identity > div:nth-child(2) {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.server-workspace-current-card span,
.server-workspace-current-card small,
.server-readonly-identity span,
.server-readonly-identity small,
.sticker-editor-identity small {
  color: rgba(41, 35, 48, 0.6);
  overflow-wrap: anywhere;
}

.server-workspace-icon {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 13px;
  background: rgba(155, 124, 245, 0.16);
  color: #655080;
  font-family: var(--font-hand, cursive);
  font-size: 1.15rem;
  font-weight: 900;
}

.server-workspace-stat {
  display: grid;
  gap: 1px;
  margin-left: auto;
  text-align: right;
}

.server-workspace-stat strong {
  font-size: 1.25rem;
}

.server-workspace-stat span {
  font-size: 0.7rem;
}

.server-workspace-placeholder {
  display: grid;
  place-items: center;
  min-height: 70px;
  padding: 16px;
  border: 1px dashed rgba(112, 86, 158, 0.25);
  border-radius: 14px;
  color: rgba(41, 35, 48, 0.65);
  text-align: center;
}

.server-workspace-placeholder.large {
  min-height: 130px;
}

.server-workspace-placeholder p {
  max-width: 620px;
  margin: 6px 0 0;
}

.server-drawer-backdrop,
.interaction-drawer-backdrop {
  position: fixed;
  z-index: 1400;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  background: rgba(35, 29, 40, 0.28);
  backdrop-filter: blur(4px);
}

.server-drawer,
.interaction-drawer {
  width: min(760px, 94vw);
  height: 100%;
  overflow: auto;
  padding: 28px;
  border-left: 1px solid rgba(112, 86, 158, 0.18);
  background:
    linear-gradient(rgba(255, 253, 249, 0.96), rgba(255, 252, 247, 0.98)),
    repeating-linear-gradient(0deg, transparent 0 26px, rgba(97, 82, 110, 0.025) 27px);
  box-shadow: -20px 0 60px rgba(34, 26, 41, 0.18);
}

.server-drawer-header,
.interaction-drawer-header {
  align-items: flex-start;
  padding-bottom: 20px;
  border-bottom: 1px dashed rgba(112, 86, 158, 0.22);
}

.drawer-close-button {
  min-width: 72px;
  padding: 10px 16px;
  border: 0;
  border-radius: 999px;
  background: #9270a4;
  color: white;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 9px 24px rgba(83, 54, 98, 0.18);
}

.server-drawer-tabs {
  display: flex;
  gap: 8px;
  margin: 18px 0 0;
  padding: 5px;
  border-radius: 14px;
  background: rgba(112, 86, 158, 0.07);
}

.server-drawer-tabs button {
  flex: 1;
  padding: 10px 13px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: rgba(41, 35, 48, 0.65);
  font-weight: 800;
  cursor: pointer;
}

.server-drawer-tabs button.active {
  background: rgba(255, 255, 255, 0.82);
  color: #5d466f;
  box-shadow: 0 5px 16px rgba(55, 42, 65, 0.08);
}

.server-drawer-form,
.interaction-drawer-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 15px;
  padding: 22px 0;
}

.server-drawer-form > label,
.interaction-drawer-form > label,
.sticker-editor-fields > label {
  display: grid;
  gap: 7px;
  font-size: 0.82rem;
  font-weight: 800;
}

.drawer-form-wide {
  grid-column: 1 / -1;
}

.server-readonly-identity {
  justify-content: flex-start;
  padding: 13px 15px;
  border-radius: 14px;
  background: rgba(155, 124, 245, 0.08);
}

.server-readonly-identity > small {
  margin-left: auto;
}

.server-profile-list {
  display: grid;
  gap: 10px;
}

.server-profile-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 14px;
  border: 1px solid rgba(41, 35, 48, 0.13);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.5);
}

.server-profile-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.server-channel-picker,
.deployment-channel-picker {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px dashed rgba(112, 86, 158, 0.24);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.42);
}

.server-channel-picker > div:first-child {
  display: grid;
  gap: 4px;
}

.server-channel-picker > div:first-child small,
.deployment-channel-picker .deployment-form-divider span {
  color: rgba(41, 35, 48, 0.64);
  font-size: 0.78rem;
  line-height: 1.45;
}

.server-channel-picker fieldset,
.deployment-channel-picker fieldset {
  display: grid;
  gap: 7px;
  min-width: 0;
  margin: 0;
  padding: 12px;
  border: 1px solid rgba(41, 35, 48, 0.13);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.54);
}

.server-channel-picker legend,
.deployment-channel-picker legend {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 5px;
  font-size: 0.78rem;
  font-weight: 800;
}

.server-channel-option {
  display: grid !important;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px !important;
  min-height: 30px;
  padding: 5px 7px;
  border-radius: 7px;
  font-size: 0.78rem !important;
  font-weight: 600 !important;
}

.server-channel-option:hover {
  background: rgba(112, 86, 158, 0.07);
}

.server-channel-option input,
.server-channel-picker legend input,
.deployment-channel-picker legend input {
  width: 16px !important;
  min-height: 16px !important;
  margin: 0;
  padding: 0 !important;
}

.server-channel-option small {
  color: rgba(41, 35, 48, 0.55);
  font-size: 0.68rem;
}

.deployment-form-wide {
  grid-column: 1 / -1;
}

.deployment-form-divider {
  display: grid;
  gap: 4px;
  padding: 12px 0 4px;
  border-top: 1px dashed rgba(41, 35, 48, 0.2);
}

.deployment-channel-picker .deployment-form-divider {
  padding-top: 0;
  border-top: 0;
}

.deployment-server-context {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 2px 12px;
  margin: 0 0 14px;
  padding: 12px 15px;
  border-radius: 13px;
  background: rgba(155, 124, 245, 0.09);
}

.deployment-server-context span {
  grid-row: 1 / 3;
  align-self: center;
  color: rgba(41, 35, 48, 0.58);
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
}

.deployment-server-context small {
  color: rgba(41, 35, 48, 0.6);
}

.server-sticker-section {
  display: grid;
  gap: 18px;
  padding: 24px 0;
}

.server-sticker-count {
  display: grid;
  min-width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 50%;
  background: rgba(155, 124, 245, 0.14);
  color: #634d78;
  font-weight: 900;
}

.server-sticker-grid {
  display: grid;
  gap: 12px;
}

.server-sticker-card {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 14px;
  border: 1px solid rgba(112, 86, 158, 0.14);
  border-radius: 15px;
  background: rgba(255, 255, 255, 0.58);
}

.server-sticker-preview {
  display: grid;
  width: 72px;
  height: 72px;
  place-items: center;
  overflow: hidden;
  border-radius: 14px;
  background: rgba(155, 124, 245, 0.09);
  color: #76588b;
  font-size: 1.5rem;
}

.server-sticker-preview.compact {
  width: 50px;
  height: 50px;
}

.server-sticker-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.server-sticker-copy {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.server-sticker-copy small {
  color: rgba(41, 35, 48, 0.55);
}

.server-sticker-copy p {
  margin: 0;
  color: rgba(41, 35, 48, 0.78);
}

.server-sticker-title-row {
  justify-content: flex-start;
}

.server-sticker-meta {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.server-sticker-meta span,
.sticker-source {
  display: inline-flex;
  width: fit-content;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(90, 127, 104, 0.11);
  font-size: 0.7rem;
}

.source-manual {
  background: rgba(155, 124, 245, 0.14);
}

.server-sticker-empty {
  display: grid;
  place-items: center;
  min-height: 130px;
  padding: 18px;
  border: 1px dashed rgba(112, 86, 158, 0.23);
  border-radius: 14px;
  text-align: center;
}

.server-sticker-empty p {
  max-width: 540px;
  margin: 6px 0 0;
  color: rgba(41, 35, 48, 0.62);
}

.sticker-meaning-editor {
  display: grid;
  gap: 15px;
  padding: 18px;
  border: 1px solid rgba(155, 124, 245, 0.2);
  border-radius: 16px;
  background: rgba(155, 124, 245, 0.06);
}

.sticker-editor-identity {
  justify-content: flex-start;
}

.sticker-editor-identity .text-button {
  margin-left: auto;
}

.sticker-editor-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 13px;
}

@media (max-width: 760px) {
  .server-workspace-heading,
  .server-workspace-selector-row,
  .server-drawer-header,
  .server-drawer-section-heading {
    display: grid;
  }

  .server-workspace-actions {
    justify-content: flex-start;
  }

  .server-workspace-current-card,
  .server-sticker-card {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .server-workspace-stat,
  .server-sticker-card > .paper-button {
    grid-column: 2;
    margin-left: 0;
    text-align: left;
  }

  .server-drawer,
  .interaction-drawer {
    width: 100%;
    padding: 20px;
  }

  .server-drawer-form,
  .interaction-drawer-form,
  .sticker-editor-fields {
    grid-template-columns: 1fr;
  }

  .drawer-form-wide,
  .deployment-form-wide {
    grid-column: auto;
  }

  .server-channel-option {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .server-channel-option small {
    grid-column: 2;
  }
}
'''
Path("web/src/discordServerProfiles.css").write_text(server_css, encoding="utf-8")

interaction_css = '''.interaction-module {
  display: grid;
  gap: 24px;
  margin-top: 24px;
}

.interaction-panel {
  padding: 24px;
}

.interaction-panel h2 {
  margin: 4px 0 8px;
}

.interaction-heading-row {
  align-items: flex-start;
}

.interaction-error {
  margin: 0;
}

.interaction-template-grid,
.interaction-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.interaction-template-card,
.interaction-card,
.interaction-empty-card {
  padding: 17px;
  border: 1px solid rgba(112, 86, 158, 0.16);
  border-radius: 16px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.66), rgba(155, 124, 245, 0.035)),
    rgba(255, 255, 255, 0.46);
  box-shadow: 0 9px 24px rgba(64, 48, 76, 0.045);
}

.interaction-template-card {
  position: relative;
  overflow: hidden;
}

.interaction-template-card::before {
  position: absolute;
  width: 80px;
  height: 20px;
  top: -4px;
  left: 24px;
  transform: rotate(-2deg);
  background: rgba(205, 186, 232, 0.46);
  content: "";
}

.interaction-template-title,
.interaction-card-heading,
.interaction-actions,
.interaction-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 9px;
  flex-wrap: wrap;
}

.interaction-template-title {
  position: relative;
  padding-top: 9px;
}

.interaction-template-title > div {
  display: grid;
  gap: 3px;
}

.interaction-template-title small {
  color: rgba(41, 35, 48, 0.5);
  font-size: 0.67rem;
  letter-spacing: 0.09em;
}

.interaction-intensity {
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(155, 124, 245, 0.13);
  color: #664d7a;
  font-size: 0.72rem;
  font-weight: 800;
}

.interaction-order-note {
  margin: 15px 0 12px;
  padding: 11px 13px;
  border-radius: 12px;
  background: rgba(155, 124, 245, 0.08);
  color: #513f60;
  font-weight: 800;
}

.interaction-template-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.interaction-template-metrics > div {
  display: grid;
  gap: 2px;
  padding: 8px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.55);
}

.interaction-template-metrics dt {
  color: rgba(41, 35, 48, 0.5);
  font-size: 0.66rem;
}

.interaction-template-metrics dd {
  margin: 0;
  font-weight: 900;
}

.interaction-card p {
  margin: 8px 0;
}

.interaction-actions {
  justify-content: flex-start;
  margin-top: 14px;
}

.compact-ink-button {
  padding: 9px 14px;
}

.interaction-empty-card {
  display: grid;
  min-height: 150px;
  place-items: center;
  text-align: center;
  border-style: dashed;
}

.interaction-empty-card.compact {
  min-height: 110px;
}

.interaction-empty-card p {
  max-width: 440px;
  margin: 6px 0 0;
  color: rgba(41, 35, 48, 0.6);
}

.interaction-server-warning {
  margin-top: 15px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(232, 174, 92, 0.1);
  color: #75562f;
  font-size: 0.8rem;
}

.interaction-drawer {
  width: min(650px, 94vw);
}

.interaction-drawer.compact-drawer {
  width: min(520px, 94vw);
}

.interaction-drawer-header {
  align-items: flex-start;
}

.interaction-drawer-form {
  padding-top: 22px;
}

.interaction-form-summary {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(155, 124, 245, 0.08);
}

.interaction-consent-note {
  display: block;
  max-width: 760px;
  color: rgba(41, 35, 48, 0.62);
}

@media (max-width: 700px) {
  .interaction-template-metrics {
    grid-template-columns: 1fr 1fr;
  }
}
'''
Path("web/src/interactionSessions.css").write_text(interaction_css, encoding="utf-8")
