import { useState } from "react";

import type { CharacterCard } from "./api";
import { BehaviorNotebook } from "./BehaviorNotebook";
import { Button, FunctionalIcon, StickyLabel, StickyNote, type FunctionalIconName } from "./components/ui";
import { ProviderTraceViewer } from "./ProviderTraceViewer";
import { RuntimeTraceViewer } from "./RuntimeTraceViewer";
import { ToolCallingTestPanel } from "./ToolCallingTestPanel";
import { ScheduledRemindersPanel } from "./ScheduledRemindersPanel";
import { useI18n } from "./i18n";

type ToolboxPage = "overview" | "behavior" | "provider" | "runtime" | "tools" | "schedules";
type ToolboxGroup = "observe" | "evidence" | "tools";

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
  icon: FunctionalIconName;
  en: string;
  zh: string;
  admin?: boolean;
}> = [
  { id: "overview", group: "observe", icon: "overview", en: "Overview", zh: "概览" },
  { id: "behavior", group: "observe", icon: "behavior", en: "Behavior Notebook", zh: "行为手帐", admin: true },
  { id: "provider", group: "evidence", icon: "provider", en: "Provider Calls", zh: "Provider 调用", admin: true },
  { id: "runtime", group: "evidence", icon: "runtime", en: "Runtime Raw", zh: "Runtime 原始记录", admin: true },
  { id: "tools", group: "tools", icon: "tools", en: "Tool Calling", zh: "Tool Calling", admin: true },
  { id: "schedules", group: "tools", icon: "schedule", en: "Schedules", zh: "提醒计划" }
];

export function ToolboxWorkspace({ cards, admin, publicDemo, onOpenLab, onOpenMatrix }: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [page, setPage] = useState<ToolboxPage>(admin ? "behavior" : "overview");
  const visibleItems = items.filter((item) => (!item.admin || admin) && (item.id !== "schedules" || !publicDemo));

  function renderNavigation(group: ToolboxGroup) {
    return visibleItems.filter((item) => item.group === group).map((item) => (
      <button type="button" key={item.id} className={page === item.id ? "is-active" : ""} onClick={() => setPage(item.id)}>
        <FunctionalIcon name={item.icon} size={17} />
        <span>{zh ? item.zh : item.en}</span>
      </button>
    ));
  }

  return (
    <main className="toolbox-v2-workspace toolbox-v3-workspace">
      <aside className="toolbox-v2-sidebar">
        <div className="toolbox-v2-sidebar-top">
          <div className="toolbox-v2-title-note">
            <StickyLabel variant="tool">RESEARCH DESK</StickyLabel>
            <strong>{zh ? "角色研究工具箱" : "Behavior Observer"}</strong>
            <span aria-hidden="true">ฅ^•ﻌ•^ฅ</span>
          </div>

          <nav aria-label={zh ? "工具箱分区" : "Toolbox sections"}>
            <span className="toolbox-v2-nav-label">{zh ? "主要观察" : "OBSERVE"}</span>
            {renderNavigation("observe")}
            {admin && <><span className="toolbox-v2-nav-label toolbox-evidence-label">{zh ? "技术证据" : "TECHNICAL EVIDENCE"}</span>{renderNavigation("evidence")}</>}
            <span className="toolbox-v2-nav-label">{zh ? "工具" : "TOOLS"}</span>
            {renderNavigation("tools")}
          </nav>
        </div>

        <StickyNote className="toolbox-v2-lab-note toolbox-v3-lab-note" variant="temporary" size="md">
          <span>LAB</span>
          <strong>{zh ? "Echo Masque 实验室" : "Echo Masque Lab"}</strong>
          <p>{zh ? "场景、测试包、实验历史与 Matrix。" : "Scenarios, test packs, experiment history, and matrices."}</p>
          <Button variant="secondary" size="sm" type="button" onClick={onOpenLab}>{zh ? "打开实验室" : "Open Lab"}</Button>
          {!publicDemo && <Button variant="ghost" size="sm" type="button" onClick={onOpenMatrix}>{zh ? "打开 Matrix" : "Open Matrix"}</Button>}
        </StickyNote>
      </aside>

      <section className="toolbox-v2-main">
        {page === "overview" && (
          <section className="toolbox-v2-overview">
            <header>
              <span className="portal-v2-tape">TOOLBOX / RESEARCH DESK</span>
              <h1>{zh ? "先读行为，再看证据。" : "Read behavior first, then inspect the evidence."}</h1>
              <p>{zh ? "Behavior Notebook 是主要入口；Provider 与 Runtime Raw 被明确归到 Technical Evidence，避免技术细节抢走角色行为的主线。" : "Behavior Notebook is the primary surface. Provider Calls and Runtime Raw are explicitly grouped as Technical Evidence so implementation detail never overtakes character behavior."}</p>
            </header>
            <div className="toolbox-v2-overview-grid">
              {admin && <button onClick={() => setPage("behavior")} className="accent-lavender"><FunctionalIcon name="behavior" size={23} /><span>01</span><strong>{zh ? "行为手帐" : "Behavior Notebook"}</strong><p>{zh ? "先读这一轮发生了什么，再展开执行路径、媒体感知与证据。" : "Read what happened first, then expand execution flow, media perception, and evidence."}</p></button>}
              {admin && <button onClick={() => setPage("provider")} className="accent-mint"><FunctionalIcon name="provider" size={23} /><span>02</span><strong>{zh ? "Provider 调用" : "Provider Calls"}</strong><p>{zh ? "模型请求、媒体理解、延迟、Token 与失败票据。" : "Model requests, media understanding, latency, tokens, and failure receipts."}</p></button>}
              {!publicDemo && <button onClick={() => setPage("schedules")} className="accent-peach"><FunctionalIcon name="schedule" size={23} /><span>03</span><strong>{zh ? "提醒计划" : "Schedules"}</strong><p>{zh ? "检查角色创建的持久提醒。" : "Inspect persistent reminders created by characters."}</p></button>}
              {admin && !publicDemo && <button onClick={() => setPage("tools")} className="accent-rose"><FunctionalIcon name="tools" size={23} /><span>04</span><strong>Tool Calling</strong><p>{zh ? "直接验证 Runtime Tool 是否正常工作。" : "Directly verify Runtime Tool execution."}</p></button>}
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