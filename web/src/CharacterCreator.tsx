import { useMemo, useState, type FormEvent } from "react";

import {
  api,
  type CharacterCard,
  type CharacterCardCreate,
  type CharacterCardUpdate,
  type PromptCharacterCreate,
  type ProviderId,
  type TargetView,
  type TestKind
} from "./api";
import { useI18n } from "./i18n";
import { getProviderPreset, providerPresets } from "./providerPresets";

interface Props {
  targets: TargetView[];
  card?: CharacterCard | null;
  target?: TargetView | null;
  onClose: () => void;
  onSaved: (card: CharacterCard) => void;
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

function configString(target: TargetView | null | undefined, key: string): string {
  const value = target?.config[key];
  return typeof value === "string" ? value : "";
}

function configNumber(
  target: TargetView | null | undefined,
  key: string,
  fallback: number
): number {
  const value = target?.config[key];
  return typeof value === "number" ? value : fallback;
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

export function CharacterCreator({
  targets,
  card = null,
  target = null,
  onClose,
  onSaved
}: Props) {
  const { t } = useI18n();
  const editing = Boolean(card);
  const userTargets = useMemo(
    () => targets.filter((item) => !item.id.startsWith("demo-")),
    [targets]
  );
  const initialPreset = useMemo(() => getProviderPreset("deepseek"), []);
  const initialBinding: BindingMode = target?.target_kind === "prompt_model" ? "prompt" : "existing";
  const initialProvider = (configString(target, "provider") || "deepseek") as ProviderId;
  const [bindingMode, setBindingMode] = useState<BindingMode>(
    editing ? initialBinding : "prompt"
  );
  const [provider, setProvider] = useState<ProviderId>(initialProvider);
  const [baseUrl, setBaseUrl] = useState(
    configString(target, "base_url") || initialPreset.baseUrl
  );
  const [model, setModel] = useState(
    configString(target, "model") || initialPreset.defaultModel
  );
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
      if (editing && card) {
        const payload: CharacterCardUpdate = {
          ...common,
          ...(target?.target_kind === "prompt_model"
            ? {
                provider,
                base_url: baseUrl,
                model,
                system_prompt: String(data.get("system_prompt")),
                temperature: Number(data.get("temperature"))
              }
            : {})
        };
        onSaved(await api.updateCharacter(card.id, payload));
      } else if (bindingMode === "prompt") {
        const payload: PromptCharacterCreate = {
          ...common,
          provider,
          base_url: baseUrl,
          model,
          system_prompt: String(data.get("system_prompt")),
          temperature: Number(data.get("temperature")),
          api_key: String(data.get("api_key"))
        };
        onSaved(await api.createPromptCharacter(payload));
      } else {
        const payload: CharacterCardCreate = {
          ...common,
          target_id: String(data.get("target_id"))
        };
        onSaved(await api.createCharacter(payload));
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("creator.error"));
    } finally {
      setSaving(false);
    }
  }

  const promptFields = bindingMode === "prompt" || target?.target_kind === "prompt_model";

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
        <p className="tape-label">
          {editing ? t("creator.editLabel") : t("creator.label")}
        </p>
        <h2 id="creator-title">
          {editing ? t("creator.editHeading") : t("creator.heading")}
        </h2>
        <p className="creator-help">
          {editing ? t("creator.editHelp") : t("creator.help")}
        </p>

        {!editing && (
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
              disabled={userTargets.length === 0}
            >
              {t("creator.existingMode")}
              <small>{t("creator.existingModeHelp")}</small>
            </button>
          </div>
        )}

        <form className="creator-form" onSubmit={submit}>
          <label>
            {t("creator.displayName")}
            <input
              name="display_name"
              required
              defaultValue={card?.display_name ?? ""}
              placeholder={t("creator.displayNamePlaceholder")}
            />
          </label>
          <label>
            {t("creator.subtitle")}
            <input
              name="subtitle"
              defaultValue={card?.subtitle ?? ""}
              placeholder={t("creator.subtitlePlaceholder")}
            />
          </label>

          {promptFields ? (
            <div className="binding-panel wide">
              <div className="binding-heading">
                <div>
                  <span>{t("creator.aiConnection")}</span>
                  <strong>{t("creator.compatibleProvider")}</strong>
                </div>
                <small>
                  {editing ? t("creator.editKeyPreserved") : t("creator.keyMemoryOnly")}
                </small>
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
                {!editing && (
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
                )}
                <label className="wide">
                  {t("creator.systemPrompt")}
                  <textarea
                    name="system_prompt"
                    rows={8}
                    required
                    defaultValue={configString(target, "system_prompt")}
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
                    defaultValue={configNumber(target, "temperature", 0.7)}
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
              {editing ? (
                <input value={target?.name ?? card?.target_id ?? ""} disabled />
              ) : (
                <select name="target_id" required defaultValue={userTargets[0]?.id}>
                  {userTargets.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.name} · {item.target_kind}
                    </option>
                  ))}
                </select>
              )}
            </label>
          )}

          <label>
            {t("creator.subjectType")}
            <select name="subject_type" defaultValue={card?.subject_type ?? "custom"}>
              <option value="companion">{t("subject.companion")}</option>
              <option value="npc">{t("subject.npc")}</option>
              <option value="assistant">{t("subject.assistant")}</option>
              <option value="custom">{t("subject.custom")}</option>
            </select>
          </label>
          <label>
            {t("creator.portraitPalette")}
            <select
              name="portrait_variant"
              defaultValue={card?.portrait_variant ?? "lavender"}
            >
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
              defaultValue={card?.persona_summary ?? ""}
              placeholder={t("creator.personaPlaceholder")}
            />
          </label>
          <label>
            {t("creator.traits")}
            <input
              name="traits"
              defaultValue={card?.traits.join(", ") ?? ""}
              placeholder={t("creator.traitsPlaceholder")}
            />
          </label>
          <label>
            {t("creator.tags")}
            <input
              name="tags"
              defaultValue={card?.tags.join(", ") ?? ""}
              placeholder={t("creator.tagsPlaceholder")}
            />
          </label>
          <label className="wide">
            {t("creator.expectedTone")}
            <input
              name="expected_tone"
              defaultValue={card?.expected_tone ?? ""}
              placeholder={t("creator.expectedTonePlaceholder")}
            />
          </label>
          <label className="wide">
            {t("creator.forbidden")}
            <input
              name="forbidden_behaviors"
              defaultValue={card?.forbidden_behaviors.join(", ") ?? ""}
              placeholder={t("creator.forbiddenPlaceholder")}
            />
          </label>
          <label className="wide">
            {t("creator.memoryNote")}
            <textarea
              name="memory_summary"
              rows={2}
              defaultValue={card?.memory_summary ?? ""}
              placeholder={t("creator.memoryPlaceholder")}
            />
          </label>

          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>
              {t("creator.cancel")}
            </button>
            <button
              className="ink-button"
              disabled={saving || (!editing && bindingMode === "existing" && userTargets.length === 0)}
            >
              {saving
                ? t("creator.saving")
                : editing
                  ? t("creator.saveChanges")
                  : t("creator.submit")}
            </button>
          </div>
          {message && <p className="error-note wide">{message}</p>}
        </form>
      </section>
    </div>
  );
}
