import { useEffect, useMemo, useState } from "react";

import {
  deploymentPresenceApi,
  type DeploymentPresenceRhythmView
} from "./deploymentPresenceApi";
import "./deployment-presence.css";

interface Props {
  deploymentId: string;
  disabled?: boolean;
  zh: boolean;
}

function minuteToClock(value: number): string {
  const minute = Math.max(0, Math.min(1439, Math.round(value)));
  const hour = Math.floor(minute / 60);
  const rest = minute % 60;
  return `${String(hour).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function clockToMinute(value: string): number {
  const [hourRaw, minuteRaw] = value.split(":");
  const hour = Number(hourRaw);
  const minute = Number(minuteRaw);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    throw new Error("Invalid sleep start time.");
  }
  return hour * 60 + minute;
}

function hoursLabel(minutes: number): string {
  const value = minutes / 60;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function scheduleInstant(value: string): number {
  const hasZone = /(?:Z|[+-]\d{2}:\d{2})$/iu.test(value);
  return Date.parse(hasZone ? value : `${value}Z`);
}

function scheduleStamp(value: string | null, timezone: string, zh: boolean): string {
  if (!value) return "—";
  const parsed = scheduleInstant(value);
  if (Number.isNaN(parsed)) return value;
  try {
    return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
      dateStyle: "medium",
      timeStyle: "short",
      ...(timezone ? { timeZone: timezone } : {})
    }).format(parsed);
  } catch {
    return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
      dateStyle: "medium",
      timeStyle: "short"
    }).format(parsed);
  }
}

export function DeploymentDailyRhythmPanel({ deploymentId, disabled = false, zh }: Props) {
  const [rhythm, setRhythm] = useState<DeploymentPresenceRhythmView | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [sleepStart, setSleepStart] = useState("01:00");
  const [minHours, setMinHours] = useState("7");
  const [maxHours, setMaxHours] = useState("9");
  const [variation, setVariation] = useState("45");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    deploymentPresenceApi
      .getRhythm(deploymentId)
      .then((value) => {
        if (!active) return;
        setRhythm(value);
        setEnabled(value.enabled);
        setSleepStart(minuteToClock(value.preferred_sleep_start_minute));
        setMinHours(hoursLabel(value.sleep_duration_min_minutes));
        setMaxHours(hoursLabel(value.sleep_duration_max_minutes));
        setVariation(String(value.variation_minutes));
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [deploymentId]);

  const dirty = useMemo(() => {
    if (!rhythm) return false;
    const min = Number(minHours);
    const max = Number(maxHours);
    const variationMinutes = Number(variation);
    let start = rhythm.preferred_sleep_start_minute;
    try {
      start = clockToMinute(sleepStart);
    } catch {
      return true;
    }
    return (
      enabled !== rhythm.enabled ||
      start !== rhythm.preferred_sleep_start_minute ||
      Math.round(min * 60) !== rhythm.sleep_duration_min_minutes ||
      Math.round(max * 60) !== rhythm.sleep_duration_max_minutes ||
      Math.round(variationMinutes) !== rhythm.variation_minutes
    );
  }, [enabled, maxHours, minHours, rhythm, sleepStart, variation]);

  async function save() {
    if (saving || disabled) return;
    try {
      setSaving(true);
      setSaved(false);
      setError("");
      const startMinute = clockToMinute(sleepStart);
      const min = Number(minHours);
      const max = Number(maxHours);
      const variationMinutes = Number(variation);
      if (!Number.isFinite(min) || min < 1 || min > 16) {
        throw new Error(zh ? "最短睡眠需介于 1–16 小时。" : "Minimum sleep must be between 1 and 16 hours.");
      }
      if (!Number.isFinite(max) || max < min || max > 16) {
        throw new Error(zh ? "最长睡眠需不短于最短值，且不超过 16 小时。" : "Maximum sleep must be at least the minimum and no more than 16 hours.");
      }
      if (!Number.isFinite(variationMinutes) || variationMinutes < 0 || variationMinutes > 180) {
        throw new Error(zh ? "时间浮动需介于 0–180 分钟。" : "Variation must be between 0 and 180 minutes.");
      }
      const next = await deploymentPresenceApi.updateRhythm(deploymentId, {
        enabled,
        preferred_sleep_start_minute: startMinute,
        sleep_duration_min_minutes: Math.round(min * 60),
        sleep_duration_max_minutes: Math.round(max * 60),
        variation_minutes: Math.round(variationMinutes)
      });
      setRhythm(next);
      setEnabled(next.enabled);
      setSleepStart(minuteToClock(next.preferred_sleep_start_minute));
      setMinHours(hoursLabel(next.sleep_duration_min_minutes));
      setMaxHours(hoursLabel(next.sleep_duration_max_minutes));
      setVariation(String(next.variation_minutes));
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="deployment-form-wide daily-rhythm-sheet">
      <div className="deployment-form-divider daily-rhythm-heading">
        <div>
          <strong>{zh ? "日常作息 / Daily Rhythm" : "Daily Rhythm"}</strong>
          <span>
            {zh
              ? "为这个 Deployment 设置持久化睡眠节奏。时间跟随 Server 时区；睡眠中会暂停角色 Runtime 与 Discovery。"
              : "Give this Deployment a persisted sleep rhythm. Scheduling follows the Server timezone; sleeping pauses character runtime and Discovery."}
          </span>
        </div>
        <label className="daily-rhythm-toggle">
          <input
            type="checkbox"
            checked={enabled}
            disabled={disabled || loading || saving}
            onChange={(event) => {
              setEnabled(event.target.checked);
              setSaved(false);
            }}
          />
          <span>{enabled ? (zh ? "已启用" : "Enabled") : zh ? "已关闭" : "Off"}</span>
        </label>
      </div>

      {loading ? (
        <small>{zh ? "读取作息设置…" : "Loading rhythm settings…"}</small>
      ) : (
        <>
          <div className={`daily-rhythm-grid${enabled ? "" : " is-disabled"}`}>
            <label>
              <span>{zh ? "偏好每日入睡时间" : "Preferred daily sleep time"}</span>
              <input
                type="time"
                value={sleepStart}
                disabled={disabled || saving}
                onChange={(event) => {
                  setSleepStart(event.target.value);
                  setSaved(false);
                }}
              />
              <small>
                {zh
                  ? "这是每天重复的偏好时刻，不是只限今天；若今天的时刻已过，会安排下一次，并套用每日时间浮动。"
                  : "This is a recurring daily preference, not a today-only time. If today's occurrence has passed, the next one is scheduled with the daily variation applied."}
              </small>
            </label>
            <label>
              <span>{zh ? "睡眠时长范围" : "Sleep duration range"}</span>
              <span className="daily-rhythm-range">
                <input
                  type="number"
                  min="1"
                  max="16"
                  step="0.5"
                  value={minHours}
                  disabled={disabled || saving}
                  onChange={(event) => {
                    setMinHours(event.target.value);
                    setSaved(false);
                  }}
                />
                <em>–</em>
                <input
                  type="number"
                  min="1"
                  max="16"
                  step="0.5"
                  value={maxHours}
                  disabled={disabled || saving}
                  onChange={(event) => {
                    setMaxHours(event.target.value);
                    setSaved(false);
                  }}
                />
                <small>{zh ? "小时" : "hours"}</small>
              </span>
            </label>
            <label>
              <span>{zh ? "每日时间浮动" : "Daily variation"}</span>
              <span className="daily-rhythm-range single">
                <input
                  type="number"
                  min="0"
                  max="180"
                  step="5"
                  value={variation}
                  disabled={disabled || saving}
                  onChange={(event) => {
                    setVariation(event.target.value);
                    setSaved(false);
                  }}
                />
                <small>{zh ? "分钟" : "minutes"}</small>
              </span>
            </label>
          </div>

          {rhythm && (
            <dl className="daily-rhythm-preview">
              <div>
                <dt>{zh ? "Server 时区" : "Server timezone"}</dt>
                <dd>{rhythm.schedule_timezone || (zh ? "启用后计算" : "Calculated when enabled")}</dd>
              </div>
              <div>
                <dt>{zh ? "下一次计划入睡" : "Next scheduled sleep"}</dt>
                <dd>{scheduleStamp(rhythm.scheduled_sleep_at, rhythm.schedule_timezone, zh)}</dd>
              </div>
              <div>
                <dt>{zh ? "下一次计划醒来" : "Next scheduled wake"}</dt>
                <dd>{scheduleStamp(rhythm.scheduled_wake_at, rhythm.schedule_timezone, zh)}</dd>
              </div>
              <div>
                <dt>{zh ? "下一次状态变化" : "Next transition"}</dt>
                <dd>
                  {rhythm.next_state ? `${rhythm.next_state} · ` : ""}
                  {scheduleStamp(rhythm.next_transition_at, rhythm.schedule_timezone, zh)}
                </dd>
              </div>
            </dl>
          )}

          {error && <small className="deployment-inline-error">{error}</small>}
          <div className="daily-rhythm-actions">
            <small>
              {saved
                ? zh
                  ? "已保存并重新计算当前计划。"
                  : "Saved and current schedule recalculated."
                : dirty
                  ? zh
                    ? "有尚未保存的更改。"
                    : "Unsaved changes."
                  : zh
                    ? "当前设置已保存。"
                    : "Current settings are saved."}
            </small>
            <button
              type="button"
              className="paper-button"
              disabled={disabled || saving || !dirty}
              onClick={() => void save()}
            >
              {saving ? (zh ? "保存中…" : "Saving…") : zh ? "保存作息" : "Save rhythm"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
