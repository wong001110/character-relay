import { useState, type FormEvent } from "react";

import { api, type CharacterCard, type CredentialStatus, type TargetView } from "./api";

interface Props {
  card: CharacterCard;
  target: TargetView;
  onClose: () => void;
  onConfigured: (status: CredentialStatus) => void;
}

export function CredentialModal({ card, target, onClose, onConfigured }: Props) {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const provider = String(target.config.provider ?? "OpenAI-compatible");
  const model = String(target.config.model ?? "Unspecified model");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      setSaving(true);
      setMessage(null);
      const status = await api.configureCredential(card.id, String(data.get("api_key")));
      onConfigured(status);
      onClose();
    } catch (reason) {
      setMessage(
        reason instanceof Error ? reason.message : "The provider key could not be stored."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="credential-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="credential-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="close-button" onClick={onClose} aria-label="Close">
          ×
        </button>
        <p className="tape-label">AI Connection</p>
        <h2 id="credential-title">Configure {card.display_name}</h2>
        <div className="connection-summary">
          <div><span>Provider</span><strong>{provider}</strong></div>
          <div><span>Model</span><strong>{model}</strong></div>
        </div>
        <form onSubmit={submit}>
          <label>
            API key
            <input
              name="api_key"
              type="password"
              required
              autoComplete="off"
              placeholder="Stored only in this backend process"
            />
          </label>
          <p className="secret-note">
            The raw key is not written to SQLite, Character Cards, trial events,
            Lab Notes, JSON reports, or logs. Restarting the server clears it.
          </p>
          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>Cancel</button>
            <button className="ink-button" disabled={saving}>
              {saving ? "Connecting…" : "Save for this session"}
            </button>
          </div>
          {message && <p className="error-note">{message}</p>}
        </form>
      </section>
    </div>
  );
}
