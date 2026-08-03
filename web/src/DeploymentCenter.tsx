import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CharacterCard } from "./api";
import {
  deploymentApi,
  type CharacterDeployment,
  type ConnectionMode,
  type DeploymentStatus,
  type MemoryScope,
  type ParticipationMode,
  type PlatformConnection,
  type PlatformId
} from "./deploymentApi";
import {
  discordIdentityApi,
  type DeploymentIdentityMode,
  type DeploymentMessageIdentity
} from "./discordIdentityApi";
import { useI18n } from "./i18n";

interface Props {
  cards: CharacterCard[];
  initialCharacterId?: string | null;
  demoMode?: boolean;
  onClose: () => void;
}

const platformLabels: Record<PlatformId, string> = {
  discord: "Discord",
  whatsapp: "WhatsApp",
  telegram: "Telegram"
};

const platformNotes: Record<PlatformId, { en: string; zh: string }> = {
  discord: {
    en: "Managed Gateway connector with per-channel webhook identity delivery.",
    zh: "托管式 Gateway Connector，并支持每个 Channel 的 Webhook 角色身份。"
  },
  whatsapp: {
    en: "Local experimental connector. The linked-device session stays on the user's computer.",
    zh: "本地实验 Connector，Linked Device Session 保留在用户电脑。"
  },
  telegram: {
    en: "Managed Bot connector with native group and sticker support.",
    zh: "托管式 Bot Connector，支持群组与原生贴图。"
  }
};

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function destination(deployment: CharacterDeployment): string {
  const workspace = deployment.workspace_name || platformLabels[deployment.platform];
  const channel = deployment.channel_name || deployment.channel_id;
  return deployment.thread_name
    ? `${workspace} / ${channel} / ${deployment.thread_name}`
    : `${workspace} / ${channel}`;
}

function defaultIdentity(deployment: CharacterDeployment): DeploymentMessageIdentity {
  const webhook = deployment.platform === "discord";
  return {
    deployment_id: deployment.id,
    mode: webhook ? "webhook" : "bot",
    display_name: deployment.character_display_name,
    avatar_url: "",
    webhook_status: webhook ? "pending" : "not_required",
    last_error: "",
    updated_at: deployment.updated_at
  };
}

