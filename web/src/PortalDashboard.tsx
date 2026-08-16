import { useEffect, useMemo, useState } from "react";

import type { CharacterCard, RuntimeStatus } from "./api";
import { CharacterPortrait } from "./CharacterPortrait";
import {
  Button,
  EmptyState,
  FunctionalIcon,
  PaperCard,
  Spinner,
  StatusIndicator,
  StickyLabel,
  StickyNote,
  type StatusTone
} from "./components/ui";
import {
  deploymentApi,
  type CharacterDeployment,
  type CharacterDeploymentPage,
  type DiscordConnectorLogPage,
  type DiscordServerCatalog,
  type DiscordServerProfile,
  type PlatformConnection
} from "./deploymentApi";
import { buildDiscordServerStatuses } from "./discordServerStatus";
import { useI18n } from "./i18n";
import type { PortalSection } from "./PortalShell";
import { formatPortalTimestamp } from "./portalTime";
import {
  schedulerApi,
  type ScheduledReminderPage
} from "./schedulerApi";
import "./portal-dashboard-reference.css";

interface Props {
  cards: CharacterCard[];
  runtime: RuntimeStatus | null;
  onNavigate: (section: PortalSection) => void;
  onCreateCharacter: () => void;
}

interface DashboardData {
  deployments: CharacterDeploymentPage | null;
  connections: PlatformConnection[] | null;
  serverProfiles: DiscordServerProfile[] | null;
  serverCatalogs: DiscordServerCatalog[] | null;
  logs: DiscordConnectorLogPage | null;
  reminders: ScheduledReminderPage | null;
}

type DashboardResource = keyof DashboardData;

const emptyDashboardData: DashboardData = {
  deployments: null,
  connections: null,
  serverProfiles: null,
  serverCatalogs: null,
  logs: null,
  reminders: null
};

function deploymentTone(status: CharacterDeployment["status"]): StatusTone {
  if (status === "active") return "success";
  if (status === "paused") return "warning";
  if (status === "error") return "danger";
  return "neutral";
}

function participationLabel(
  mode: CharacterDeployment["participation_mode"],
  zh: boolean
): string {
  const labels = zh
    ? {
        mention_only: "仅被提及时",
        reply_only: "仅回复时",
        mention_and_reply: "提及或回复",
        smart: "智能参与"
      }
    : {
        mention_only: "Mention only",
        reply_only: "Reply only",
        mention_and_reply: "Mention or reply",
        smart: "Smart participation"
      };
  return labels[mode];
}

function deploymentStatusLabel(
  status: CharacterDeployment["status"],
  zh: boolean
): string {
  if (!zh) return status.toUpperCase();
  return {
    active: "运行中",
    paused: "已暂停",
    offline: "离线",
    error: "异常",
    disconnected: "未连接"
  }[status];
}

function resourceUnavailable(zh: boolean): string {
  return zh ? "暂时无法读取这页实时记录。" : "This live notebook section is temporarily unavailable.";
}

function serverStateLabel(state: string, zh: boolean): string {
  if (!zh) return state.replaceAll("_", " ");
  return {
    stale: "状态过期",
    connector_error: "Connector 异常",
    connector_offline: "Connector 离线",
    server_not_seen: "尚未同步到 Server"
  }[state] ?? state.replaceAll("_", " ");
}

