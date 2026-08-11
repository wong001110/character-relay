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
  | "media"
  | "runtime"
  | "tools"
  | "schedules";

interface Props {
  cards: CharacterCard[];
  admin: boolean;
  publicDemo: boolean;
  onOpenLab: () => void;
  onOpenMatrix: () => void;
}

const items: Array<{ id: ToolboxPage; icon: string; en: string; zh: string; admin?: boolean }> = [
  { id: "overview", icon: "⌂", en: "Overview", zh: "概览" },
  { id: "behavior", icon: "▧", en: "Behavior Notebook", zh: "行为手帐", admin: true },
  { id: "provider", icon: "⌁", en: "Provider Calls", zh: "Provider 调用", admin: true },
  { id: "media", icon: "◉", en: "Media & Cache", zh: "媒体与缓存", admin: true },
  { id: "runtime", icon: "↝", en: "Runtime Raw", zh: "Runtime 原始记录", admin: true },
  { id: "tools", icon: "⚒", en: "Tool Calling", zh: "Tool Calling", admin: true },
  { id: "schedules", icon: "◷", en: "Schedules", zh: "提醒计划" }
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

  return (
    <main className="toolbox-v2-workspace">
      <aside className="toolbox-v2-sidebar">
        <div className="toolbox-v2-title-note">
          <strong>{zh ? "角色研究工具箱" : "Behavior Observer"}</strong>
          <span aria-hidden="true">ฅ^•ﻌ•^ฅ</span>
        </div>
        <nav aria-label={zh ? "工具箱分区" : "Toolbox sections"}>
          {items
            .filter((item) => !item.admin || admin)
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
            ))}
        </nav>

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
              <p>{zh ? "这里集中观察 LangGraph、Provider、Tool、Media 与测试工具。" : "This desk brings LangGraph, provider calls, tools, media, and testing utilities into one place."}</p>
            </header>
            <div className="toolbox-v2-overview-grid">
              {admin && (
                <button onClick={() => setPage("behavior")} className="accent-lavender">
                  <span>01</span><strong>{zh ? "行为手帐" : "Behavior Notebook"}</strong><p>{zh ? "按 Character Turn 查看真实执行路径与证据。" : "Inspect the real execution path and evidence by Character Turn."}</p>
                </button>
              )}
              {admin && (
                <button onClick={() => setPage("provider")} className="accent-mint">
                  <span>02</span><strong>{zh ? "Provider 调用" : "Provider Calls"}</strong><p>{zh ? "查看模型请求、延迟、Token 与错误。" : "Inspect model requests, latency, tokens, and failures."}</p>
                </button>
              )}
              <button onClick={() => setPage("schedules")} className="accent-peach">
                <span>03</span><strong>{zh ? "提醒计划" : "Schedules"}</strong><p>{zh ? "检查角色创建的持久提醒。" : "Inspect persistent reminders created by characters."}</p>
              </button>
              {admin && (
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

        {page === "media" && admin && (
          <section className="toolbox-v2-media-board">
            <header>
              <span className="portal-v2-tape">MEDIA / PERCEPTION</span>
              <h1>{zh ? "角色看见了什么？" : "What did the character actually perceive?"}</h1>
              <p>{zh ? "Media Attention、Understanding、Cache 与角色声明姿态都应该从真实 trace 证据读取。" : "Media Attention, Understanding, cache behavior, and declared stance should all be read from real trace evidence."}</p>
            </header>
            <div className="toolbox-v2-media-grid">
              <article><span>◉</span><strong>{zh ? "实际感知" : "Actual perception"}</strong><p>{zh ? "Behavior Notebook 会显示 perceived / skipped / unavailable。" : "Behavior Notebook shows perceived / skipped / unavailable."}</p></article>
              <article><span>✦</span><strong>{zh ? "角色姿态" : "Character stance"}</strong><p>truthful · tease · bluff · lie · evasive · guess · uncertain</p></article>
              <article><span>⌁</span><strong>{zh ? "Provider 证据" : "Provider evidence"}</strong><p>{zh ? "媒体理解请求仍可在 Provider Calls 中检查。" : "Media understanding requests remain inspectable under Provider Calls."}</p></article>
              <article><span>↻</span><strong>Cache</strong><p>{zh ? "命中缓存时不会产生重复的媒体理解 Provider 请求。" : "Cache hits avoid duplicate media-understanding provider requests."}</p></article>
            </div>
            <button className="paper-button" onClick={() => setPage("behavior")}>{zh ? "回到行为手帐" : "Open Behavior Notebook"}</button>
            <button className="paper-button" onClick={() => setPage("provider")}>{zh ? "查看 Provider Calls" : "Inspect Provider Calls"}</button>
          </section>
        )}
      </section>
    </main>
  );
}