export function DeploymentCenter({
  cards,
  initialCharacterId = null,
  demoMode = false,
  onClose
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [identities, setIdentities] = useState<DeploymentMessageIdentity[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [deploymentOpen, setDeploymentOpen] = useState(Boolean(initialCharacterId));
  const [editingDeployment, setEditingDeployment] = useState<CharacterDeployment | null>(null);
  const [platformFilter, setPlatformFilter] = useState<"all" | PlatformId>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | DeploymentStatus>("all");
  const [characterFilter, setCharacterFilter] = useState(initialCharacterId ?? "all");
  const [draftCharacterId, setDraftCharacterId] = useState(
    initialCharacterId ?? cards[0]?.id ?? ""
  );
  const [draftConnectionId, setDraftConnectionId] = useState("");
  const [connectionPlatform, setConnectionPlatform] = useState<PlatformId>("discord");
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("managed");

  async function load() {
    try {
      setLoading(true);
      const [nextConnections, nextDeployments, nextIdentities] = await Promise.all([
        deploymentApi.listConnections(),
        deploymentApi.listDeployments(),
        discordIdentityApi.list()
      ]);
      setConnections(nextConnections);
      setDeployments(nextDeployments);
      setIdentities(nextIdentities);
      setDraftConnectionId((current) =>
        current && nextConnections.some((item) => item.id === current)
          ? current
          : nextConnections[0]?.id ?? ""
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (initialCharacterId) {
      setCharacterFilter(initialCharacterId);
      setDraftCharacterId(initialCharacterId);
      setDeploymentOpen(true);
    }
  }, [initialCharacterId]);

  const identityMap = useMemo(
    () => new Map(identities.map((item) => [item.deployment_id, item])),
    [identities]
  );
  const filtered = useMemo(
    () =>
      deployments.filter(
        (item) =>
          (platformFilter === "all" || item.platform === platformFilter) &&
          (statusFilter === "all" || item.status === statusFilter) &&
          (characterFilter === "all" || item.character_card_id === characterFilter)
      ),
    [characterFilter, deployments, platformFilter, statusFilter]
  );
  const counts = useMemo(
    () => ({
      active: deployments.filter((item) => item.status === "active").length,
      paused: deployments.filter((item) => item.status === "paused").length,
      attention: deployments.filter(
        (item) => item.status === "error" || item.status === "offline"
      ).length
    }),
    [deployments]
  );
  const selectedConnection = connections.find(
    (item) => item.id === draftConnectionId
  );
  const formIdentity = editingDeployment
    ? identityMap.get(editingDeployment.id) ?? defaultIdentity(editingDeployment)
    : null;

  function changeConnectionPlatform(platform: PlatformId) {
    setConnectionPlatform(platform);
    setConnectionMode(platform === "whatsapp" ? "local" : "managed");
  }

  function openNewDeployment() {
    setEditingDeployment(null);
    setDraftCharacterId(initialCharacterId ?? cards[0]?.id ?? "");
    setDraftConnectionId(connections[0]?.id ?? "");
    setDeploymentOpen(true);
  }

  function openEditDeployment(item: CharacterDeployment) {
    setEditingDeployment(item);
    setDraftCharacterId(item.character_card_id);
    setDraftConnectionId(item.connection_id);
    setDeploymentOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function closeDeploymentForm() {
    setDeploymentOpen(false);
    setEditingDeployment(null);
  }

  async function createConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      setWorking(true);
      setError(null);
      await deploymentApi.createConnection({
        platform: connectionPlatform,
        display_name: String(data.get("display_name") ?? "").trim(),
        connection_mode: connectionMode,
        external_account_id: String(data.get("external_account_id") ?? "").trim(),
        status: "disconnected",
        metadata: {
          setup_state: "connector_not_configured",
          product_stage: "connector"
        }
      });
      form.reset();
      setConnectionOpen(false);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function saveDeployment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const baseFields = {
      workspace_id: String(data.get("workspace_id") ?? "").trim(),
      workspace_name: String(data.get("workspace_name") ?? "").trim(),
      channel_id: String(data.get("channel_id") ?? "").trim(),
      channel_name: String(data.get("channel_name") ?? "").trim(),
      thread_id: String(data.get("thread_id") ?? "").trim(),
      thread_name: String(data.get("thread_name") ?? "").trim(),
      participation_mode: String(data.get("participation_mode")) as ParticipationMode,
      memory_scope: String(data.get("memory_scope")) as MemoryScope,
      version_label:
        String(data.get("version_label") ?? "Current").trim() || "Current",
      sticker_count: Number(data.get("sticker_count") ?? 0)
    };
    try {
      setWorking(true);
      setError(null);
      const saved = editingDeployment
        ? await deploymentApi.updateDeployment(editingDeployment.id, baseFields)
        : await deploymentApi.createDeployment({
            character_card_id: draftCharacterId,
            connection_id: draftConnectionId,
            ...baseFields,
            status: "paused"
          });

      const connection = connections.find(
        (item) => item.id === saved.connection_id
      );
      if (connection?.platform === "discord") {
        const mode = String(data.get("identity_mode") ?? "webhook") as DeploymentIdentityMode;
        const displayName =
          String(data.get("identity_display_name") ?? "").trim() ||
          saved.character_display_name;
        const avatarUrl = String(data.get("identity_avatar_url") ?? "").trim();
        await discordIdentityApi.update(saved.id, {
          mode,
          display_name: displayName,
          avatar_url: avatarUrl || null
        });
      }
      closeDeploymentForm();
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function toggleDeployment(item: CharacterDeployment) {
    try {
      setWorking(true);
      await deploymentApi.updateDeploymentStatus(
        item.id,
        item.status === "active" ? "paused" : "active"
      );
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeDeployment(item: CharacterDeployment) {
    const confirmed = window.confirm(
      zh
        ? `移除 ${item.character_display_name} 在 ${destination(item)} 的部署？`
        : `Remove ${item.character_display_name} from ${destination(item)}?`
    );
    if (!confirmed) return;
    try {
      setWorking(true);
      await discordIdentityApi.delete(item.id).catch(() => undefined);
      await deploymentApi.deleteDeployment(item.id);
      if (editingDeployment?.id === item.id) closeDeploymentForm();
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeConnection(item: PlatformConnection) {
    const confirmed = window.confirm(
      zh
        ? `删除连接“${item.display_name}”？其下所有部署记录也会被移除。`
        : `Delete “${item.display_name}”? All deployments using it will also be removed.`
    );
    if (!confirmed) return;
    try {
      setWorking(true);
      await deploymentApi.deleteConnection(item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  const formDeployment = editingDeployment;
  const formConnection = formDeployment
    ? connections.find((item) => item.id === formDeployment.connection_id)
    : selectedConnection;
  const discordIdentityEnabled = formConnection?.platform === "discord";

  return (
    <main className="deployment-page">
      <header className="deployment-header">
        <div>
          <p className="kicker">CHARACTER RELAY / DEPLOYMENT CENTER</p>
          <h1>{zh ? "角色部署与平台连接" : "Character deployments and platform connections"}</h1>
          <p>
            {zh
              ? "一张角色卡可以部署到多个 Server、Channel、Thread 或群组；现在可以直接编辑每个部署，并用 Webhook 显示角色自己的名称与头像。"
              : "Deploy one character to multiple destinations, edit each deployment directly, and use Discord webhooks for the character's own name and avatar."}
          </p>
        </div>
        <div className="deployment-header-actions">
          {!demoMode && (
            <button
              className="ink-button"
              onClick={openNewDeployment}
              disabled={!cards.length || !connections.length}
            >
              {zh ? "+ 新部署" : "+ New deployment"}
            </button>
          )}
          <button className="paper-button" onClick={onClose}>
            {zh ? "返回角色库" : "Back to library"}
          </button>
        </div>
      </header>

      <section className="deployment-summary-grid">
        <article className="paper-sheet deployment-summary-card">
          <span>{zh ? "部署总数" : "Deployments"}</span>
          <strong>{deployments.length}</strong>
          <small>{zh ? "每个 Channel / Thread 独立记录" : "One record per channel or thread"}</small>
        </article>
        <article className="paper-sheet deployment-summary-card">
          <span>{zh ? "运行中" : "Active"}</span>
          <strong>{counts.active}</strong>
          <small>{zh ? "Connector 正在读取的部署" : "Read by the connector"}</small>
        </article>
        <article className="paper-sheet deployment-summary-card">
          <span>{zh ? "已暂停" : "Paused"}</span>
          <strong>{counts.paused}</strong>
          <small>{zh ? "配置保留，不参与聊天" : "Configured but silent"}</small>
        </article>
        <article className="paper-sheet deployment-summary-card">
          <span>{zh ? "需要处理" : "Needs attention"}</span>
          <strong>{counts.attention}</strong>
          <small>{zh ? "离线或错误状态" : "Offline or error states"}</small>
        </article>
      </section>

      {error && <p className="error-note deployment-error" role="alert">{error}</p>}

      <section className="deployment-layout">
        <aside className="deployment-sidebar">
          <section className="paper-sheet connection-panel">
            <div className="panel-heading-row">
              <div>
                <p className="tape-label">CONNECTIONS</p>
                <h2>{zh ? "平台账户" : "Platform accounts"}</h2>
              </div>
              {!demoMode && (
                <button
                  className="paper-button"
                  onClick={() => setConnectionOpen((current) => !current)}
                >
                  {connectionOpen ? (zh ? "取消" : "Cancel") : (zh ? "+ 添加" : "+ Add")}
                </button>
              )}
            </div>

            {connectionOpen && !demoMode && (
              <form className="connection-form" onSubmit={createConnection}>
                <label>
                  {zh ? "平台" : "Platform"}
                  <select
                    value={connectionPlatform}
                    onChange={(event) =>
                      changeConnectionPlatform(event.currentTarget.value as PlatformId)
                    }
                  >
                    <option value="discord">Discord</option>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="telegram">Telegram</option>
                  </select>
                </label>
                <label>
                  {zh ? "连接名称" : "Connection name"}
                  <input
                    name="display_name"
                    required
                    placeholder={zh ? "例如：主要 Discord Bot" : "e.g. Main Discord Bot"}
                  />
                </label>
                <label>
                  {zh ? "运行方式" : "Run mode"}
                  <select
                    value={connectionMode}
                    onChange={(event) =>
                      setConnectionMode(event.currentTarget.value as ConnectionMode)
                    }
                  >
                    <option value="managed">{zh ? "云端托管" : "Managed cloud"}</option>
                    <option value="local">{zh ? "本地 Connector" : "Local connector"}</option>
                  </select>
                </label>
                <label>
                  {zh ? "外部账号 ID（可选）" : "External account ID (optional)"}
                  <input name="external_account_id" />
                </label>
                <p className="connection-note">
                  {zh
                    ? platformNotes[connectionPlatform].zh
                    : platformNotes[connectionPlatform].en}
                </p>
                <button className="ink-button" disabled={working}>
                  {working ? (zh ? "保存中…" : "Saving…") : (zh ? "保存连接" : "Save connection")}
                </button>
              </form>
            )}

            <div className="connection-list">
              {connections.map((item) => (
                <article className="connection-card" key={item.id}>
                  <div className={`platform-icon platform-${item.platform}`} aria-hidden="true">
                    {item.platform.slice(0, 1).toUpperCase()}
                  </div>
                  <div>
                    <strong>{item.display_name}</strong>
                    <span>{platformLabels[item.platform]} · {item.connection_mode}</span>
                    <small>{zh ? platformNotes[item.platform].zh : platformNotes[item.platform].en}</small>
                  </div>
                  <span className={`deployment-status status-${item.status}`}>
                    {statusLabel(item.status)}
                  </span>
                  {!demoMode && (
                    <button
                      className="text-button danger-text"
                      onClick={() => void removeConnection(item)}
                      disabled={working}
                    >
                      {zh ? "删除" : "Delete"}
                    </button>
                  )}
                </article>
              ))}
              {!loading && connections.length === 0 && (
                <div className="deployment-empty compact-empty">
                  <strong>{zh ? "还没有平台连接" : "No platform connections yet"}</strong>
                  <p>{zh ? "先添加平台连接，再建立部署。" : "Add a platform connection first."}</p>
                </div>
              )}
            </div>
          </section>
        </aside>

        <section className="deployment-main">
          {deploymentOpen && !demoMode && (
            <section className="paper-sheet deployment-form-sheet">
              <div className="panel-heading-row">
                <div>
                  <p className="tape-label">
                    {formDeployment ? "EDIT DEPLOYMENT" : "NEW DEPLOYMENT"}
                  </p>
                  <h2>
                    {formDeployment
                      ? zh
                        ? "编辑现有部署"
                        : "Edit deployment"
                      : zh
                        ? "将角色部署到一个聊天位置"
                        : "Deploy a character to one chat destination"}
                  </h2>
                </div>
                <button className="paper-button" onClick={closeDeploymentForm}>
                  {zh ? "关闭" : "Close"}
                </button>
              </div>
              <p className="deployment-foundation-note">
                {discordIdentityEnabled
                  ? zh
                    ? "Webhook 模式会由 Connector 自动查找或建立 Channel Webhook。你不需要手动填写 Webhook URL 或 Token。"
                    : "Webhook mode is provisioned automatically by the connector. Do not paste a webhook URL or token here."
                  : zh
                    ? "修改会保留当前部署状态，不需要先删除再重建。"
                    : "Edits preserve the current deployment status; deletion and recreation are no longer required."}
              </p>
              <form
                className="deployment-form"
                onSubmit={saveDeployment}
                key={formDeployment?.id ?? "new-deployment"}
              >
                <label>
                  {zh ? "角色" : "Character"}
                  <select
                    value={draftCharacterId}
                    onChange={(event) => setDraftCharacterId(event.currentTarget.value)}
                    disabled={Boolean(formDeployment)}
                    required
                  >
                    {cards.map((card) => (
                      <option value={card.id} key={card.id}>{card.display_name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  {zh ? "平台连接" : "Platform connection"}
                  <select
                    value={draftConnectionId}
                    onChange={(event) => setDraftConnectionId(event.currentTarget.value)}
                    disabled={Boolean(formDeployment)}
                    required
                  >
                    {connections.map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.display_name} · {platformLabels[item.platform]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {zh ? "Server / Workspace 名称" : "Server / workspace name"}
                  <input name="workspace_name" defaultValue={formDeployment?.workspace_name ?? ""} />
                </label>
                <label>
                  {zh ? "Server / Workspace ID" : "Server / workspace ID"}
                  <input name="workspace_id" defaultValue={formDeployment?.workspace_id ?? ""} />
                </label>
                <label>
                  {zh ? "Channel / Group 名称" : "Channel / group name"}
                  <input
                    name="channel_name"
                    required
                    defaultValue={formDeployment?.channel_name ?? ""}
                    placeholder="#ann-room"
                  />
                </label>
                <label>
                  {zh ? "Channel / Group ID" : "Channel / group ID"}
                  <input
                    name="channel_id"
                    required
                    defaultValue={formDeployment?.channel_id ?? ""}
                  />
                </label>
                <label>
                  {zh ? "Thread 名称（可选）" : "Thread name (optional)"}
                  <input name="thread_name" defaultValue={formDeployment?.thread_name ?? ""} />
                </label>
                <label>
                  {zh ? "Thread ID（可选）" : "Thread ID (optional)"}
                  <input name="thread_id" defaultValue={formDeployment?.thread_id ?? ""} />
                </label>
                <label>
                  {zh ? "参与模式" : "Participation mode"}
                  <select
                    name="participation_mode"
                    defaultValue={formDeployment?.participation_mode ?? "mention_and_reply"}
                  >
                    <option value="mention_only">Mention only</option>
                    <option value="reply_only">Reply only</option>
                    <option value="mention_and_reply">Mention + reply</option>
                    <option value="smart">Smart participation</option>
                  </select>
                </label>
                <label>
                  {zh ? "记忆范围" : "Memory scope"}
                  <select
                    name="memory_scope"
                    defaultValue={formDeployment?.memory_scope ?? "channel_isolated"}
                  >
                    <option value="channel_isolated">Channel isolated</option>
                    <option value="server_shared">Server shared</option>
                    <option value="custom">Custom</option>
                  </select>
                </label>
                <label>
                  {zh ? "角色版本" : "Character version"}
                  <input name="version_label" defaultValue={formDeployment?.version_label ?? "Current"} />
                </label>
                <label>
                  {zh ? "已配置贴图数量" : "Configured stickers"}
                  <input
                    name="sticker_count"
                    type="number"
                    min="0"
                    max="500"
                    defaultValue={formDeployment?.sticker_count ?? 0}
                  />
                </label>

                {discordIdentityEnabled && (
                  <>
                    <div className="deployment-form-divider">
                      <strong>{zh ? "Discord 消息身份" : "Discord message identity"}</strong>
                      <span>{zh ? "名称和头像由 Webhook 每条消息动态覆盖" : "Name and avatar are overridden per webhook message"}</span>
                    </div>
                    <label>
                      {zh ? "发送方式" : "Delivery identity"}
                      <select name="identity_mode" defaultValue={formIdentity?.mode ?? "webhook"}>
                        <option value="webhook">{zh ? "角色 Webhook 身份" : "Character webhook identity"}</option>
                        <option value="bot">{zh ? "共用 Bot 身份" : "Shared Bot identity"}</option>
                      </select>
                    </label>
                    <label>
                      {zh ? "显示名称" : "Display name"}
                      <input
                        name="identity_display_name"
                        maxLength={80}
                        defaultValue={
                          formIdentity?.display_name ??
                          cards.find((card) => card.id === draftCharacterId)?.display_name ??
                          "Character"
                        }
                      />
                    </label>
                    <label className="deployment-form-wide">
                      {zh ? "头像公开 URL（可选）" : "Public avatar URL (optional)"}
                      <input
                        name="identity_avatar_url"
                        type="url"
                        defaultValue={formIdentity?.avatar_url ?? ""}
                        placeholder="https://.../ann-avatar.png"
                      />
                      <small>
                        {zh
                          ? "Discord 必须能公开读取该图片。留空时使用 Webhook 默认头像。"
                          : "Discord must be able to fetch this image publicly. Blank uses the webhook default."}
                      </small>
                    </label>
                  </>
                )}

                <button
                  className="ink-button deployment-submit"
                  disabled={working || !draftCharacterId || !draftConnectionId}
                >
                  {working
                    ? zh
                      ? "保存中…"
                      : "Saving…"
                    : formDeployment
                      ? zh
                        ? "保存部署修改"
                        : "Save deployment changes"
                      : zh
                        ? "建立暂停状态的部署"
                        : "Create paused deployment"}
                </button>
              </form>
            </section>
          )}

          <section className="paper-sheet deployment-list-sheet">
            <div className="panel-heading-row deployment-list-heading">
              <div>
                <p className="tape-label">DEPLOYMENT LIST</p>
                <h2>{zh ? "目前部署到哪些位置" : "Where characters are deployed"}</h2>
              </div>
              <span>{filtered.length} / {deployments.length}</span>
            </div>

            <div className="deployment-filters">
              <label>
                {zh ? "角色" : "Character"}
                <select
                  value={characterFilter}
                  onChange={(event) => setCharacterFilter(event.currentTarget.value)}
                >
                  <option value="all">{zh ? "全部角色" : "All characters"}</option>
                  {cards.map((card) => (
                    <option value={card.id} key={card.id}>{card.display_name}</option>
                  ))}
                </select>
              </label>
              <label>
                {zh ? "平台" : "Platform"}
                <select
                  value={platformFilter}
                  onChange={(event) =>
                    setPlatformFilter(event.currentTarget.value as "all" | PlatformId)
                  }
                >
                  <option value="all">{zh ? "全部平台" : "All platforms"}</option>
                  <option value="discord">Discord</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                </select>
              </label>
              <label>
                {zh ? "状态" : "Status"}
                <select
                  value={statusFilter}
                  onChange={(event) =>
                    setStatusFilter(event.currentTarget.value as "all" | DeploymentStatus)
                  }
                >
                  <option value="all">{zh ? "全部状态" : "All statuses"}</option>
                  <option value="active">Active</option>
                  <option value="paused">Paused</option>
                  <option value="offline">Offline</option>
                  <option value="error">Error</option>
                  <option value="disconnected">Disconnected</option>
                </select>
              </label>
            </div>

            {loading ? (
              <div className="deployment-empty">
                <strong>{zh ? "正在读取部署…" : "Loading deployments…"}</strong>
              </div>
            ) : filtered.length === 0 ? (
              <div className="deployment-empty">
                <strong>
                  {deployments.length
                    ? zh
                      ? "没有符合筛选条件的部署"
                      : "No deployments match the filters"
                    : zh
                      ? "还没有角色部署"
                      : "No character deployments yet"}
                </strong>
                <p>{zh ? "每个 Channel、Thread 或群组会成为一条独立记录。" : "Each destination appears as an independent record."}</p>
              </div>
            ) : (
              <div className="deployment-table" role="table">
                <div className="deployment-row deployment-row-head" role="row">
                  <span>{zh ? "角色 / 版本" : "Character / version"}</span>
                  <span>{zh ? "平台位置" : "Platform destination"}</span>
                  <span>{zh ? "行为 / 身份" : "Behavior / identity"}</span>
                  <span>{zh ? "状态" : "Status"}</span>
                  <span>{zh ? "操作" : "Actions"}</span>
                </div>
                {filtered.map((item) => {
                  const identity = identityMap.get(item.id) ?? defaultIdentity(item);
                  return (
                    <article className="deployment-row" role="row" key={item.id}>
                      <div>
                        <strong>{item.character_display_name}</strong>
                        <span>{item.version_label}</span>
                      </div>
                      <div>
                        <strong>{platformLabels[item.platform]}</strong>
                        <span>{destination(item)}</span>
                      </div>
                      <div>
                        <strong>{item.participation_mode.replaceAll("_", " ")}</strong>
                        <span>
                          {item.memory_scope.replaceAll("_", " ")} · {item.sticker_count} {zh ? "贴图" : "stickers"}
                        </span>
                        {item.platform === "discord" && (
                          <span className="deployment-identity-line">
                            {identity.mode === "webhook" ? "Webhook" : "Bot"} · {identity.display_name} · {statusLabel(identity.webhook_status)}
                          </span>
                        )}
                        {identity.last_error && (
                          <small className="deployment-inline-error">{identity.last_error}</small>
                        )}
                      </div>
                      <div>
                        <span className={`deployment-status status-${item.status}`}>
                          {statusLabel(item.status)}
                        </span>
                        {item.last_error && (
                          <small className="deployment-inline-error">{item.last_error}</small>
                        )}
                      </div>
                      <div className="deployment-actions">
                        {!demoMode && (
                          <>
                            <button
                              className="paper-button"
                              onClick={() => openEditDeployment(item)}
                              disabled={working}
                            >
                              {zh ? "编辑" : "Edit"}
                            </button>
                            <button
                              className="paper-button"
                              onClick={() => void toggleDeployment(item)}
                              disabled={
                                working ||
                                item.status === "offline" ||
                                item.status === "disconnected"
                              }
                            >
                              {item.status === "active"
                                ? zh
                                  ? "暂停"
                                  : "Pause"
                                : zh
                                  ? "启用"
                                  : "Activate"}
                            </button>
                            <button
                              className="text-button danger-text"
                              onClick={() => void removeDeployment(item)}
                              disabled={working}
                            >
                              {zh ? "移除" : "Remove"}
                            </button>
                          </>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}
