import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CharacterCard } from "./api";
import {
  deploymentApi,
  type CharacterDeployment,
  type ConnectionMode,
  type DeploymentStatus,
  type PlatformConnection,
  type PlatformId
} from "./deploymentApi";
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
    en: "Managed Bot connector. Designed to run continuously on Railway.",
    zh: "托管式 Bot Connector，适合持续运行在 Railway。"
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

function statusLabel(status: DeploymentStatus | PlatformConnection["status"]): string {
  return status.replaceAll("_", " ");
}

function destination(deployment: CharacterDeployment): string {
  const workspace = deployment.workspace_name || platformLabels[deployment.platform];
  const channel = deployment.channel_name || deployment.channel_id;
  return deployment.thread_name
    ? `${workspace} / ${channel} / ${deployment.thread_name}`
    : `${workspace} / ${channel}`;
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
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [deploymentOpen, setDeploymentOpen] = useState(Boolean(initialCharacterId));
  const [platformFilter, setPlatformFilter] = useState<"all" | PlatformId>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | DeploymentStatus>("all");
  const [characterFilter, setCharacterFilter] = useState(initialCharacterId ?? "all");
  const [draftCharacterId, setDraftCharacterId] = useState(initialCharacterId ?? cards[0]?.id ?? "");
  const [draftConnectionId, setDraftConnectionId] = useState("");
  const [connectionPlatform, setConnectionPlatform] = useState<PlatformId>("discord");
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("managed");

  async function load() {
    try {
      setLoading(true);
      const [nextConnections, nextDeployments] = await Promise.all([
        deploymentApi.listConnections(),
        deploymentApi.listDeployments()
      ]);
      setConnections(nextConnections);
      setDeployments(nextDeployments);
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
      attention: deployments.filter((item) => item.status === "error" || item.status === "offline").length
    }),
    [deployments]
  );

  function changeConnectionPlatform(platform: PlatformId) {
    setConnectionPlatform(platform);
    setConnectionMode(platform === "whatsapp" ? "local" : "managed");
  }

  async function createConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
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
          product_stage: "foundation"
        }
      });
      event.currentTarget.reset();
      setConnectionOpen(false);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function createDeployment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      setWorking(true);
      setError(null);
      await deploymentApi.createDeployment({
        character_card_id: draftCharacterId,
        connection_id: draftConnectionId,
        workspace_id: String(data.get("workspace_id") ?? "").trim(),
        workspace_name: String(data.get("workspace_name") ?? "").trim(),
        channel_id: String(data.get("channel_id") ?? "").trim(),
        channel_name: String(data.get("channel_name") ?? "").trim(),
        thread_id: String(data.get("thread_id") ?? "").trim(),
        thread_name: String(data.get("thread_name") ?? "").trim(),
        participation_mode: String(data.get("participation_mode")) as
          | "mention_only"
          | "reply_only"
          | "mention_and_reply"
          | "smart",
        memory_scope: String(data.get("memory_scope")) as
          | "channel_isolated"
          | "server_shared"
          | "custom",
        version_label: String(data.get("version_label") ?? "Current").trim() || "Current",
        sticker_count: Number(data.get("sticker_count") ?? 0),
        status: "paused"
      });
      event.currentTarget.reset();
      setDeploymentOpen(false);
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
      await deploymentApi.deleteDeployment(item.id);
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

  return (
    <main className="deployment-page">
      <header className="deployment-header">
        <div>
          <p className="kicker">CHARACTER RELAY / DEPLOYMENT CENTER</p>
          <h1>{zh ? "角色部署与平台连接" : "Character deployments and platform connections"}</h1>
          <p>
            {zh
              ? "一张角色卡可以部署到多个 Server、Channel、Thread 或群组；每个目的地都是可独立管理的部署实例。"
              : "Deploy one character to multiple servers, channels, threads, or groups. Every destination remains independently manageable."}
          </p>
        </div>
        <div className="deployment-header-actions">
          {!demoMode && (
            <button className="ink-button" onClick={() => setDeploymentOpen(true)} disabled={!cards.length || !connections.length}>
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
          <small>{zh ? "Connector 就绪后可接收消息" : "Ready to receive connector events"}</small>
        </article>
        <article className="paper-sheet deployment-summary-card">
          <span>{zh ? "已暂停" : "Paused"}</span>
          <strong>{counts.paused}</strong>
          <small>{zh ? "配置保留，不参与聊天" : "Configured but not participating"}</small>
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
                <button className="paper-button" onClick={() => setConnectionOpen((current) => !current)}>
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
                    onChange={(event) => changeConnectionPlatform(event.currentTarget.value as PlatformId)}
                  >
                    <option value="discord">Discord</option>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="telegram">Telegram</option>
                  </select>
                </label>
                <label>
                  {zh ? "连接名称" : "Connection name"}
                  <input name="display_name" required placeholder={zh ? "例如：主要 Discord Bot" : "e.g. Main Discord Bot"} />
                </label>
                <label>
                  {zh ? "运行方式" : "Run mode"}
                  <select value={connectionMode} onChange={(event) => setConnectionMode(event.currentTarget.value as ConnectionMode)}>
                    <option value="managed">{zh ? "云端托管" : "Managed cloud"}</option>
                    <option value="local">{zh ? "本地 Connector" : "Local connector"}</option>
                  </select>
                </label>
                <label>
                  {zh ? "外部账号 ID（可选）" : "External account ID (optional)"}
                  <input name="external_account_id" placeholder={zh ? "Bot ID、电话号码标签等" : "Bot ID, phone label, etc."} />
                </label>
                <p className="connection-note">
                  {zh ? platformNotes[connectionPlatform].zh : platformNotes[connectionPlatform].en}
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
                  <span className={`deployment-status status-${item.status}`}>{statusLabel(item.status)}</span>
                  {!demoMode && (
                    <button className="text-button danger-text" onClick={() => void removeConnection(item)} disabled={working}>
                      {zh ? "删除" : "Delete"}
                    </button>
                  )}
                </article>
              ))}
              {!loading && connections.length === 0 && (
                <div className="deployment-empty compact-empty">
                  <strong>{zh ? "还没有平台连接" : "No platform connections yet"}</strong>
                  <p>{zh ? "先添加 Discord、WhatsApp 或 Telegram 连接，再建立部署。" : "Add Discord, WhatsApp, or Telegram before creating a deployment."}</p>
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
                  <p className="tape-label">NEW DEPLOYMENT</p>
                  <h2>{zh ? "将角色部署到一个聊天位置" : "Deploy a character to one chat destination"}</h2>
                </div>
                <button className="paper-button" onClick={() => setDeploymentOpen(false)}>
                  {zh ? "关闭" : "Close"}
                </button>
              </div>
              <p className="deployment-foundation-note">
                {zh
                  ? "当前版本保存部署配置与状态。Discord OAuth、WhatsApp QR 配对和 Telegram Bot Token 会由后续 Connector 阶段接管这些手动字段。"
                  : "This release persists deployment configuration and status. Later connector phases will replace manual IDs with Discord OAuth, WhatsApp QR pairing, and Telegram Bot setup."}
              </p>
              <form className="deployment-form" onSubmit={createDeployment}>
                <label>
                  {zh ? "角色" : "Character"}
                  <select value={draftCharacterId} onChange={(event) => setDraftCharacterId(event.currentTarget.value)} required>
                    {cards.map((card) => <option value={card.id} key={card.id}>{card.display_name}</option>)}
                  </select>
                </label>
                <label>
                  {zh ? "平台连接" : "Platform connection"}
                  <select value={draftConnectionId} onChange={(event) => setDraftConnectionId(event.currentTarget.value)} required>
                    {connections.map((item) => <option value={item.id} key={item.id}>{item.display_name} · {platformLabels[item.platform]}</option>)}
                  </select>
                </label>
                <label>
                  {zh ? "Server / Workspace 名称" : "Server / workspace name"}
                  <input name="workspace_name" placeholder={zh ? "例如：Juen Test Server" : "e.g. Juen Test Server"} />
                </label>
                <label>
                  {zh ? "Server / Workspace ID" : "Server / workspace ID"}
                  <input name="workspace_id" placeholder="123456789" />
                </label>
                <label>
                  {zh ? "Channel / Group 名称" : "Channel / group name"}
                  <input name="channel_name" required placeholder={zh ? "例如：#ann-room" : "e.g. #ann-room"} />
                </label>
                <label>
                  {zh ? "Channel / Group ID" : "Channel / group ID"}
                  <input name="channel_id" required placeholder="987654321" />
                </label>
                <label>
                  {zh ? "Thread 名称（可选）" : "Thread name (optional)"}
                  <input name="thread_name" />
                </label>
                <label>
                  {zh ? "Thread ID（可选）" : "Thread ID (optional)"}
                  <input name="thread_id" />
                </label>
                <label>
                  {zh ? "参与模式" : "Participation mode"}
                  <select name="participation_mode" defaultValue="mention_and_reply">
                    <option value="mention_only">Mention only</option>
                    <option value="reply_only">Reply only</option>
                    <option value="mention_and_reply">Mention + reply</option>
                    <option value="smart">Smart participation</option>
                  </select>
                </label>
                <label>
                  {zh ? "记忆范围" : "Memory scope"}
                  <select name="memory_scope" defaultValue="channel_isolated">
                    <option value="channel_isolated">Channel isolated</option>
                    <option value="server_shared">Server shared</option>
                    <option value="custom">Custom</option>
                  </select>
                </label>
                <label>
                  {zh ? "角色版本" : "Character version"}
                  <input name="version_label" defaultValue="Current" />
                </label>
                <label>
                  {zh ? "已配置贴图数量" : "Configured stickers"}
                  <input name="sticker_count" type="number" min="0" max="500" defaultValue="0" />
                </label>
                <button className="ink-button deployment-submit" disabled={working || !draftCharacterId || !draftConnectionId}>
                  {working ? (zh ? "建立中…" : "Creating…") : (zh ? "建立暂停状态的部署" : "Create paused deployment")}
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
                <select value={characterFilter} onChange={(event) => setCharacterFilter(event.currentTarget.value)}>
                  <option value="all">{zh ? "全部角色" : "All characters"}</option>
                  {cards.map((card) => <option value={card.id} key={card.id}>{card.display_name}</option>)}
                </select>
              </label>
              <label>
                {zh ? "平台" : "Platform"}
                <select value={platformFilter} onChange={(event) => setPlatformFilter(event.currentTarget.value as "all" | PlatformId)}>
                  <option value="all">{zh ? "全部平台" : "All platforms"}</option>
                  <option value="discord">Discord</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                </select>
              </label>
              <label>
                {zh ? "状态" : "Status"}
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.currentTarget.value as "all" | DeploymentStatus)}>
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
              <div className="deployment-empty"><strong>{zh ? "正在读取部署…" : "Loading deployments…"}</strong></div>
            ) : filtered.length === 0 ? (
              <div className="deployment-empty">
                <strong>{deployments.length ? (zh ? "没有符合筛选条件的部署" : "No deployments match the filters") : (zh ? "还没有角色部署" : "No character deployments yet")}</strong>
                <p>{zh ? "每个 Channel、Thread 或群组会成为一条独立记录。" : "Each channel, thread, or group will appear as an independent record."}</p>
              </div>
            ) : (
              <div className="deployment-table" role="table" aria-label={zh ? "角色部署列表" : "Character deployments"}>
                <div className="deployment-row deployment-row-head" role="row">
                  <span>{zh ? "角色 / 版本" : "Character / version"}</span>
                  <span>{zh ? "平台位置" : "Platform destination"}</span>
                  <span>{zh ? "行为配置" : "Behavior"}</span>
                  <span>{zh ? "状态" : "Status"}</span>
                  <span>{zh ? "操作" : "Actions"}</span>
                </div>
                {filtered.map((item) => (
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
                      <span>{item.memory_scope.replaceAll("_", " ")} · {item.sticker_count} {zh ? "贴图" : "stickers"}</span>
                    </div>
                    <div>
                      <span className={`deployment-status status-${item.status}`}>{statusLabel(item.status)}</span>
                      {item.last_error && <small className="deployment-inline-error">{item.last_error}</small>}
                    </div>
                    <div className="deployment-actions">
                      {!demoMode && (
                        <>
                          <button className="paper-button" onClick={() => void toggleDeployment(item)} disabled={working || item.status === "offline" || item.status === "disconnected"}>
                            {item.status === "active" ? (zh ? "暂停" : "Pause") : (zh ? "启用" : "Activate")}
                          </button>
                          <button className="text-button danger-text" onClick={() => void removeDeployment(item)} disabled={working}>
                            {zh ? "移除" : "Remove"}
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}
