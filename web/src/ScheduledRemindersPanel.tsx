import { useEffect, useRef, useState } from "react";

import { useI18n } from "./i18n";
import { formatPortalTimestamp } from "./portalTime";
import {
  schedulerApi,
  type ScheduledReminder,
  type ScheduledReminderCounts,
  type ScheduledReminderStatus
} from "./schedulerApi";
import "./scheduled-reminders.css";

const EMPTY_COUNTS: ScheduledReminderCounts = {
  pending: 0,
  processing: 0,
  completed: 0,
  failed: 0,
  cancelled: 0
};

function statusLabel(status: ScheduledReminderStatus, zh: boolean): string {
  if (!zh) return status;
  return {
    pending: "等待中",
    processing: "执行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消"
  }[status];
}

function destination(item: ScheduledReminder): string {
  const channel = item.channel_name || item.channel_id || item.platform;
  return item.thread_name || item.thread_id
    ? `${channel} / ${item.thread_name || item.thread_id}`
    : channel;
}

export function ScheduledRemindersPanel({
  onClose,
  readOnly = false
}: {
  onClose: () => void;
  readOnly?: boolean;
}) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [items, setItems] = useState<ScheduledReminder[]>([]);
  const [counts, setCounts] = useState<ScheduledReminderCounts>(EMPTY_COUNTS);
  const [status, setStatus] = useState<ScheduledReminderStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [visible, setVisible] = useState(() => document.visibilityState === "visible");
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<Array<string | null>>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [pollCycle, setPollCycle] = useState(0);
  const requestRef = useRef<AbortController | null>(null);

  async function load(
    targetCursor: string | null = cursor,
    background = false
  ) {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    if (!background) setLoading(true);
    try {
      const result = await schedulerApi.page({
        status,
        limit: 50,
        cursor: targetCursor,
        signal: controller.signal
      });
      if (controller.signal.aborted) return;
      setItems(result.items);
      setCounts(result.counts);
      setNextCursor(result.next_cursor);
      setError(null);
    } catch (reason) {
      if (controller.signal.aborted) return;
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        if (background) {
          setPollCycle((current) => current + 1);
        } else {
          setLoading(false);
        }
      }
    }
  }

  function resetAndLoad() {
    setCursor(null);
    setCursorHistory([]);
    setNextCursor(null);
    setPage(1);
    void load(null);
  }

  function showOlder() {
    if (!nextCursor) return;
    setCursorHistory((current) => [...current, cursor]);
    setCursor(nextCursor);
    setPage((current) => current + 1);
    void load(nextCursor);
  }

  function showNewer() {
    const previous = cursorHistory.at(-1);
    if (previous === undefined) return;
    setCursorHistory((current) => current.slice(0, -1));
    setCursor(previous);
    setPage((current) => Math.max(1, current - 1));
    void load(previous);
  }

  useEffect(() => {
    resetAndLoad();
  }, [status]);

  useEffect(() => {
    const onVisibilityChange = () => {
      setVisible(document.visibilityState === "visible");
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      requestRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!autoRefresh || !visible || page !== 1) return;
    const delay = counts.processing > 0 ? 5000 : counts.pending > 0 ? 10000 : 30000;
    const timer = window.setTimeout(() => void load(null, true), delay);
    return () => window.clearTimeout(timer);
  }, [
    autoRefresh,
    visible,
    page,
    status,
    counts.processing,
    counts.pending,
    pollCycle
  ]);

  async function cancel(item: ScheduledReminder) {
    const confirmed = window.confirm(
      zh
        ? `取消 ${item.character_name} 的提醒？\n${item.reminder_text}`
        : `Cancel ${item.character_name}'s reminder?\n${item.reminder_text}`
    );
    if (!confirmed) return;
    try {
      await schedulerApi.cancel(item.id);
      await load(cursor);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <section className="scheduled-reminders-panel">
      <header className="scheduled-reminders-header">
        <div>
          <p className="tape-label">TOOL CALLING / SCHEDULER</p>
          <h2>{zh ? "提醒计划" : "Scheduled reminders"}</h2>
          <p>
            {zh
              ? "只有出现在这里的记录才代表 scheduler.remind 已实际执行并写入 Runtime；角色口头说“会提醒”不算成功。所有时间统一按马来西亚时间（MYT）显示。"
              : "A reminder is real only after scheduler.remind executed and a record appears here. A character promise alone is not confirmation. All times are shown in Malaysia time (MYT)."}
          </p>
        </div>
        <button type="button" className="paper-button" onClick={onClose}>
          {zh ? "返回" : "Back"}
        </button>
      </header>

      <div className="scheduled-reminders-toolbar">
        <label>
          {zh ? "状态" : "Status"}
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.currentTarget.value as ScheduledReminderStatus | "all")
            }
          >
            <option value="all">{zh ? "全部" : "All"}</option>
            <option value="pending">{zh ? "等待中" : "Pending"}</option>
            <option value="processing">{zh ? "执行中" : "Processing"}</option>
            <option value="completed">{zh ? "已完成" : "Completed"}</option>
            <option value="failed">{zh ? "失败" : "Failed"}</option>
            <option value="cancelled">{zh ? "已取消" : "Cancelled"}</option>
          </select>
        </label>
        <button type="button" className="paper-button" onClick={() => void load(cursor)}>
          {loading ? (zh ? "读取中…" : "Loading…") : zh ? "刷新" : "Refresh"}
        </button>
        <label className="scheduled-reminders-auto-refresh">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(event) => setAutoRefresh(event.currentTarget.checked)}
          />
          {zh ? "自适应刷新（5–30 秒）" : "Adaptive refresh (5–30s)"}
        </label>
        <span>
          {zh ? `第 ${page} 页 · ${items.length} 条` : `Page ${page} · ${items.length} items`}
        </span>
      </div>

      {status === "all" && (
        <div className="scheduled-reminders-summary">
          <span>{zh ? "等待" : "Pending"} <strong>{counts.pending}</strong></span>
          <span>{zh ? "执行" : "Processing"} <strong>{counts.processing}</strong></span>
          <span>{zh ? "完成" : "Completed"} <strong>{counts.completed}</strong></span>
          <span>{zh ? "失败" : "Failed"} <strong>{counts.failed}</strong></span>
        </div>
      )}

      {error && <p className="error-note">{error}</p>}

      <div className="scheduled-reminders-list">
        {loading && items.length === 0 ? (
          <div className="scheduled-reminders-empty">
            <strong>{zh ? "正在读取提醒…" : "Loading reminders…"}</strong>
          </div>
        ) : items.length === 0 ? (
          <div className="scheduled-reminders-empty">
            <strong>{zh ? "目前没有提醒记录" : "No reminder records"}</strong>
            <p>
              {zh
                ? "测试 scheduler.remind 后，这里会显示计划时间、角色、状态与失败原因。"
                : "After scheduler.remind runs, this view shows schedule time, character, status, and failures."}
            </p>
          </div>
        ) : (
          <>
            {items.map((item) => (
              <article className="scheduled-reminder-card" key={item.id}>
                <div className="scheduled-reminder-card-heading">
                  <div>
                    <strong>{item.character_name}</strong>
                    <small>{destination(item)}</small>
                  </div>
                  <span className={`scheduled-reminder-status reminder-${item.status}`}>
                    {statusLabel(item.status, zh)}
                  </span>
                </div>
                <p className="scheduled-reminder-text">{item.reminder_text}</p>
                <dl>
                  <div>
                    <dt>{zh ? "计划时间" : "Scheduled"}</dt>
                    <dd>{formatPortalTimestamp(item.scheduled_at, zh)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "建立时间" : "Created"}</dt>
                    <dd>{formatPortalTimestamp(item.created_at, zh)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "尝试次数" : "Attempts"}</dt>
                    <dd>{item.attempt_count}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "送达时间" : "Delivered"}</dt>
                    <dd>
                      {item.delivered_at
                        ? formatPortalTimestamp(item.delivered_at, zh)
                        : "—"}
                    </dd>
                  </div>
                </dl>
                {item.last_error && (
                  <p className="scheduled-reminder-error">
                    <strong>{zh ? "最后错误：" : "Last error: "}</strong>
                    {item.last_error}
                  </p>
                )}
                <footer>
                  <code>{item.id.slice(0, 12)}</code>
                  {!readOnly && ["pending", "processing"].includes(item.status) && (
                    <button
                      type="button"
                      className="paper-button danger-text"
                      onClick={() => void cancel(item)}
                    >
                      {zh ? "取消提醒" : "Cancel reminder"}
                    </button>
                  )}
                </footer>
              </article>
            ))}
            <nav
              className="library-pagination"
              style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}
            >
              <button
                type="button"
                className="paper-button"
                disabled={cursorHistory.length === 0 || loading}
                onClick={showNewer}
              >
                {zh ? "较新" : "Newer"}
              </button>
              <span>{page}</span>
              <button
                type="button"
                className="paper-button"
                disabled={!nextCursor || loading}
                onClick={showOlder}
              >
                {zh ? "较旧" : "Older"}
              </button>
            </nav>
          </>
        )}
      </div>
    </section>
  );
}
