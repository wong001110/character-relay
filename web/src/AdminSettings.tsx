import { useEffect, useState, type FormEvent } from "react";

import {
  api,
  type AdminRuntimeConfig,
  type AdminRuntimeView,
  type ProviderId,
  type RuntimeKind
} from "./api";
import { useI18n } from "./i18n";
import { getProviderPreset, providerPresets } from "./providerPresets";

interface Props {
  onClose: () => void;
  onUpdated: (view: AdminRuntimeView) => void;
}

export function AdminSettings({ onClose, onUpdated }: Props) {
  const { language, t } = useI18n();
  const [view, setView] = useState<AdminRuntimeView | null>(null);
  const [adaptiveKey, setAdaptiveKey] = useState("");
  const [judgeKey, setJudgeKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      setSaving(true);
      setMessage(null);
      const loaded = await api.getAdminRuntime();
      setView(loaded);
      onUpdated(loaded);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("admin.error"));
    } finally {
      setSaving(false);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!view) return;
    try {
      setSaving(true);
      setMessage(null);
      let next = await api.updateAdminRuntime(view.config);
      if (adaptiveKey.trim()) {
        next = await api.configureRuntimeCredential("adaptive", adaptiveKey.trim());
      }
      if (judgeKey.trim()) {
        next = await api.configureRuntimeCredential("judge", judgeKey.trim());
      }
      setAdaptiveKey("");
      setJudgeKey("");
      setView(next);
      onUpdated(next);
      setMessage(t("admin.saved"));
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("admin.error"));
    } finally {
      setSaving(false);
    }
  }

  function updateConfig(config: AdminRuntimeConfig) {
    setView((current) => (current ? { ...current, config } : current));
  }

  async function clearCredential(kind: RuntimeKind) {
    if (!view) return;
    try {
      setSaving(true);
      setMessage(null);
      const next = await api.clearRuntimeCredential(kind);
      setView(next);
      onUpdated(next);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("admin.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="admin-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="close-button" onClick={onClose} aria-label={t("creator.cancel")}>
          ×
        </button>
        <p className="tape-label">{t("admin.label")}</p>
        <h2 id="admin-title">{t("admin.heading")}</h2>
        <p className="creator-help">{t("admin.help")}</p>

        {!view ? (
          <div className="admin-login">
            <p>
              {language === "zh-CN"
                ? "管理员权限由当前登录 Session 验证，不再使用浏览器 Admin Token。"
                : "Admin access is verified by the signed-in Session. Browser Admin tokens are no longer used."}
            </p>
            <button className="ink-button" disabled={saving} onClick={() => void load()}>
              {saving ? t("admin.connecting") : t("admin.connect")}
            </button>
          </div>
        ) : (
          <form className="admin-runtime-form" onSubmit={save}>
            <section className="runtime-panel">
              <RuntimeHeader
                title={t("admin.adaptiveTitle")}
                configured={view.status.adaptive.configured}
                source={view.status.adaptive.credential_source}
              />
              <label className="runtime-toggle">
                <input
                  type="checkbox"
                  checked={view.config.adaptive.enabled}
                  onChange={(event) =>
                    updateConfig({
                      ...view.config,
                      adaptive: {
                        ...view.config.adaptive,
                        enabled: event.currentTarget.checked
                      }
                    })
                  }
                />
                {t("admin.enabled")}
              </label>
              <ProviderFields
                provider={view.config.adaptive.provider}
                baseUrl={view.config.adaptive.base_url}
                model={view.config.adaptive.model}
                onChange={(provider, baseUrl, model) =>
                  updateConfig({
                    ...view.config,
                    adaptive: {
                      ...view.config.adaptive,
                      provider,
                      base_url: baseUrl,
                      model
                    }
                  })
                }
              />
              <label className="wide">
                {t("admin.systemPrompt")}
                <textarea
                  rows={6}
                  value={view.config.adaptive.system_prompt}
                  onChange={(event) =>
                    updateConfig({
                      ...view.config,
                      adaptive: {
                        ...view.config.adaptive,
                        system_prompt: event.currentTarget.value
                      }
                    })
                  }
                />
              </label>
              <div className="runtime-number-grid">
                <label>
                  {t("admin.temperature")}
                  <input
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value={view.config.adaptive.temperature}
                    onChange={(event) =>
                      updateConfig({
                        ...view.config,
                        adaptive: {
                          ...view.config.adaptive,
                          temperature: Number(event.currentTarget.value)
                        }
                      })
                    }
                  />
                </label>
                <label>
                  {t("admin.maxTurns")}
                  <input
                    type="number"
                    min="2"
                    max="8"
                    value={view.config.adaptive.max_turns}
                    onChange={(event) =>
                      updateConfig({
                        ...view.config,
                        adaptive: {
                          ...view.config.adaptive,
                          max_turns: Number(event.currentTarget.value)
                        }
                      })
                    }
                  />
                </label>
              </div>
              <CredentialField
                value={adaptiveKey}
                onChange={setAdaptiveKey}
                source={view.status.adaptive.credential_source}
                onClear={() => void clearCredential("adaptive")}
              />
            </section>

            <section className="runtime-panel judge-runtime-panel">
              <RuntimeHeader
                title={t("admin.judgeTitle")}
                configured={view.status.judge.configured}
                source={view.status.judge.credential_source}
              />
              <label className="runtime-toggle">
                <input
                  type="checkbox"
                  checked={view.config.judge.enabled}
                  onChange={(event) =>
                    updateConfig({
                      ...view.config,
                      judge: {
                        ...view.config.judge,
                        enabled: event.currentTarget.checked
                      }
                    })
                  }
                />
                {t("admin.enabled")}
              </label>
              <ProviderFields
                provider={view.config.judge.provider}
                baseUrl={view.config.judge.base_url}
                model={view.config.judge.model}
                onChange={(provider, baseUrl, model) =>
                  updateConfig({
                    ...view.config,
                    judge: {
                      ...view.config.judge,
                      provider,
                      base_url: baseUrl,
                      model
                    }
                  })
                }
              />
              <label className="wide">
                {t("admin.systemPrompt")}
                <textarea
                  rows={6}
                  value={view.config.judge.system_prompt}
                  onChange={(event) =>
                    updateConfig({
                      ...view.config,
                      judge: {
                        ...view.config.judge,
                        system_prompt: event.currentTarget.value
                      }
                    })
                  }
                />
              </label>
              <div className="runtime-number-grid">
                <label>
                  {t("admin.temperature")}
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={view.config.judge.temperature}
                    onChange={(event) =>
                      updateConfig({
                        ...view.config,
                        judge: {
                          ...view.config.judge,
                          temperature: Number(event.currentTarget.value)
                        }
                      })
                    }
                  />
                </label>
                <label>
                  {t("admin.rubricVersion")}
                  <input
                    value={view.config.judge.rubric_version}
                    onChange={(event) =>
                      updateConfig({
                        ...view.config,
                        judge: {
                          ...view.config.judge,
                          rubric_version: event.currentTarget.value
                        }
                      })
                    }
                  />
                </label>
              </div>
              <CredentialField
                value={judgeKey}
                onChange={setJudgeKey}
                source={view.status.judge.credential_source}
                onClear={() => void clearCredential("judge")}
              />
            </section>

            <label className="default-judge-mode">
              {t("admin.defaultJudge")}
              <select
                value={view.config.default_judge_mode}
                onChange={(event) =>
                  updateConfig({
                    ...view.config,
                    default_judge_mode:
                      event.currentTarget.value as AdminRuntimeConfig["default_judge_mode"]
                  })
                }
              >
                <option value="rules">{t("judge.rules")}</option>
                <option value="semantic">{t("judge.semantic")}</option>
                <option value="hybrid">{t("judge.hybrid")}</option>
              </select>
            </label>

            <p className="admin-security-note">
              {language === "zh-CN"
                ? "Runtime API Key 会写入服务器端加密凭证库；浏览器不会保存原始 Key。"
                : "Runtime API keys are written to the server-side encrypted vault. The browser does not retain raw keys."}
            </p>
            <div className="form-actions">
              <button type="button" className="paper-button" onClick={onClose}>
                {t("creator.cancel")}
              </button>
              <button className="ink-button" disabled={saving}>
                {saving ? t("creator.saving") : t("admin.save")}
              </button>
            </div>
          </form>
        )}
        {message && (
          <p className={message === t("admin.saved") ? "success-note" : "error-note"}>
            {message}
          </p>
        )}
      </section>
    </div>
  );
}

function RuntimeHeader({
  title,
  configured,
  source
}: {
  title: string;
  configured: boolean;
  source: string;
}) {
  const { t } = useI18n();
  return (
    <div className="runtime-heading">
      <div>
        <span>{t("admin.runtime")}</span>
        <h3>{title}</h3>
      </div>
      <div className={configured ? "runtime-badge ready" : "runtime-badge missing"}>
        {configured ? t("admin.ready") : t("admin.missing")}
        <small>{source}</small>
      </div>
    </div>
  );
}

function ProviderFields({
  provider,
  baseUrl,
  model,
  onChange
}: {
  provider: ProviderId;
  baseUrl: string;
  model: string;
  onChange: (provider: ProviderId, baseUrl: string, model: string) => void;
}) {
  const { t } = useI18n();

  function choose(next: ProviderId) {
    const preset = getProviderPreset(next);
    onChange(next, preset.baseUrl, preset.defaultModel);
  }

  return (
    <div className="runtime-provider-grid">
      <label>
        {t("creator.provider")}
        <select
          value={provider}
          onChange={(event) => choose(event.currentTarget.value as ProviderId)}
        >
          {providerPresets.map((item) => (
            <option value={item.id} key={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("creator.modelId")}
        <input
          value={model}
          onChange={(event) => onChange(provider, baseUrl, event.currentTarget.value)}
        />
      </label>
      <label className="wide">
        {t("creator.baseUrl")}
        <input
          value={baseUrl}
          onChange={(event) => onChange(provider, event.currentTarget.value, model)}
        />
      </label>
    </div>
  );
}

function CredentialField({
  value,
  onChange,
  source,
  onClear
}: {
  value: string;
  onChange: (value: string) => void;
  source: string;
  onClear: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="runtime-credential-row">
      <label>
        {t("admin.apiKey")}
        <input
          type="password"
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
          placeholder={t("admin.apiKeyPlaceholder")}
          autoComplete="off"
        />
      </label>
      <div>
        <span className="status-chip">{source}</span>
        <button type="button" className="paper-button" onClick={onClear}>
          {t("admin.clearMemoryKey")}
        </button>
      </div>
    </div>
  );
}
