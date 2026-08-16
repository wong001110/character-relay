import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  Button,
  EmptyState,
  FormField,
  Input,
  PaperCard,
  PaperDrawer,
  PaperTab,
  Select,
  Spinner,
  StatusIndicator,
  StickyLabel,
  StickyNote,
  Toast,
  type StatusTone
} from "./components/ui";
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

type InteractionNotebookTab = "templates" | "sessions";

function discordUserId(value: string): string {
  return value.trim().replaceAll(/[<@!>]/gu, "");
}

function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}

function sessionTone(status: InteractionStatus): StatusTone {
  if (status === "active") return "success";
  if (status === "paused") return "warning";
  if (status === "completed") return "info";
  if (status === "stopped") return "neutral";
  return "neutral";
}

export function InteractionSessionsPanel({ demoMode, zh, serverProfile, serverCatalog }: Props) {
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [templates, setTemplates] = useState<InteractionTemplate[]>([]);
  const [sessions, setSessions] = useState<InteractionSession[]>([]);
  const [notebookTab, setNotebookTab] = useState<InteractionNotebookTab>("templates");
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
    () => (serverCatalog?.channels ?? []).filter(
      (channel) =>
        !serverProfile.excluded_channel_ids.includes(channel.id) &&
        (!channel.category_id || !serverProfile.excluded_category_ids.includes(channel.category_id))
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
        interactionApi.listSessions({ connectionId: serverProfile.connection_id, guildId: serverProfile.guild_id })
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
    setNotebookTab("templates");
    setTemplateDrawerOpen(false);
    setEditingTemplate(null);
    setApplyingTemplate(null);
    void load();
  }, [serverProfile.id]);

  function openNewTemplate() {
    setEditingTemplate(null);
    setFirstCharacterId(activeDeployments[0]?.character_card_id ?? "");
    setSecondCharacterId(activeDeployments.find((item) => item.character_card_id !== activeDeployments[0]?.character_card_id)?.character_card_id ?? "");
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
      if (editingTemplate) await interactionApi.updateTemplate(editingTemplate.id, payload);
      else await interactionApi.createTemplate({ server_profile_id: serverProfile.id, ...payload });
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
    try {
      setWorking(true);
      await interactionApi.applyTemplate(applyingTemplate.id, {
        channel_id: String(data.get("channel_id") ?? ""),
        target_user_id: discordUserId(String(data.get("target_user_id") ?? "")),
        target_display_name: String(data.get("target_display_name") ?? "").trim(),
        status: String(data.get("status")) === "active" ? "active" : "paused"
      });
      setApplyingTemplate(null);
      await load();
      setNotebookTab("sessions");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeTemplate(item: InteractionTemplate) {
    if (!window.confirm(zh ? `删除 Template“${item.name}”？` : `Delete “${item.name}”?`)) return;
    try { setWorking(true); await interactionApi.deleteTemplate(item.id); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  async function setStatus(item: InteractionSession, status: InteractionStatus) {
    try { setWorking(true); await interactionApi.updateSessionStatus(item.id, status); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  async function removeSession(item: InteractionSession) {
    if (!window.confirm(zh ? "删除这个 Server Session？" : "Delete this Server Session?")) return;
    try { setWorking(true); await interactionApi.deleteSession(item.id); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  return (
    <section className="interaction-module interaction-notebook interaction-v3-notebook">
      {error && <Toast className="interaction-error" tone="danger" title={zh ? "互动记录操作失败" : "Interaction operation failed"}>{error}</Toast>}

      <aside className="interaction-notebook-tabs" aria-label={zh ? "互动记录分页" : "Interaction notebook pages"}>
        <span className="interaction-tab-caption">INTERACTION</span>
        <PaperTab tone="peach" active={notebookTab === "templates"} onClick={() => setNotebookTab("templates")}><strong>{zh ? "互动模板" : "Templates"}</strong><small>{templates.length}</small></PaperTab>
        <PaperTab tone="yellow" active={notebookTab === "sessions"} onClick={() => setNotebookTab("sessions")}><strong>{zh ? "Server Session" : "Server Sessions"}</strong><small>{sessions.length}</small></PaperTab>
      </aside>

      <div className="interaction-notebook-page">
        {notebookTab === "templates" && (
          <section className="paper-sheet interaction-panel interaction-template-page">
            <div className="panel-heading-row interaction-heading-row">
              <div><StickyLabel variant="neutral">INTERACTION TEMPLATES</StickyLabel><h2>{zh ? "可复用的多角色互动规则" : "Reusable multi-character interaction rules"}</h2><p>{zh ? `Template 属于 ${serverProfile.guild_name}。它是可重复套用的规则卡；Apply 后才会产生实际 Session。` : `Templates belong to ${serverProfile.guild_name}. They are reusable rule cards; applying one creates a real Session.`}</p></div>
              {!demoMode && <Button variant="primary" onClick={openNewTemplate} disabled={activeDeployments.length < 2}>{zh ? "+ 新 Template" : "+ New Template"}</Button>}
            </div>

            {activeDeployments.length < 2 && <Toast tone="warning">{zh ? "当前 Server 至少需要两个 Active Character Deployment，才能建立双角色 Template。" : "This Server needs at least two active Character Deployments before a two-character Template can be created."}</Toast>}

            {loading ? <EmptyState title={zh ? "正在翻开 Interaction Template…" : "Opening Interaction Templates…"} illustration={<Spinner label={zh ? "读取 Template" : "Loading templates"} />} /> : (
              <div className="interaction-template-grid">
                {templates.map((item) => (
                  <PaperCard className="interaction-template-card" key={item.id}>
                    <div className="interaction-template-title"><div><StickyLabel variant="neutral">INTERACTION TEMPLATE</StickyLabel><strong>{item.name}</strong></div><StickyLabel variant={item.intensity === "sharp" ? "warning" : "neutral"}>{item.intensity}</StickyLabel></div>
                    <StickyNote className="interaction-order-note" variant="temporary" size="sm"><strong>{item.participant_names.join(" → ")}</strong><small>{zh ? "固定角色顺序" : "fixed character order"}</small></StickyNote>
                    <dl className="interaction-template-metrics"><div><dt>{zh ? "轮次" : "Rounds"}</dt><dd>{item.rounds_per_trigger}</dd></div><div><dt>{zh ? "回复" : "Replies"}</dt><dd>{item.maximum_replies_per_trigger}</dd></div><div><dt>{zh ? "触发" : "Triggers"}</dt><dd>{item.maximum_triggers}</dd></div><div><dt>{zh ? "冷却" : "Cooldown"}</dt><dd>{item.cooldown_seconds}s</dd></div></dl>
                    {!demoMode && <div className="interaction-actions"><Button variant="primary" size="sm" onClick={() => setApplyingTemplate(item)} disabled={!availableChannels.length}>{zh ? "Apply / 建立 Session" : "Apply / Create Session"}</Button><Button variant="secondary" size="sm" onClick={() => openEditTemplate(item)}>{zh ? "编辑" : "Edit"}</Button><Button variant="ghost" size="sm" onClick={() => void removeTemplate(item)}>{zh ? "删除" : "Delete"}</Button></div>}
                  </PaperCard>
                ))}
                {!templates.length && <EmptyState title={zh ? "还没有 Interaction Template" : "No Interaction Templates yet"} description={zh ? "先保存角色顺序和运行限制，之后可以重复 Apply 给不同 Channel 或目标用户。" : "Save character order and limits once, then apply the Template to different Channels or target members."} action={!demoMode ? <Button variant="primary" onClick={openNewTemplate} disabled={activeDeployments.length < 2}>{zh ? "建立第一个 Template" : "Create first Template"}</Button> : undefined} />}
              </div>
            )}
          </section>
        )}

        {notebookTab === "sessions" && (
          <section className="paper-sheet interaction-panel interaction-session-page">
            <div className="panel-heading-row interaction-heading-row"><div><StickyLabel variant="link">INTERACTION JOURNAL</StickyLabel><h2>{zh ? "Server Session 运行记录" : "Server Session Journal"}</h2><p>{zh ? "Session 是 Template 的运行实例。按真实运行记录查看谁和谁互动、在哪里发生、进度与状态。" : "Sessions are running Template instances. Read them as an interaction journal: who interacted, where it happened, progress, and current state."}</p></div><Button variant="secondary" onClick={() => setNotebookTab("templates")}>{zh ? "查看 Template" : "Back to Templates"}</Button></div>
            <div className="interaction-card-grid">
              {sessions.map((item) => (
                <StickyNote className="interaction-card" variant={item.status === "active" ? "character" : "note"} key={item.id}>
                  <div className="interaction-card-heading"><strong>{item.participant_names.join(" ↔ ")}</strong><StatusIndicator tone={sessionTone(item.status)} pulse={item.status === "active"}>{item.status}</StatusIndicator></div>
                  <p><b>{zh ? "目标" : "Target"}:</b> {item.target_display_name || item.target_user_id}</p><p><b>Channel:</b> #{item.channel_name}</p><p><b>{zh ? "轮次" : "Rounds"}:</b> {item.rounds_per_trigger} · {item.maximum_replies_per_trigger} {zh ? "条回复/触发" : "replies/trigger"}</p><p><b>{zh ? "触发" : "Triggers"}:</b> {item.completed_triggers} / {item.maximum_triggers}</p><p><b>{zh ? "冷却" : "Cooldown"}:</b> {item.cooldown_seconds}s · {minutes(item.duration_seconds)}m</p>
                  {!demoMode && <div className="interaction-actions">{item.status !== "active" && <Button variant="secondary" size="sm" disabled={working} onClick={() => void setStatus(item, "active")}>{zh ? "启用" : "Activate"}</Button>}{item.status === "active" && <Button variant="secondary" size="sm" disabled={working} onClick={() => void setStatus(item, "paused")}>{zh ? "暂停" : "Pause"}</Button>}{!["stopped", "completed"].includes(item.status) && <Button variant="ghost" size="sm" disabled={working} onClick={() => void setStatus(item, "stopped")}>{zh ? "停止" : "Stop"}</Button>}<Button variant="ghost" size="sm" disabled={working} onClick={() => void removeSession(item)}>{zh ? "删除" : "Delete"}</Button></div>}
                </StickyNote>
              ))}
              {!loading && !sessions.length && <EmptyState title={zh ? "当前 Server 没有 Session" : "No Sessions in this Server"} description={zh ? "回到 Interaction Template，点击 Apply 建立 Session。" : "Return to Interaction Templates and Apply one to create a Session."} />}
            </div>
          </section>
        )}
      </div>

      {templateDrawerOpen && !demoMode && (
        <PaperDrawer onClose={() => setTemplateDrawerOpen(false)} ariaLabel={editingTemplate ? (zh ? "编辑 Interaction Template" : "Edit Interaction Template") : (zh ? "建立 Interaction Template" : "Create Interaction Template")} className="interaction-drawer-v3">
          <div className="interaction-drawer-header"><div><StickyLabel variant="neutral">{editingTemplate ? "EDIT TEMPLATE" : "NEW TEMPLATE"}</StickyLabel><h2>{editingTemplate ? editingTemplate.name : zh ? "建立 Interaction Template" : "Create Interaction Template"}</h2><p>{serverProfile.guild_name}</p></div><Button variant="ghost" onClick={() => setTemplateDrawerOpen(false)}>{zh ? "关闭" : "Close"}</Button></div>
          <form className="interaction-drawer-form" onSubmit={saveTemplate} key={editingTemplate?.id ?? "new-template"}>
            <FormField className="drawer-form-wide" label={zh ? "Template 名称" : "Template name"} required><Input name="name" required defaultValue={editingTemplate?.name ?? "Ann + Ning Roast"} /></FormField>
            <FormField label={zh ? "第一位角色" : "First character"} required><Select value={firstCharacterId} onChange={(event) => setFirstCharacterId(event.currentTarget.value)} required>{activeDeployments.map((item) => <option key={item.id} value={item.character_card_id}>{item.character_display_name}</option>)}</Select></FormField>
            <FormField label={zh ? "第二位角色" : "Second character"} required><Select value={secondCharacterId} onChange={(event) => setSecondCharacterId(event.currentTarget.value)} required>{activeDeployments.filter((item) => item.character_card_id !== firstCharacterId).map((item) => <option key={item.id} value={item.character_card_id}>{item.character_display_name}</option>)}</Select></FormField>
            <StickyNote className="interaction-form-summary drawer-form-wide" variant="temporary" size="sm"><strong>{zh ? "固定顺序" : "Fixed order"}</strong><span>{activeDeployments.find((item) => item.character_card_id === firstCharacterId)?.character_display_name || "—"}{" → "}{activeDeployments.find((item) => item.character_card_id === secondCharacterId)?.character_display_name || "—"}</span><small>{zh ? "每一轮两个角色各回复一次。" : "Each round gives both characters one turn."}</small></StickyNote>
            <FormField label={zh ? "每次触发轮数" : "Rounds per trigger"}><Input name="rounds_per_trigger" type="number" min="1" max="3" defaultValue={editingTemplate?.rounds_per_trigger ?? 1} /></FormField><FormField label={zh ? "最多触发次数" : "Maximum triggers"}><Input name="maximum_triggers" type="number" min="1" max="5" defaultValue={editingTemplate?.maximum_triggers ?? 1} /></FormField><FormField label={zh ? "冷却秒数" : "Cooldown seconds"}><Input name="cooldown_seconds" type="number" min="0" max="3600" defaultValue={editingTemplate?.cooldown_seconds ?? 60} /></FormField><FormField label={zh ? "持续分钟" : "Duration minutes"}><Input name="duration_minutes" type="number" min="1" max="1440" defaultValue={minutes(editingTemplate?.duration_seconds ?? 600)} /></FormField>
            <FormField className="drawer-form-wide" label={zh ? "强度" : "Intensity"}><Select value={intensity} onChange={(event) => setIntensity(event.currentTarget.value as InteractionIntensity)}><option value="light">Light</option><option value="playful">Playful</option><option value="sharp">Sharp</option></Select></FormField>
            <Button className="drawer-form-wide" variant="primary" disabled={working || !firstCharacterId || !secondCharacterId}>{working ? <><Spinner size="sm" label={zh ? "保存中" : "Saving"} /> {zh ? "保存中…" : "Saving…"}</> : zh ? "保存 Template" : "Save Template"}</Button>
          </form>
        </PaperDrawer>
      )}

      {applyingTemplate && !demoMode && (
        <PaperDrawer onClose={() => setApplyingTemplate(null)} ariaLabel={zh ? "套用 Interaction Template" : "Apply Interaction Template"} className="interaction-drawer-v3 interaction-apply-drawer-v3">
          <div className="interaction-drawer-header"><div><StickyLabel variant="link">APPLY TEMPLATE</StickyLabel><h2>{applyingTemplate.name}</h2><p>{applyingTemplate.participant_names.join(" → ")} · {serverProfile.guild_name}</p></div><Button variant="ghost" onClick={() => setApplyingTemplate(null)}>{zh ? "关闭" : "Close"}</Button></div>
          <form className="interaction-drawer-form" onSubmit={applyTemplate}>
            <FormField className="drawer-form-wide" label="Channel" required><Select name="channel_id" required defaultValue={availableChannels[0]?.id ?? ""}>{availableChannels.map((channel) => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}</Select></FormField>
            <FormField className="drawer-form-wide" label={zh ? "目标用户 ID 或 Mention" : "Target user ID or mention"} required><Input name="target_user_id" required placeholder="<@606232885489303603>" /></FormField>
            <FormField className="drawer-form-wide" label={zh ? "目标显示名称" : "Target display name"}><Input name="target_display_name" placeholder="501 Not Implemented" /></FormField>
            <FormField className="drawer-form-wide" label={zh ? "建立后状态" : "Initial status"}><Select name="status" defaultValue="paused"><option value="paused">Paused</option><option value="active">Active</option></Select></FormField>
            <StickyNote className="interaction-consent-note drawer-form-wide" variant="warning" size="sm">{zh ? "仅用于已明确同意参与的测试成员或你自己的测试账号。" : "Use only with a consenting test member or your own test account."}</StickyNote>
            <Button className="drawer-form-wide" variant="primary" disabled={working || !availableChannels.length}>{working ? (zh ? "Apply 中…" : "Applying…") : zh ? "建立 Server Session" : "Create Server Session"}</Button>
          </form>
        </PaperDrawer>
      )}
    </section>
  );
}