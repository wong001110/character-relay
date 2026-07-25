import { useMemo, useState, type FormEvent } from "react";

import {
  api,
  type CharacterCard,
  type CharacterCardCreate,
  type PromptCharacterCreate,
  type ProviderId,
  type TargetView,
  type TestKind
} from "./api";
import { useI18n } from "./i18n";
import { getProviderPreset, providerPresets } from "./providerPresets";

interface Props {
  targets: TargetView[];
  onClose: () => void;
  onCreated: (card: CharacterCard) => void;
}

type BindingMode = "prompt" | "existing";

const allSuites: TestKind[] = [
  "identity_integrity",
  "false_memory",
  "prompt_injection",
  "long_conversation_drift"
];

const providerNoteKeys = {
  deepseek: "provider.note.deepseek",
  openai: "provider.note.openai",
  openrouter: "provider.note.openrouter",
  custom: "provider.note.custom"
} as const;

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function commonFields(data: FormData): Omit<CharacterCardCreate, "target_id"> {
  return {
    display_name: String(data.get("display_name")),
    subtitle: String(data.get("subtitle")),
    subject_type: String(data.get("subject_type")) as CharacterCard["subject_type"],
    persona_summary: String(data.get("persona_summary")),
    traits: splitList(String(data.get("traits"))),
    tags: splitList(String(data.get("tags"))),
    expected_tone: String(data.get("expected_tone")) || null,
    forbidden_behaviors: splitList(String(data.get("forbidden_behaviors"))),
    memory_summary: String(data.get("memory_summary")) || null,
    preferred_suites: allSuites,
    portrait_variant: String(data.get("portrait_variant")) as CharacterCard["portrait_variant"]
  };
}

