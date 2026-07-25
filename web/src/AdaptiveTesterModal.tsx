import { useState, type FormEvent } from "react";

import type { AdaptiveTesterConfig, ProviderId } from "./api";
import { getProviderPreset, providerPresets } from "./providerPresets";
import "./adaptive.css";

interface Props {
  initial: AdaptiveTesterConfig;
  onClose: () => void;
  onSave: (config: AdaptiveTesterConfig) => void;
}

export function AdaptiveTesterModal({ initial, onClose, onSave }: Props) {
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
        <button className="close-button" onClick={onClose} aria-label="Close">×</button>
        <p className="tape-label">Adaptive Tester</p>
        <h2 id="adaptive-tester-title">Configure the pressure agent.</h2>
        <p className="creator-help">
          This second AI reads only the scenario transcript and produces one follow-up at
          a time. Its API key is sent for the next run only and is never persisted.
        </p>

        <form className="adaptive-tester-form" onSubmit={submit}>
          <label>
            Provider
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
            Model ID
            <input
              value={model}
              onChange={(event) => setModel(event.currentTarget.value)}
              required
              placeholder="Tester model ID"
            />
          </label>
          <label className="wide">
            Base URL
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.currentTarget.value)}
              required
            />
          </label>
          <label>
            Temperature
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
            Maximum turns per room
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
            Tester system prompt
            <textarea
              rows={7}
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.currentTarget.value)}
              required
            />
          </label>
          <label className="wide">
            API key for the next run
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.currentTarget.value)}
              autoComplete="off"
              required
              placeholder="Cleared after the run is submitted"
            />
          </label>
          <p className="adaptive-security-note wide">
            The Adaptive Tester is separate from the Subject and Judge. Its key and prompt
            are not written to SQLite, trial events, Lab Notes, or JSON reports.
          </p>
          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>Cancel</button>
            <button className="ink-button">Use for next run</button>
          </div>
        </form>
      </section>
    </div>
  );
}