export function PortalDashboard({
  cards,
  runtime,
  onNavigate,
  onCreateCharacter
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [data, setData] = useState<DashboardData>(emptyDashboardData);
  const [loading, setLoading] = useState(true);
  const [failedResources, setFailedResources] = useState<Set<DashboardResource>>(
    () => new Set()
  );

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      setLoading(true);
      const requests = await Promise.allSettled([
        deploymentApi.listDeploymentsPage({ page: 1, pageSize: 8 }),
        deploymentApi.listConnections(),
        deploymentApi.listDiscordServerProfiles(),
        deploymentApi.listDiscordServerCatalog(),
        deploymentApi.listDiscordLogs({ page: 1, pageSize: 8 }),
        schedulerApi.page({ status: "pending", limit: 4 })
      ]);
      if (!active) return;

      const keys: DashboardResource[] = [
        "deployments",
        "connections",
        "serverProfiles",
        "serverCatalogs",
        "logs",
        "reminders"
      ];
      const failures = new Set<DashboardResource>();
      const next = { ...emptyDashboardData };

      requests.forEach((result, index) => {
        const key = keys[index];
        if (result.status === "rejected") {
          failures.add(key);
          return;
        }
        if (key === "deployments") next.deployments = result.value as CharacterDeploymentPage;
        if (key === "connections") next.connections = result.value as PlatformConnection[];
        if (key === "serverProfiles") next.serverProfiles = result.value as DiscordServerProfile[];
        if (key === "serverCatalogs") next.serverCatalogs = result.value as DiscordServerCatalog[];
        if (key === "logs") next.logs = result.value as DiscordConnectorLogPage;
        if (key === "reminders") next.reminders = result.value as ScheduledReminderPage;
      });

      setData(next);
      setFailedResources(failures);
      setLoading(false);
    }

    void loadDashboard();
    return () => {
      active = false;
    };
  }, []);

  const cardsById = useMemo(
    () => new Map(cards.map((card) => [card.id, card])),
    [cards]
  );
  const serverStatuses = useMemo(() => {
    if (!data.connections || !data.serverProfiles || !data.serverCatalogs) return null;
    return buildDiscordServerStatuses(
      data.serverProfiles,
      data.connections,
      data.serverCatalogs
    );
  }, [data.connections, data.serverProfiles, data.serverCatalogs]);
  const serversOnline = serverStatuses?.filter((item) => item.state === "connected").length ?? null;
  const configuredRuntimes = runtime
    ? [runtime.adaptive, runtime.judge].filter((item) => item.enabled && item.configured).length
    : null;

  const attentionIssues = useMemo(() => {
    const issues: Array<{ key: string; text: string }> = [];

    data.deployments?.items
      .filter((item) => item.status === "error" || item.status === "offline" || item.status === "disconnected" || Boolean(item.last_error))
      .slice(0, 3)
      .forEach((item) => {
        issues.push({
          key: `deployment-${item.id}`,
          text: zh
            ? `${item.character_display_name} 的 Discord 部署需要检查（${deploymentStatusLabel(item.status, true)}）。`
            : `${item.character_display_name}'s Discord deployment needs review (${deploymentStatusLabel(item.status, false)}).`
        });
      });

    serverStatuses
      ?.filter((item) => item.state !== "connected")
      .slice(0, Math.max(0, 3 - issues.length))
      .forEach((item) => {
        issues.push({
          key: `server-${item.profile.id}`,
          text: zh
            ? `${item.profile.guild_name || item.profile.name}：${serverStateLabel(item.state, true)}。`
            : `${item.profile.guild_name || item.profile.name} is ${serverStateLabel(item.state, false)}.`
        });
      });

    if (runtime) {
      [
        { name: "Adaptive", value: runtime.adaptive },
        { name: "Judge", value: runtime.judge }
      ].forEach(({ name, value }) => {
        if (issues.length < 3 && value.enabled && !value.configured) {
          issues.push({
            key: `runtime-${name}`,
            text: zh ? `${name} Runtime 已启用但尚未配置完成。` : `${name} Runtime is enabled but not configured.`
          });
        }
      });
    }

    if (issues.length < 3 && data.reminders && data.reminders.counts.failed > 0) {
      issues.push({
        key: "failed-reminders",
        text: zh
          ? `${data.reminders.counts.failed} 条提醒发送失败，需要到工具箱检查。`
          : `${data.reminders.counts.failed} reminder${data.reminders.counts.failed === 1 ? "" : "s"} failed and need review.`
      });
    }

    return issues;
  }, [data.deployments, data.reminders, runtime, serverStatuses, zh]);

  const attentionComplete = Boolean(
    data.deployments &&
      data.connections &&
      data.serverProfiles &&
      data.serverCatalogs &&
      data.reminders &&
      runtime
  );
  const attentionCount = attentionComplete
    ? (data.deployments?.attention ?? 0) +
      (serverStatuses?.filter((item) => item.state !== "connected").length ?? 0) +
      (data.reminders?.counts.failed ?? 0) +
      [runtime?.adaptive, runtime?.judge].filter((item) => item?.enabled && !item.configured).length
    : null;
  const liveDeployments = data.deployments?.items.slice(0, 4) ?? [];
  const recentLogs = data.logs?.items.slice(0, 5) ?? [];
  const upcomingReminders = data.reminders?.items.slice(0, 3) ?? [];
  const quickCharacters = cards.slice(0, 4);
  const discordSystemReady = serversOnline !== null && serversOnline > 0;

  return (
    <main className="portal-v2-dashboard portal-v3-dashboard">
      <div className="portal-v3-dashboard-layout">
        <div className="portal-v3-dashboard-main">
          <section className="portal-v2-dashboard-hero portal-v3-dashboard-hero">
            <div className="portal-v2-hero-copy">
              <span className="portal-v2-tape">CHARACTER RESEARCH STUDIO</span>
              <h1>{zh ? "今天想让谁去真实世界里说话？" : "Who should step into a real conversation today?"}</h1>
              <p>
                {zh
                  ? "从角色档案、Discord 部署到行为观察，把正在发生的事留在同一本研究手帐里。"
                  : "Keep character files, Discord deployments, and behavior observations together in one living research notebook."}
              </p>
              <div className="portal-v2-hero-actions">
                <Button variant="primary" onClick={onCreateCharacter}>
                  {zh ? "+ 创建角色" : "+ Create character"}
                </Button>
                <Button variant="secondary" onClick={() => onNavigate("toolbox")}>
                  {zh ? "打开行为观察" : "Open behavior observer"}
                </Button>
              </div>
            </div>
            <img
              className="portal-v3-hero-mark"
              src="/assets/scrapbook/black-cat-lavender.png"
              alt=""
              aria-hidden="true"
            />
          </section>

          <section className="portal-v3-snapshot-grid" aria-label={zh ? "工作室快照" : "Studio snapshot"}>
            <Button className="portal-v3-snapshot is-lavender" variant="ghost" onClick={() => onNavigate("characters")}>
              <FunctionalIcon name="archive" size={32} />
              <span>{zh ? "角色档案" : "Character Files"}</span>
              <strong>{cards.length}</strong>
              <small>{zh ? "已保存" : "saved"}</small>
            </Button>
            <Button className="portal-v3-snapshot is-mint" variant="ghost" onClick={() => onNavigate("deployments")}>
              <FunctionalIcon name="paper-plane" size={32} />
              <span>{zh ? "活跃部署" : "Active Deployments"}</span>
              <strong>{data.deployments?.active ?? "—"}</strong>
              <small>{data.deployments ? (zh ? "运行中" : "running") : (loading ? (zh ? "读取中" : "loading") : (zh ? "不可用" : "unavailable"))}</small>
            </Button>
            <Button className="portal-v3-snapshot is-blue" variant="ghost" onClick={() => onNavigate("deployments")}>
              <FunctionalIcon name="cloud" size={32} />
              <span>{zh ? "在线 Server" : "Servers Online"}</span>
              <strong>{serversOnline ?? "—"}</strong>
              <small>{serverStatuses ? (zh ? `共 ${serverStatuses.length} 个` : `${serverStatuses.length} total`) : (loading ? (zh ? "读取中" : "loading") : (zh ? "不可用" : "unavailable"))}</small>
            </Button>
            <Button className="portal-v3-snapshot is-rose" variant="ghost" onClick={() => onNavigate("deployments")}>
              <FunctionalIcon name="warning" size={32} />
              <span>{zh ? "需要留意" : "Needs Attention"}</span>
              <strong>{attentionCount ?? "—"}</strong>
              <small>{attentionComplete ? (zh ? "真实状态" : "live state") : (loading ? (zh ? "核对中" : "checking") : (zh ? "未完全读取" : "partially unavailable"))}</small>
            </Button>
          </section>

          <PaperCard className="portal-v3-dashboard-panel portal-v3-live-panel">
            <header className="portal-v3-panel-heading">
              <div>
                <StickyLabel variant="success">LIVE ON DISCORD</StickyLabel>
                <h2>{zh ? "正在 Discord 里的角色" : "Characters living on Discord"}</h2>
                <p>{zh ? "Server、Channel、参与方式与最近活动都来自当前部署。" : "Server, channel, participation, and recent activity come from current deployments."}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => onNavigate("deployments")}>
                {zh ? "查看全部" : "View all"} →
              </Button>
            </header>

            {loading && !data.deployments ? (
              <div className="portal-v3-inline-loading"><Spinner size="sm" label={zh ? "读取部署" : "Loading deployments"} /> {zh ? "正在翻开部署记录…" : "Opening deployment records…"}</div>
            ) : failedResources.has("deployments") ? (
              <EmptyState title={zh ? "部署记录暂不可用" : "Deployment records unavailable"} description={resourceUnavailable(zh)} />
            ) : liveDeployments.length === 0 ? (
              <EmptyState
                title={zh ? "还没有 Discord 部署" : "No Discord deployments yet"}
                description={zh ? "先从一个角色档案开始，把它带到 Server。" : "Start from a character file and bring it into a Server."}
                action={<Button variant="secondary" onClick={() => onNavigate("characters")}>{zh ? "打开角色档案" : "Open character files"}</Button>}
              />
            ) : (
              <div className="portal-v3-deployment-list">
                {liveDeployments.map((deployment) => {
                  const card = cardsById.get(deployment.character_card_id);
                  const destination = deployment.server_profile_name || deployment.workspace_name || "—";
                  const channel = deployment.thread_name || deployment.channel_name;
                  return (
                    <article className="portal-v3-deployment-row" key={deployment.id}>
                      <span className={`portal-v3-deployment-portrait portrait-${card?.portrait_variant ?? "lavender"}`}>
                        <CharacterPortrait cardId={deployment.character_card_id} alt="" />
                        <span className={`portal-v3-deployment-status-dot status-${deployment.status}`} aria-hidden="true" />
                      </span>
                      <div className="portal-v3-deployment-character">
                        <strong>{deployment.character_display_name}</strong>
                        <small>{card?.subtitle || deployment.version_label}</small>
                      </div>
                      <div className="portal-v3-deployment-destination">
                        <span>{destination}</span>
                        <small>{channel ? `# ${channel.replace(/^#/, "")}` : (zh ? "Server 全域" : "Server-wide")}</small>
                      </div>
                      <div className="portal-v3-deployment-mode">
                        <span>{participationLabel(deployment.participation_mode, zh)}</span>
                        <small>{deployment.last_message_at ? formatPortalTimestamp(deployment.last_message_at, zh) : (zh ? "暂无活动" : "No activity yet")}</small>
                      </div>
                      <StatusIndicator tone={deploymentTone(deployment.status)} pulse={deployment.status === "active"}>
                        {deploymentStatusLabel(deployment.status, zh)}
                      </StatusIndicator>
                    </article>
                  );
                })}
              </div>
            )}
          </PaperCard>

          <div className="portal-v3-dashboard-lower-grid">
            <PaperCard className="portal-v3-dashboard-panel portal-v3-activity-panel">
              <header className="portal-v3-panel-heading portal-v3-panel-heading-compact">
                <div>
                  <StickyLabel variant="neutral">RECENT ACTIVITY JOURNAL</StickyLabel>
                  <h2>{zh ? "刚刚发生了什么" : "What just happened"}</h2>
                </div>
                <Button variant="ghost" size="sm" onClick={() => onNavigate("toolbox")}>
                  {zh ? "行为观察" : "Observer"} →
                </Button>
              </header>
              {loading && !data.logs ? (
                <div className="portal-v3-inline-loading"><Spinner size="sm" label={zh ? "读取活动" : "Loading activity"} /> {zh ? "整理活动记录…" : "Gathering activity…"}</div>
              ) : failedResources.has("logs") ? (
                <EmptyState title={zh ? "活动记录暂不可用" : "Activity journal unavailable"} description={resourceUnavailable(zh)} />
              ) : recentLogs.length === 0 ? (
                <EmptyState title={zh ? "今天还没有 Discord 活动" : "No Discord activity yet"} description={zh ? "Connector 的安全事件摘要会出现在这里。" : "Safe connector event summaries will appear here."} />
              ) : (
                <ol className="portal-v3-activity-list">
                  {recentLogs.map((log) => (
                    <li key={log.id}>
                      <span className={`portal-v3-activity-dot level-${log.level}`} aria-hidden="true" />
                      <div>
                        <strong>{log.character_name || log.event_type.replaceAll("_", " ")}</strong>
                        <p>{log.message || log.event_type.replaceAll("_", " ")}</p>
                        <small>{[log.guild_name, log.channel_name].filter(Boolean).join(" · ") || "Discord"} · {formatPortalTimestamp(log.occurred_at, zh)}</small>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </PaperCard>

            <PaperCard className="portal-v3-dashboard-panel portal-v3-character-panel">
              <header className="portal-v3-panel-heading portal-v3-panel-heading-compact">
                <div>
                  <StickyLabel variant="image">CHARACTER FILES</StickyLabel>
                  <h2>{zh ? "常用角色档案" : "Character files at hand"}</h2>
                </div>
                <Button variant="ghost" size="sm" onClick={() => onNavigate("characters")}>
                  {zh ? "打开档案册" : "Open archive"} →
                </Button>
              </header>
              {quickCharacters.length === 0 ? (
                <EmptyState
                  title={zh ? "档案册还是空的" : "The archive is empty"}
                  description={zh ? "写下第一个角色档案，研究就从这里开始。" : "Write the first character file to begin the studio."}
                  action={<Button variant="primary" onClick={onCreateCharacter}>{zh ? "创建角色" : "Create character"}</Button>}
                />
              ) : (
                <div className="portal-v3-character-strip">
                  {quickCharacters.map((card) => (
                    <Button className={`portal-v3-character-file portrait-${card.portrait_variant}`} variant="ghost" key={card.id} onClick={() => onNavigate("characters")} aria-label={`${zh ? "打开角色档案" : "Open character file"}: ${card.display_name}`}>
                      <span className="portal-v3-character-photo"><CharacterPortrait cardId={card.id} alt="" /></span>
                      <span><strong>{card.display_name}</strong><small>{card.subtitle}</small></span>
                    </Button>
                  ))}
                </div>
              )}
            </PaperCard>
          </div>

          <section className="portal-v3-system-note" aria-label={zh ? "系统状态" : "System status"}>
            <span className="portal-v3-system-label">SYSTEM NOTE</span>
            <StatusIndicator tone={runtime?.judge.configured ? "success" : runtime ? "warning" : "neutral"}>Judge {runtime?.judge.configured ? (zh ? "就绪" : "ready") : (zh ? "待配置" : "not ready")}</StatusIndicator>
            <StatusIndicator tone={runtime?.adaptive.configured ? "success" : runtime ? "warning" : "neutral"}>Adaptive {runtime?.adaptive.configured ? (zh ? "就绪" : "ready") : (zh ? "待配置" : "not ready")}</StatusIndicator>
            <StatusIndicator tone={discordSystemReady ? "success" : serverStatuses ? "warning" : "neutral"}>Discord {discordSystemReady ? (zh ? "在线" : "ready") : serverStatuses ? (zh ? "未在线" : "not online") : (zh ? "核对中" : "checking")}</StatusIndicator>
            <small>{configuredRuntimes === null ? (zh ? "正在读取 Runtime" : "Reading runtime") : (zh ? `${configuredRuntimes}/2 个评测 Runtime 已配置` : `${configuredRuntimes}/2 evaluation runtimes configured`)}</small>
          </section>
        </div>

        <aside className="portal-v3-dashboard-margin" aria-label={zh ? "研究手帐边栏" : "Research notebook margin"}>
          <StickyNote className="portal-v3-studio-note" variant="reminder" size="lg" pinned>
            <span className="portal-v3-note-kicker">STUDIO NOTE</span>
            <strong className="portal-v3-studio-number">{cards.length}</strong>
            <h2>{zh ? "个角色档案" : cards.length === 1 ? "Character File" : "Character Files"}</h2>
            <div className="portal-v3-studio-rule" aria-hidden="true" />
            <p>
              {data.deployments
                ? zh
                  ? `${data.deployments.active} 个活跃部署 · ${configuredRuntimes ?? "—"}/2 个评测 Runtime 已配置`
                  : `${data.deployments.active} active deployment${data.deployments.active === 1 ? "" : "s"} · ${configuredRuntimes ?? "—"}/2 evaluation runtimes configured`
                : loading
                  ? zh ? "正在整理工作室记录…" : "Gathering studio records…"
                  : resourceUnavailable(zh)}
            </p>
            <img src="/assets/scrapbook/black-cat-lavender.png" alt="" aria-hidden="true" />
          </StickyNote>

          <StickyNote className="portal-v3-attention-note" variant={attentionIssues.length > 0 ? "warning" : "note"} size="lg" pinned>
            <span className="portal-v3-note-kicker">ATTENTION NOTES</span>
            <h2>{zh ? "需要我留意吗？" : "Anything need attention?"}</h2>
            {loading && !attentionComplete ? (
              <div className="portal-v3-note-loading"><Spinner size="sm" label={zh ? "核对状态" : "Checking status"} /> {zh ? "核对中…" : "Checking…"}</div>
            ) : attentionIssues.length > 0 ? (
              <ul>{attentionIssues.map((issue) => <li key={issue.key}>{issue.text}</li>)}</ul>
            ) : attentionComplete ? (
              <p>{zh ? "目前没有检测到部署、Server、提醒或 Runtime 异常。" : "No deployment, Server, reminder, or runtime issues detected."}</p>
            ) : (
              <p>{resourceUnavailable(zh)}</p>
            )}
            <Button variant="ghost" size="sm" onClick={() => onNavigate("deployments")}>{zh ? "检查部署" : "Review deployments"} →</Button>
          </StickyNote>

          <StickyNote className="portal-v3-upcoming-note" variant="reminder" size="lg">
            <span className="portal-v3-note-kicker">UPCOMING</span>
            <h2>{zh ? "接下来的提醒" : "Coming up"}</h2>
            {loading && !data.reminders ? (
              <div className="portal-v3-note-loading"><Spinner size="sm" label={zh ? "读取提醒" : "Loading reminders"} /> {zh ? "翻开日程…" : "Opening schedule…"}</div>
            ) : failedResources.has("reminders") ? (
              <p>{resourceUnavailable(zh)}</p>
            ) : upcomingReminders.length === 0 ? (
              <p>{zh ? "目前没有等待中的持久提醒。" : "No persistent reminders are pending."}</p>
            ) : (
              <ol>
                {upcomingReminders.map((reminder) => (
                  <li key={reminder.id}>
                    <strong>{reminder.character_name}</strong>
                    <span>{reminder.reminder_text}</span>
                    <small>{formatPortalTimestamp(reminder.scheduled_at, zh)}</small>
                  </li>
                ))}
              </ol>
            )}
            <Button variant="ghost" size="sm" onClick={() => onNavigate("toolbox")}>{zh ? "打开工具箱" : "Open toolbox"} →</Button>
          </StickyNote>

          <div className="portal-v3-margin-doodle" aria-hidden="true">
            <span>✦</span>
            <strong>observe</strong>
            <span>↳</span>
          </div>
        </aside>
      </div>
    </main>
  );
}
