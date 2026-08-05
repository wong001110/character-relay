import { useEffect, useMemo, useState, type FormEvent } from "react";

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
