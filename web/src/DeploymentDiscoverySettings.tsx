import { useEffect, useState } from "react";

import {
  discoveryApi,
  type DiscoveryMode,
  type DiscoveryProfile
} from "./discoveryApi";

interface Props {
  deploymentId: string;
  disabled?: boolean;
  zh: boolean;
}

const emptyProfile = (deploymentId: string): DiscoveryProfile => ({
  deployment_id: deploymentId,
  mode: "off",
  youtube_enabled: false,
  bilibili_enabled: false,
  bilibili_experimental_available: false,
  auto_share_enabled: false,
  auto_global_enabled: false,
  daily_share_budget: 1,
  share_cooldown_minutes: 180
});

function mutableProfile(profile: DiscoveryProfile) {
  return {
    mode: profile.mode,
    youtube_enabled: profile.youtube_enabled,
    bilibili_enabled: profile.bilibili_enabled,
    auto_share_enabled: profile.auto_share_enabled,
    daily_share_budget: profile.daily_share_budget,
    share_cooldown_minutes: profile.share_cooldown_minutes
  };
}

function sameProfile(left: DiscoveryProfile, right: DiscoveryProfile): boolean {
  return JSON.stringify(mutableProfile(left)) === JSON.stringify(mutableProfile(right));
}

export function DeploymentDiscoverySettings({
  deploymentId,
  disabled = false,
  zh
}: Props) {
  const [persisted, setPersisted] = useState<DiscoveryProfile>(() => emptyProfile(deploymentId));
  const [draft, setDraft] = useState<DiscoveryProfile>(() => emptyProfile(deploymentId));
  const [lastEnabledMode, setLastEnabledMode] =
    useState<Exclude<DiscoveryMode, "off">>("shadow");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedNote, setSavedNote] = useState("");

  const dirty = !sameProfile(persisted, draft);
  const enabled = draft.mode !== "off";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setSavedNote("");
    discoveryApi
      .profile(deploymentId)
      .then((profile) => {
        if (!active) return;
        setPersisted(profile);
        setDraft(profile);
        if (profile.mode !== "off") setLastEnabledMode(profile.mode);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [deploymentId]);

  function patch(values: Partial<DiscoveryProfile>) {
    setDraft((current) => ({ ...current, ...values }));
    setSavedNote("");
  }

  function toggleEnabled() {
    if (enabled) {
      if (draft.mode !== "off") setLastEnabledMode(draft.mode);
      patch({ mode: "off" });
    } else {
      patch({ mode: lastEnabledMode });
    }
  }

  function setMode(mode: Exclude<DiscoveryMode, "off">) {
    setLastEnabledMode(mode);
    patch({ mode });
  }

  async function saveChanges() {
    if (!dirty) return;
    try {
      setSaving(true);
      setError("");
      const saved = await discoveryApi.updateProfile(deploymentId, draft);
      setPersisted(saved);
      setDraft(saved);
      if (saved.mode !== "off") setLastEnabledMode(saved.mode);
      setSavedNote(
        zh
          ? "Discovery 权限已保存。浏览历史与判断请到 Intelligence → Discovery 查看。"
          : "Discovery policy saved. Inspect browsing history and decisions in Intelligence → Discovery."
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="deployment-form-wide discovery-settings-sheet">
      <div className="deployment-form-divider discovery-settings-heading">
        <div>
          <strong>{zh ? "角色探索 / Discovery Policy" : "Character Discovery / Policy"}</strong>
          <span>
            {zh
              ? "这里只决定这个 Deployment 是否能浏览、允许哪些来源，以及分享权限。运行证据已移到 Intelligence。"
              : "This editor only controls whether this Deployment may browse, which sources are allowed, and sharing policy. Runtime evidence now lives in Intelligence."}
          </span>
        </div>
        <label className="discovery-master-toggle">
          <input
            type="checkbox"
            checked={enabled}
            disabled={disabled || loading || saving}
            onChange={toggleEnabled}
          />
          <strong>{enabled ? "ON" : "OFF"}</strong>
        </label>
      </div>

      {error && <small className="deployment-inline-error">{error}</small>}

      <div className={`discovery-settings-grid${enabled ? "" : " is-disabled"}`}>
        <fieldset disabled={!enabled || disabled || loading || saving}>
          <legend>{zh ? "允许来源" : "Allowed sources"}</legend>
          <label>
            <input
              type="checkbox"
              checked={draft.youtube_enabled}
              onChange={() => patch({ youtube_enabled: !draft.youtube_enabled })}
            />
            <span>YouTube</span>
          </label>
          <label>
            <input
              type="checkbox"
              checked={draft.bilibili_enabled}
              disabled={!draft.bilibili_experimental_available}
              onChange={() => patch({ bilibili_enabled: !draft.bilibili_enabled })}
            />
            <span>Bilibili <em>EXPERIMENTAL</em></span>
          </label>
          {!draft.bilibili_experimental_available && (
            <small>
              {zh
                ? "Bilibili 被系统级 Experimental 开关禁用。"
                : "Bilibili is disabled by the system Experimental gate."}
            </small>
          )}
        </fieldset>

        <fieldset disabled={!enabled || disabled || loading || saving}>
          <legend>{zh ? "分享行为" : "Sharing behavior"}</legend>
          {(["shadow", "review", "auto"] as const).map((mode) => (
            <label key={mode}>
              <input
                type="radio"
                name={`discovery-mode-${deploymentId}`}
                checked={draft.mode === mode}
                onChange={() => setMode(mode)}
              />
              <span>{mode.toUpperCase()}</span>
            </label>
          ))}
          {draft.mode === "auto" && (
            <label>
              <input
                type="checkbox"
                checked={draft.auto_share_enabled}
                onChange={() => patch({ auto_share_enabled: !draft.auto_share_enabled })}
              />
              <span>{zh ? "允许此 Deployment AUTO 分享" : "Allow AUTO for this Deployment"}</span>
              {!draft.auto_global_enabled && (
                <small>{zh ? "全局 AUTO 仍关闭" : "Global AUTO remains disabled"}</small>
              )}
            </label>
          )}
        </fieldset>

        <fieldset disabled={!enabled || disabled || loading || saving}>
          <legend>{zh ? "分享限制" : "Share limits"}</legend>
          <label>
            <span>{zh ? "每日预算" : "Daily budget"}</span>
            <input
              type="number"
              min={0}
              max={8}
              value={draft.daily_share_budget}
              onChange={(event) => patch({ daily_share_budget: Number(event.currentTarget.value) })}
            />
          </label>
          <label>
            <span>{zh ? "冷却（分钟）" : "Cooldown (minutes)"}</span>
            <input
              type="number"
              min={15}
              max={1440}
              value={draft.share_cooldown_minutes}
              onChange={(event) => patch({ share_cooldown_minutes: Number(event.currentTarget.value) })}
            />
          </label>
        </fieldset>
      </div>

      <div className="discovery-settings-actions">
        <div>
          <small>
            {zh ? "已保存运行状态：" : "Persisted runtime: "}
            {persisted.mode.toUpperCase()}
          </small>
        </div>
        <div>
          {dirty && (
            <button
              type="button"
              className="text-button"
              disabled={saving}
              onClick={() => {
                setDraft(persisted);
                setSavedNote("");
                setError("");
              }}
            >
              {zh ? "撤销修改" : "Discard changes"}
            </button>
          )}
          <button
            type="button"
            className="ink-button"
            disabled={!dirty || disabled || loading || saving}
            onClick={() => void saveChanges()}
          >
            {saving ? (zh ? "保存中…" : "Saving…") : (zh ? "保存 Discovery 设置" : "Save Discovery settings")}
          </button>
        </div>
      </div>
      {savedNote && <p className="success-note">{savedNote}</p>}
    </section>
  );
}
