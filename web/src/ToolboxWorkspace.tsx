import { useState } from "react";

import type { CharacterCard } from "./api";
import { BehaviorNotebook } from "./BehaviorNotebook";
import { ProviderTraceViewer } from "./ProviderTraceViewer";
import { RuntimeTraceViewer } from "./RuntimeTraceViewer";
import { ToolCallingTestPanel } from "./ToolCallingTestPanel";
import { ScheduledRemindersPanel } from "./ScheduledRemindersPanel";
import { useI18n } from "./i18n";

type ToolboxPage =
  | "overview"
  | "behavior"
  | "provider"
  | "runtime"
  | "tools"
  | "schedules";

type ToolboxGroup = "observe" | "tools";

interface Props {
  cards: CharacterCard[];
  admin: boolean;
  publicDemo: boolean;
  onOpenLab: () => void;
  onOpenMatrix: () => void;
}

const items: Array<{
  id: ToolboxPage;
  group: ToolboxGroup;
  icon: string;
  en: string;
  zh: string;
  admin?: boolean;
}> = [
  { id: "overview", group: "observe", icon: "⌂", en: "Overview", zh: "概览" },
  { id: "behavior", group: "observe", icon: "▧", en: "Behavior Notebook", zh: "行为手帐", admin: true },
  { id: "provider", group: "observe", icon: "⌁", en: "Provider Calls", zh: "Provider 调用", admin: true },
  { id: "runtime", group: "observe", icon: "↝", en: "Runtime Raw", zh: "Runtime 原始记录", admin: true },
  { id: "tools", group: "tools", icon: "⚒", en: "Tool Calling", zh: "Tool Calling", admin: true },
  { id: "schedules", group: "tools", icon: "◷", en: "Schedules", zh: "提醒计划" }
];

export function ToolboxWorkspace({
  cards,
  admin,
  publicDemo,
  onOpenLab,
  onOpenMatrix
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [page, setPage] = useState<ToolboxPage>(admin ? "behavior" : "overview");
  const visibleItems = items.filter(
    (item) => (!item.admin || admin) && (item.id !== "schedules" || !publicDemo)
  );

  function renderNavigation(group: ToolboxGroup) {
    return visibleItems
      .filter((item) => item.group === group)
      .map((item) => (
        <button
          type="button"
          key={item.id}
          className={page === item.id ? "is-active" : ""}
          onClick={() => setPage(item.id)}
        >
          <span aria-hidden="true">{item.icon}</span>
          {zh ? item.zh : item.en}
        </button>
      ));
  }

  return (
    <main className="toolbox-v2-workspace">
      <aside className="toolbox-v2-sidebar">
        <div className="toolbox-v2-sidebar-top">
          <div className="toolbox-v2-title-note">
            <strong>{zh ? "角色研究工具箱" : "Behavior Observer"}</strong>
            <span aria-hidden="true">ฅ^•ﻌ•^ฅ</span>
          </div>

          <nav aria-label={zh ? "工具箱分区" : "Toolbox sections"}>
            <span className="toolbox-v2-nav-label">{zh ? "观察" : "OBSERVE"}</span>
            {renderNavigation("observe")}
            <span className="toolbox-v2-nav-label">{zh ? "工具" : "TOOLS"}</span>
            {renderNavigation("tools")}
          </nav>
        </div>

        <section className="toolbox-v2-lab-note">
          <span>LAB</span>
          <strong>{zh ? "Echo Masque 实验室" : "Echo Masque Lab"}</strong>
          <p>{zh ? "场景、测试包、实验历史与 Matrix。" : "Scenarios, test packs, experiment history, and matrices."}</p>
          <button type="button" onClick={onOpenLab}>{zh ? "打开实验室" : "Open Lab"}</button>
          {!publicDemo && <button type="button" onClick={onOpenMatrix}>{zh ? "打开 Matrix" : "Open Matrix"}</button>}
        </section>
      </aside>

      <section className="toolbox-v2-main">
        {page === "overview" && (
          <section className="toolbox-v2-overview">
            <header>
              <span className="portal-v2-tape">TOOLBOX / RESEARCH DESK</span>
              <h1>{zh ? "把角色的行为拆开来看。" : "Open the character turn and see what actually happened."}</h1>
              <p>
                {zh
                  ? "这里集中观察 LangGraph、Provider、Tool 与持久提醒；媒体证据直接归入 Behavior Notebook 与 Provider Calls。"
                  : "This desk brings LangGraph, provider calls, tools, and persistent reminders together. Media evidence stays attached to Behavior Notebook and Provider Calls instead of living in a separate page."}
              </p>
            </header>
            <div className="toolbox-v2-overview-grid">
              {admin && (
                <button onClick={() => setPage("behavior")} className="accent-lavender">
                  <span>01</span><strong>{zh ? "行为手帐" : "Behavior Notebook"}</strong><p>{zh ? "按 Character Turn 查看真实执行路径、媒体感知与证据。" : "Inspect the real execution path, media perception, and evidence by Character Turn."}</p>
                </button>
              )}
              {admin && (
                <button onClick={() => setPage("provider")} className="accent-mint">
                  <span>02</span><strong>{zh ? "Provider 调用" : "Provider Calls"}</strong><p>{zh ? "查看模型请求、媒体理解、延迟、Token 与错误。" : "Inspect model and media-understanding requests, latency, tokens, and failures."}</p>
                </button>
              )}
              {!publicDemo && (
                <button onClick={() => setPage("schedules")} className="accent-peach">
                  <span>03</span><strong>{zh ? "提醒计划" : "Schedules"}</strong><p>{zh ? "检查角色创建的持久提醒。" : "Inspect persistent reminders created by characters."}</p>
                </button>
              )}
              {admin && !publicDemo && (
                <button onClick={() => setPage("tools")} className="accent-rose">
                  <span>04</span><strong>Tool Calling</strong><p>{zh ? "直接验证 Runtime Tool 是否正常工作。" : "Directly verify Runtime Tool execution."}</p>
                </button>
              )}
            </div>
          </section>
        )}

        {page === "behavior" && admin && <BehaviorNotebook cards={cards} />}
        {page === "provider" && admin && <ProviderTraceViewer embedded onClose={() => setPage("behavior")} />}
        {page === "runtime" && admin && <RuntimeTraceViewer onClose={() => setPage("behavior")} />}
        {page === "tools" && admin && !publicDemo && <ToolCallingTestPanel onClose={() => setPage("overview")} />}
        {page === "schedules" && !publicDemo && <ScheduledRemindersPanel onClose={() => setPage("overview")} />}
      </section>
    </main>
  );
}
