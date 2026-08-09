import { useEffect, useMemo, useState } from "react";

import { useI18n } from "./i18n";
import {
  schedulerApi,
  type ScheduledReminder,
  type ScheduledReminderStatus
} from "./schedulerApi";
import "./scheduled-reminders.css";

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
  const [status, setStatus] = useState<ScheduledReminderStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setLoading(true);
      const result = await schedulerApi.list({ status, limit: 200 });
      setItems(result.items);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [status]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, status]);

  const counts = useMemo(() => {
    const result: Record<ScheduledReminderStatus, number> = {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
      cancelled: 0
    };
    for (const item of items) result[item.status] += 1;
    return result;
  }, [items]);

  async function cancel(item: ScheduledReminder) {
    const confirmed = window.confirm(
      zh
        ? `取消 ${item.character_name} 的提醒？\n${item.reminder_text}`
        : `Cancel ${item.character_name}'s reminder?\n${item.reminder_text}`
    );
    if (!confirmed) return;
    try {
      await schedulerApi.cancel(item.id);
      await load();
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
              ? "只有出现在这里的记录才代表 scheduler.remind 已实际执行并写入 Runtime；角色口头说“会提醒”不算成功。"
              : "A reminder is real only after scheduler.remind executed and a record appears here. A character promise alone is not confirmation."}
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
        <button type="button" className="paper-button" onClick={() => void load()}>
          {loading ? (zh ? "读取中…" : "Loading…") : zh ? "刷新" : "Refresh"}
        </button>
        <label className="scheduled-reminders-auto-refresh">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(event) => setAutoRefresh(event.currentTarget.checked)}
          />
          {zh ? "每 5 秒刷新" : "Refresh every 5 seconds"}
        </label>
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
        {!loading && items.length === 0 ? (
          <div className="scheduled-reminders-empty">
            <strong>{zh ? "目前没有提醒记录" : "No reminder records"}</strong>
            <p>
              {zh
                ? "测试 scheduler.remind 后，这里会显示计划时间、角色、状态与失败原因。"
                : "After scheduler.remind runs, this view shows schedule time, character, status, and failures."}
            </p>
          </div>
        ) : (
          items.map((item) => (
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
                  <dd>{new Date(item.scheduled_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt>{zh ? "建立时间" : "Created"}</dt>
                  <dd>{new Date(item.created_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt>{zh ? "尝试次数" : "Attempts"}</dt>
                  <dd>{item.attempt_count}</dd>
                </div>
                <div>
                  <dt>{zh ? "送达时间" : "Delivered"}</dt>
                  <dd>{item.delivered_at ? new Date(item.delivered_at).toLocaleString() : "—"}</dd>
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
          ))
        )}
      </div>
    </section>
  );
}
