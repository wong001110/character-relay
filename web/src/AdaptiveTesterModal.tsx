import { useState, type FormEvent } from "react";

import type { AdaptiveTesterConfig, ProviderId } from "./api";
import { useI18n } from "./i18n";
import { getProviderPreset, providerPresets } from "./providerPresets";
import "./adaptive.css";

interface Props {
  initial: AdaptiveTesterConfig;
  onClose: () => void;
  onSave: (config: AdaptiveTesterConfig) => void;
}

export function AdaptiveTesterModal({ initial, onClose, onSave }: Props) {
  const { t } = useI18n();
  const [provider, setProvider] = useState<ProviderId>(initial.provider);
  const [baseUrl, setBaseUrl] = useState(initial.base_url);
  const [model, setModel] = useState(initial.model);
  const [systemPrompt, setSystemPrompt] = useState(initial.system_prompt);
  const [temperature, setTemperature] = useState(initial.temperature);
  const [maxTurns, setMaxTurns] = useState(initial.max_turns);
  const [apiKey, setApiKey] = useState("");

  function changeProvider(next: ProviderId) {
    const preset = getProviderPreset(next);
    setProvider(next);
    setBaseUrl(preset.baseUrl);
    setModel(preset.defaultModel);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSave({
      provider,
      base_url: baseUrl,
      model,
      system_prompt: systemPrompt,
      temperature,
      max_turns: maxTurns,
      api_key: apiKey
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="creator-sheet adaptive-tester-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adaptive-tester-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="close-button" onClick={onClose} aria-label={t("creator.cancel")}>×</button>
        <p className="tape-label">{t("adaptive.label")}</p>
        <h2 id="adaptive-tester-title">{t("adaptive.heading")}</h2>
        <p className="creator-help">{t("adaptive.help")}</p>

        <form className="adaptive-tester-form" onSubmit={submit}>
          <label>
            {t("adaptive.provider")}
            <select
              value={provider}
              onChange={(event) => changeProvider(event.currentTarget.value as ProviderId)}
            >
              {providerPresets.map((preset) => (
                <option value={preset.id} key={preset.id}>{preset.label}</option>
              ))}
            </select>
          </label>
          <label>
            {t("adaptive.modelId")}
            <input
              value={model}
              onChange={(event) => setModel(event.currentTarget.value)}
              required
              placeholder={t("adaptive.modelPlaceholder")}
            />
          </label>
          <label className="wide">
            {t("adaptive.baseUrl")}
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.currentTarget.value)}
              required
            />
          </label>
          <label>
            {t("adaptive.temperature")}
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={temperature}
              onChange={(event) => setTemperature(Number(event.currentTarget.value))}
              required
            />
          </label>
          <label>
            {t("adaptive.maxTurns")}
            <input
              type="number"
              min="2"
              max="8"
              value={maxTurns}
              onChange={(event) => setMaxTurns(Number(event.currentTarget.value))}
              required
            />
          </label>
          <label className="wide">
            {t("adaptive.systemPrompt")}
            <textarea
              rows={7}
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.currentTarget.value)}
              required
            />
          </label>
          <label className="wide">
            {t("adaptive.apiKey")}
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.currentTarget.value)}
              autoComplete="off"
              required
              placeholder={t("adaptive.apiKeyPlaceholder")}
            />
          </label>
          <p className="adaptive-security-note wide">{t("adaptive.security")}</p>
          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>
              {t("creator.cancel")}
            </button>
            <button className="ink-button">{t("adaptive.useNext")}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
