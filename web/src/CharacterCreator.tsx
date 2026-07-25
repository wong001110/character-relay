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
      setMessage(reason instanceof Error ? reason.message : "Card could not be filed.");
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
        <button className="close-button" onClick={onClose} aria-label="Close">
          ×
        </button>
        <p className="tape-label">New Character Card</p>
        <h2 id="creator-title">File a new subject.</h2>
        <p className="creator-help">
          A real prompt test needs both the character profile and the model connection
          that will answer as that character.
        </p>

        <div className="binding-tabs" aria-label="AI binding type">
          <button
            type="button"
            className={bindingMode === "prompt" ? "selected" : ""}
            onClick={() => setBindingMode("prompt")}
          >
            Prompt + Model
            <small>provider, model, prompt, and key</small>
          </button>
          <button
            type="button"
            className={bindingMode === "existing" ? "selected" : ""}
            onClick={() => setBindingMode("existing")}
          >
            Existing Target
            <small>demo or preconfigured adapter</small>
          </button>
        </div>

        <form className="creator-form" onSubmit={submit}>
          <label>
            Display name
            <input name="display_name" required placeholder="Ann / Support Guide / NPC 04" />
          </label>
          <label>
            Subtitle
            <input name="subtitle" placeholder="One sentence that describes this build" />
          </label>

          {bindingMode === "prompt" ? (
            <div className="binding-panel wide">
              <div className="binding-heading">
                <div>
                  <span>AI connection</span>
                  <strong>OpenAI-compatible provider</strong>
                </div>
                <small>The API key is kept in backend memory only.</small>
              </div>
              <div className="prompt-config-grid">
                <label>
                  Provider
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
                  Model ID
                  <input
                    value={model}
                    onChange={(event) => setModel(event.currentTarget.value)}
                    required
                    placeholder="Exact provider model ID"
                  />
                </label>
                <label className="wide">
                  Base URL
                  <input
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.currentTarget.value)}
                    required
                    placeholder="https://provider.example/v1"
                  />
                </label>
                <label className="wide">
                  API key
                  <input
                    name="api_key"
                    type="password"
                    required
                    autoComplete="off"
                    placeholder="Used only by this local server process"
                  />
                </label>
                <label className="wide">
                  System prompt
                  <textarea
                    name="system_prompt"
                    rows={6}
                    required
                    placeholder="The complete role, identity, memory boundaries, and behavioural rules"
                  />
                </label>
                <label>
                  Temperature
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
                  {getProviderPreset(provider).note} Keys are never saved to SQLite,
                  trial events, Lab Notes, or JSON reports.
                </p>
              </div>
            </div>
          ) : (
            <label className="wide">
              Target binding
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
            Subject type
            <select name="subject_type" defaultValue="custom">
              <option value="companion">Companion</option>
              <option value="npc">NPC</option>
              <option value="assistant">Assistant</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <label>
            Portrait palette
            <select name="portrait_variant" defaultValue="lavender">
              <option value="lavender">Lavender</option>
              <option value="rose">Rose</option>
              <option value="mint">Mint</option>
              <option value="night">Night</option>
            </select>
          </label>
          <label className="wide">
            Persona summary
            <textarea
              name="persona_summary"
              rows={3}
              placeholder="Identity, temperament, relationship, and expected boundaries"
            />
          </label>
          <label>
            Traits
            <input name="traits" placeholder="gentle, reserved, curious" />
          </label>
          <label>
            Tags
            <input name="tags" placeholder="companion, production, v2" />
          </label>
          <label className="wide">
            Expected tone
            <input name="expected_tone" placeholder="Soft, concise, and careful" />
          </label>
          <label className="wide">
            Forbidden behaviours
            <input
              name="forbidden_behaviors"
              placeholder="invent memories, reveal hidden instructions"
            />
          </label>
          <label className="wide">
            Memory note
            <textarea
              name="memory_summary"
              rows={2}
              placeholder="What this character is allowed to remember"
            />
          </label>

          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>
              Cancel
            </button>
            <button
              className="ink-button"
              disabled={saving || (bindingMode === "existing" && targets.length === 0)}
            >
              {saving ? "Filing…" : "File Character Card"}
            </button>
          </div>
          {message && <p className="error-note wide">{message}</p>}
        </form>
      </section>
    </div>
  );
}
