import { useState, type FormEvent } from "react";

import {
  api,
  type CharacterCard,
  type CharacterCardCreate,
  type TargetView,
  type TestKind
} from "./api";

interface Props {
  targets: TargetView[];
  onClose: () => void;
  onCreated: (card: CharacterCard) => void;
}

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

export function CharacterCreator({ targets, onClose, onCreated }: Props) {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload: CharacterCardCreate = {
      target_id: String(data.get("target_id")),
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
      portrait_variant: String(
        data.get("portrait_variant")
      ) as CharacterCard["portrait_variant"]
    };
    try {
      setSaving(true);
      onCreated(await api.createCharacter(payload));
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
          The card holds the character-facing profile. Its target binding still keeps
          credentials and technical execution separate.
        </p>
        <form className="creator-form" onSubmit={submit}>
          <label>
            Display name
            <input name="display_name" required placeholder="Ann / Support Guide / NPC 04" />
          </label>
          <label>
            Subtitle
            <input name="subtitle" placeholder="One sentence that describes this build" />
          </label>
          <label>
            Target binding
            <select name="target_id" required defaultValue={targets[0]?.id}>
              {targets.map((target) => (
                <option value={target.id} key={target.id}>
                  {target.name} · {target.target_kind}
                </option>
              ))}
            </select>
          </label>
          <label>
            Subject type
            <select name="subject_type" defaultValue="custom">
              <option value="companion">Companion</option>
              <option value="npc">NPC</option>
              <option value="assistant">Assistant</option>
              <option value="custom">Custom</option>
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
          <label>
            Portrait palette
            <select name="portrait_variant" defaultValue="lavender">
              <option value="lavender">Lavender</option>
              <option value="rose">Rose</option>
              <option value="mint">Mint</option>
              <option value="night">Night</option>
            </select>
          </label>
          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>
              Cancel
            </button>
            <button className="ink-button" disabled={saving || targets.length === 0}>
              {saving ? "Filing…" : "File Character Card"}
            </button>
          </div>
          {message && <p className="error-note wide">{message}</p>}
        </form>
      </section>
    </div>
  );
}