export function CharacterCreator({ targets, onClose, onCreated }: Props) {
  const { t } = useI18n();
  const initialPreset = useMemo(() => getProviderPreset("deepseek"), []);
  const [bindingMode, setBindingMode] = useState<BindingMode>("prompt");
  const [provider, setProvider] = useState<ProviderId>("deepseek");
  const [baseUrl, setBaseUrl] = useState(initialPreset.baseUrl);
  const [model, setModel] = useState(initialPreset.defaultModel);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function changeProvider(nextProvider: ProviderId) {
    const preset = getProviderPreset(nextProvider);
    setProvider(nextProvider);
    setBaseUrl(preset.baseUrl);
    setModel(preset.defaultModel);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const common = commonFields(data);

    try {
      setSaving(true);
      setMessage(null);
      if (bindingMode === "prompt") {
        const payload: PromptCharacterCreate = {
          ...common,
          provider,
          base_url: baseUrl,
          model,
          system_prompt: String(data.get("system_prompt")),
          temperature: Number(data.get("temperature")),
          api_key: String(data.get("api_key"))
        };
        onCreated(await api.createPromptCharacter(payload));
      } else {
        const payload: CharacterCardCreate = {
          ...common,
          target_id: String(data.get("target_id"))
        };
        onCreated(await api.createCharacter(payload));
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("creator.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="creator-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="creator-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="close-button" onClick={onClose} aria-label={t("creator.cancel")}>
          ×
        </button>
        <p className="tape-label">{t("creator.label")}</p>
        <h2 id="creator-title">{t("creator.heading")}</h2>
        <p className="creator-help">{t("creator.help")}</p>

        <div className="binding-tabs" aria-label={t("creator.bindingAria")}>
          <button
            type="button"
            className={bindingMode === "prompt" ? "selected" : ""}
            onClick={() => setBindingMode("prompt")}
          >
            {t("creator.promptMode")}
            <small>{t("creator.promptModeHelp")}</small>
          </button>
          <button
            type="button"
            className={bindingMode === "existing" ? "selected" : ""}
            onClick={() => setBindingMode("existing")}
          >
            {t("creator.existingMode")}
            <small>{t("creator.existingModeHelp")}</small>
          </button>
        </div>

        <form className="creator-form" onSubmit={submit}>
          <label>
            {t("creator.displayName")}
            <input
              name="display_name"
              required
              placeholder={t("creator.displayNamePlaceholder")}
            />
          </label>
          <label>
            {t("creator.subtitle")}
            <input name="subtitle" placeholder={t("creator.subtitlePlaceholder")} />
          </label>

          {bindingMode === "prompt" ? (
            <div className="binding-panel wide">
              <div className="binding-heading">
                <div>
                  <span>{t("creator.aiConnection")}</span>
                  <strong>{t("creator.compatibleProvider")}</strong>
                </div>
                <small>{t("creator.keyMemoryOnly")}</small>
              </div>
              <div className="prompt-config-grid">
                <label>
                  {t("creator.provider")}
                  <select
                    value={provider}
                    onChange={(event) =>
                      changeProvider(event.currentTarget.value as ProviderId)
                    }
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
                    onChange={(event) => setModel(event.currentTarget.value)}
                    required
                    placeholder={t("creator.modelPlaceholder")}
                  />
                </label>
                <label className="wide">
                  {t("creator.baseUrl")}
                  <input
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.currentTarget.value)}
                    required
                    placeholder={t("creator.baseUrlPlaceholder")}
                  />
                </label>
                <label className="wide">
                  {t("creator.apiKey")}
                  <input
                    name="api_key"
                    type="password"
                    required
                    autoComplete="off"
                    placeholder={t("creator.apiKeyPlaceholder")}
                  />
                </label>
                <label className="wide">
                  {t("creator.systemPrompt")}
                  <textarea
                    name="system_prompt"
                    rows={6}
                    required
                    placeholder={t("creator.systemPromptPlaceholder")}
                  />
                </label>
                <label>
                  {t("creator.temperature")}
                  <input
                    name="temperature"
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    defaultValue="0.7"
                    required
                  />
                </label>
                <p className="provider-note">
                  {t(providerNoteKeys[provider])} {t("creator.keysNeverSaved")}
                </p>
              </div>
            </div>
          ) : (
            <label className="wide">
              {t("creator.targetBinding")}
              <select name="target_id" required defaultValue={targets[0]?.id}>
                {targets.map((target) => (
                  <option value={target.id} key={target.id}>
                    {target.name} · {target.target_kind}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label>
            {t("creator.subjectType")}
            <select name="subject_type" defaultValue="custom">
              <option value="companion">{t("subject.companion")}</option>
              <option value="npc">{t("subject.npc")}</option>
              <option value="assistant">{t("subject.assistant")}</option>
              <option value="custom">{t("subject.custom")}</option>
            </select>
          </label>
          <label>
            {t("creator.portraitPalette")}
            <select name="portrait_variant" defaultValue="lavender">
              <option value="lavender">{t("palette.lavender")}</option>
              <option value="rose">{t("palette.rose")}</option>
              <option value="mint">{t("palette.mint")}</option>
              <option value="night">{t("palette.night")}</option>
            </select>
          </label>
          <label className="wide">
            {t("creator.personaSummary")}
            <textarea
              name="persona_summary"
              rows={3}
              placeholder={t("creator.personaPlaceholder")}
            />
          </label>
          <label>
            {t("creator.traits")}
            <input name="traits" placeholder={t("creator.traitsPlaceholder")} />
          </label>
          <label>
            {t("creator.tags")}
            <input name="tags" placeholder={t("creator.tagsPlaceholder")} />
          </label>
          <label className="wide">
            {t("creator.expectedTone")}
            <input name="expected_tone" placeholder={t("creator.expectedTonePlaceholder")} />
          </label>
          <label className="wide">
            {t("creator.forbidden")}
            <input
              name="forbidden_behaviors"
              placeholder={t("creator.forbiddenPlaceholder")}
            />
          </label>
          <label className="wide">
            {t("creator.memoryNote")}
            <textarea
              name="memory_summary"
              rows={2}
              placeholder={t("creator.memoryPlaceholder")}
            />
          </label>

          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>
              {t("creator.cancel")}
            </button>
            <button
              className="ink-button"
              disabled={saving || (bindingMode === "existing" && targets.length === 0)}
            >
              {saving ? t("creator.saving") : t("creator.submit")}
            </button>
          </div>
          {message && <p className="error-note wide">{message}</p>}
        </form>
      </section>
    </div>
  );
}
