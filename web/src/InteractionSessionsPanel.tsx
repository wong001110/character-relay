import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  deploymentApi,
  type CharacterDeployment,
  type DiscordServerCatalog,
  type PlatformConnection
} from "./deploymentApi";
import {
  interactionApi,
  type InteractionIntensity,
  type InteractionSession,
  type InteractionStatus,
  type StickerSemantic
} from "./interactionApi";

interface Props {
  demoMode: boolean;
  zh: boolean;
}

function discordUserId(value: string): string {
  return value.trim().replaceAll(/[<@!>]/gu, "");
}

function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}

export function InteractionSessionsPanel({ demoMode, zh }: Props) {
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [catalog, setCatalog] = useState<DiscordServerCatalog[]>([]);
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [sessions, setSessions] = useState<InteractionSession[]>([]);
  const [stickers, setStickers] = useState<StickerSemantic[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionFormOpen, setSessionFormOpen] = useState(false);
  const [stickerFormOpen, setStickerFormOpen] = useState(false);
  const [editingSticker, setEditingSticker] = useState<StickerSemantic | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [guildId, setGuildId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [firstDeploymentId, setFirstDeploymentId] = useState("");
  const [secondDeploymentId, setSecondDeploymentId] = useState("");
  const [intensity, setIntensity] = useState<InteractionIntensity>("playful");

  async function load() {
    try {
      setLoading(true);
      const [nextConnections, nextCatalog, nextDeployments, nextSessions, nextStickers] =
        await Promise.all([
          deploymentApi.listConnections(),
          deploymentApi.listDiscordServerCatalog(),
          deploymentApi.listDeployments(),
          interactionApi.listSessions(),
          interactionApi.listStickers()
        ]);
      const discordConnections = nextConnections.filter((item) => item.platform === "discord");
      setConnections(discordConnections);
      setCatalog(nextCatalog);
      setDeployments(nextDeployments);
      setSessions(nextSessions);
      setStickers(nextStickers);
      setConnectionId((current) => current || discordConnections[0]?.id || "");
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

  const servers = catalog.filter((item) => item.connection_id === connectionId);
  const selectedServer = servers.find((item) => item.guild_id === guildId) ?? servers[0];
  const channels = selectedServer?.channels ?? [];
  const selectedChannel = channels.find((item) => item.id === channelId) ?? channels[0];
  const eligibleDeployments = useMemo(
    () =>
      deployments.filter(
        (item) =>
          item.platform === "discord" &&
          item.status === "active" &&
          item.connection_id === connectionId &&
          (!selectedServer || item.workspace_id === selectedServer.guild_id)
      ),
    [connectionId, deployments, selectedServer]
  );

  useEffect(() => {
    if (selectedServer && selectedServer.guild_id !== guildId) {
      setGuildId(selectedServer.guild_id);
    }
    if (selectedChannel && selectedChannel.id !== channelId) {
      setChannelId(selectedChannel.id);
    }
    if (!eligibleDeployments.some((item) => item.id === firstDeploymentId)) {
      setFirstDeploymentId(eligibleDeployments[0]?.id ?? "");
    }
    if (
      !eligibleDeployments.some(
        (item) => item.id === secondDeploymentId && item.id !== firstDeploymentId
      )
    ) {
      setSecondDeploymentId(
        eligibleDeployments.find((item) => item.id !== firstDeploymentId)?.id ?? ""
      );
    }
  }, [
    channelId,
    eligibleDeployments,
    firstDeploymentId,
    guildId,
    secondDeploymentId,
    selectedChannel,
    selectedServer
  ]);

  async function createSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const targetUserId = discordUserId(String(data.get("target_user_id") ?? ""));
    if (!selectedServer || !selectedChannel || !targetUserId) return;
    try {
      setWorking(true);
      await interactionApi.createSession({
        connection_id: connectionId,
        guild_id: selectedServer.guild_id,
        guild_name: selectedServer.guild_name,
        channel_id: selectedChannel.id,
        channel_name: selectedChannel.name,
        category_id: selectedChannel.category_id,
        target_user_id: targetUserId,
        target_display_name: String(data.get("target_display_name") ?? "").trim(),
        participant_deployment_ids: [firstDeploymentId, secondDeploymentId],
        rounds_per_trigger: Number(data.get("rounds_per_trigger") ?? 1),
        maximum_triggers: Number(data.get("maximum_triggers") ?? 1),
        cooldown_seconds: Number(data.get("cooldown_seconds") ?? 60),
        duration_seconds: Number(data.get("duration_minutes") ?? 10) * 60,
        intensity,
        status: String(data.get("status")) === "active" ? "active" : "paused"
      });
      setSessionFormOpen(false);
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
    if (!window.confirm(zh ? "删除这个 Interaction Session？" : "Delete this Interaction Session?")) {
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

  function openStickerForm(item: StickerSemantic | null = null) {
    setEditingSticker(item);
    if (item) {
      setConnectionId(item.connection_id);
      setGuildId(item.guild_id);
    }
    setStickerFormOpen(true);
  }

  async function saveSticker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const stickerGuildId = String(data.get("guild_id") ?? guildId).trim();
    try {
      setWorking(true);
      await interactionApi.saveSticker({
        connection_id: String(data.get("connection_id") ?? connectionId),
        guild_id: stickerGuildId,
        sticker_id: String(data.get("sticker_id") ?? "").trim(),
        name: String(data.get("name") ?? "Sticker").trim(),
        description: String(data.get("description") ?? "").trim(),
        tags: String(data.get("tags") ?? "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        format_type: String(data.get("format_type") ?? "unknown").trim(),
        asset_url: String(data.get("asset_url") ?? "").trim(),
        semantic_intent:
          String(data.get("semantic_intent") ?? "sticker_reaction").trim() ||
          "sticker_reaction",
        semantic_emotion: String(data.get("semantic_emotion") ?? "").trim(),
        semantic_description: String(data.get("semantic_description") ?? "").trim()
      });
      setStickerFormOpen(false);
      setEditingSticker(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeSticker(item: StickerSemantic) {
    if (!window.confirm(zh ? "删除这个 Sticker 语义？" : "Delete this Sticker meaning?")) return;
    try {
      setWorking(true);
      await interactionApi.deleteSticker(item.id);
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
        <div className="panel-heading-row">
          <div>
            <p className="tape-label">INTERACTION SESSIONS</p>
            <h2>{zh ? "可控的多角色互动" : "Controlled multi-character interactions"}</h2>
            <p>
              {zh
                ? "Roast Session 只在指定 Channel、指定用户与固定轮次内运行。每一轮代表两个角色各回复一次。"
                : "Roast Sessions run only for one target member in one channel. Each round gives both characters one turn."}
            </p>
          </div>
          {!demoMode && (
            <button className="ink-button" onClick={() => setSessionFormOpen((value) => !value)}>
              {sessionFormOpen ? (zh ? "关闭" : "Close") : zh ? "+ 新 Session" : "+ New session"}
            </button>
          )}
        </div>

        {sessionFormOpen && !demoMode && (
          <form className="interaction-form" onSubmit={createSession}>
            <label>
              {zh ? "Discord Connector" : "Discord connector"}
              <select value={connectionId} onChange={(event) => setConnectionId(event.currentTarget.value)}>
                {connections.map((item) => (
                  <option value={item.id} key={item.id}>{item.display_name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "Server" : "Server"}
              <select value={selectedServer?.guild_id ?? ""} onChange={(event) => setGuildId(event.currentTarget.value)}>
                {servers.map((item) => (
                  <option value={item.guild_id} key={item.guild_id}>{item.guild_name}</option>
                ))}
              </select>
            </label>
            <label>
              Channel
              <select value={selectedChannel?.id ?? ""} onChange={(event) => setChannelId(event.currentTarget.value)}>
                {channels.map((item) => (
                  <option value={item.id} key={item.id}>#{item.name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "目标用户 ID 或 Mention" : "Target user ID or mention"}
              <input name="target_user_id" required placeholder="<@606232885489303603>" />
            </label>
            <label>
              {zh ? "目标显示名称" : "Target display name"}
              <input name="target_display_name" placeholder="501 Not Implemented" />
            </label>
            <label>
              {zh ? "第一位角色" : "First character"}
              <select value={firstDeploymentId} onChange={(event) => setFirstDeploymentId(event.currentTarget.value)}>
                {eligibleDeployments.map((item) => (
                  <option value={item.id} key={item.id}>{item.character_display_name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "第二位角色" : "Second character"}
              <select value={secondDeploymentId} onChange={(event) => setSecondDeploymentId(event.currentTarget.value)}>
                {eligibleDeployments.filter((item) => item.id !== firstDeploymentId).map((item) => (
                  <option value={item.id} key={item.id}>{item.character_display_name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "每次触发轮数" : "Rounds per trigger"}
              <input name="rounds_per_trigger" type="number" min="1" max="3" defaultValue="1" />
            </label>
            <label>
              {zh ? "最多触发次数" : "Maximum triggers"}
              <input name="maximum_triggers" type="number" min="1" max="5" defaultValue="1" />
            </label>
            <label>
              {zh ? "冷却秒数" : "Cooldown seconds"}
              <input name="cooldown_seconds" type="number" min="0" max="3600" defaultValue="60" />
            </label>
            <label>
              {zh ? "持续分钟" : "Duration minutes"}
              <input name="duration_minutes" type="number" min="1" max="1440" defaultValue="10" />
            </label>
            <label>
              {zh ? "强度" : "Intensity"}
              <select value={intensity} onChange={(event) => setIntensity(event.currentTarget.value as InteractionIntensity)}>
                <option value="light">Light</option>
                <option value="playful">Playful</option>
                <option value="sharp">Sharp</option>
              </select>
            </label>
            <label>
              {zh ? "建立后状态" : "Initial status"}
              <select name="status" defaultValue="paused">
                <option value="paused">Paused</option>
                <option value="active">Active</option>
              </select>
            </label>
            <div className="interaction-form-summary">
              <strong>{zh ? "固定顺序" : "Fixed order"}</strong>
              <span>
                {eligibleDeployments.find((item) => item.id === firstDeploymentId)?.character_display_name || "—"}
                {" → "}
                {eligibleDeployments.find((item) => item.id === secondDeploymentId)?.character_display_name || "—"}
              </span>
              <small>{zh ? "1 轮 = 两个角色各回复一次。" : "One round means one reply from each character."}</small>
            </div>
            <button className="ink-button" disabled={working || !firstDeploymentId || !secondDeploymentId}>
              {working ? (zh ? "保存中…" : "Saving…") : zh ? "建立 Roast Session" : "Create Roast Session"}
            </button>
          </form>
        )}

        {loading ? (
          <p>{zh ? "读取 Session…" : "Loading sessions…"}</p>
        ) : (
          <div className="interaction-card-grid">
            {sessions.map((item) => (
              <article className="interaction-card" key={item.id}>
                <div className="interaction-card-heading">
                  <strong>Roast Session</strong>
                  <span className={`deployment-status status-${item.status}`}>{item.status}</span>
                </div>
                <p><b>{zh ? "目标" : "Target"}:</b> {item.target_display_name || item.target_user_id}</p>
                <p><b>{zh ? "角色" : "Characters"}:</b> {item.participant_names.join(" → ")}</p>
                <p><b>{zh ? "位置" : "Location"}:</b> {item.guild_name} / #{item.channel_name}</p>
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
            {!sessions.length && <p>{zh ? "还没有 Interaction Session。" : "No Interaction Sessions yet."}</p>}
          </div>
        )}
      </section>

      <section className="paper-sheet interaction-panel">
        <div className="panel-heading-row">
          <div>
            <p className="tape-label">STICKER DICTIONARY</p>
            <h2>{zh ? "让角色理解用户发送的 Sticker" : "Teach characters what Discord Stickers mean"}</h2>
            <p>
              {zh
                ? "Connector 会自动记录见过的 Sticker。人工定义优先于名称、description 与 tags 推断。"
                : "The connector records observed Stickers automatically. Manual meanings override Discord metadata."}
            </p>
          </div>
          {!demoMode && (
            <button className="ink-button" onClick={() => stickerFormOpen ? setStickerFormOpen(false) : openStickerForm()}>
              {stickerFormOpen ? (zh ? "关闭" : "Close") : zh ? "+ 添加含义" : "+ Add meaning"}
            </button>
          )}
        </div>

        {stickerFormOpen && !demoMode && (
          <form className="interaction-form sticker-form" onSubmit={saveSticker} key={editingSticker?.id ?? "new-sticker"}>
            <label>
              Connector
              <select name="connection_id" defaultValue={editingSticker?.connection_id ?? connectionId}>
                {connections.map((item) => <option value={item.id} key={item.id}>{item.display_name}</option>)}
              </select>
            </label>
            <label>
              Server ID
              <input name="guild_id" required defaultValue={editingSticker?.guild_id ?? selectedServer?.guild_id ?? ""} />
            </label>
            <label>
              Sticker ID
              <input name="sticker_id" required readOnly={Boolean(editingSticker)} defaultValue={editingSticker?.sticker_id ?? ""} />
            </label>
            <label>
              Name
              <input name="name" required defaultValue={editingSticker?.name ?? ""} />
            </label>
            <label>
              Discord description
              <input name="description" defaultValue={editingSticker?.description ?? ""} />
            </label>
            <label>
              Discord tags
              <input name="tags" defaultValue={editingSticker?.tags.join(", ") ?? ""} />
            </label>
            <label>
              Intent
              <input name="semantic_intent" defaultValue={editingSticker?.semantic_intent ?? "sticker_reaction"} />
            </label>
            <label>
              Emotion
              <input name="semantic_emotion" defaultValue={editingSticker?.semantic_emotion ?? ""} placeholder="amused / shy / annoyed" />
            </label>
            <label className="interaction-form-wide">
              {zh ? "角色应理解的含义" : "Meaning supplied to characters"}
              <textarea name="semantic_description" required rows={3} defaultValue={editingSticker?.semantic_description ?? ""} />
            </label>
            <input type="hidden" name="format_type" value={editingSticker?.format_type ?? "unknown"} />
            <input type="hidden" name="asset_url" value={editingSticker?.asset_url ?? ""} />
            <button className="ink-button" disabled={working}>{working ? (zh ? "保存中…" : "Saving…") : zh ? "保存 Sticker 含义" : "Save Sticker meaning"}</button>
          </form>
        )}

        <div className="sticker-table">
          {stickers.map((item) => (
            <article className="sticker-row" key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <span>ID: {item.sticker_id}</span>
              </div>
              <div>
                <strong>{item.semantic_intent || "sticker_reaction"}</strong>
                <span>{item.semantic_emotion || "—"}</span>
              </div>
              <p>{item.semantic_description}</p>
              <div>
                <span className={`sticker-source source-${item.semantic_source}`}>{item.semantic_source}</span>
                <small>{Math.round(item.semantic_confidence * 100)}%</small>
              </div>
              {!demoMode && (
                <div className="interaction-actions">
                  <button className="paper-button" onClick={() => openStickerForm(item)}>{zh ? "编辑" : "Edit"}</button>
                  <button className="text-button danger-text" onClick={() => void removeSticker(item)}>{zh ? "删除" : "Delete"}</button>
                </div>
              )}
            </article>
          ))}
          {!loading && !stickers.length && <p>{zh ? "尚未观察到 Sticker。发送后会自动出现在这里。" : "No Stickers observed yet. They appear here after use."}</p>}
        </div>
      </section>
    </section>
  );
}
