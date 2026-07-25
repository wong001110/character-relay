import { useState, type FormEvent } from "react";

import { api, type CharacterCard, type CredentialStatus, type TargetView } from "./api";
import { useI18n } from "./i18n";

interface Props {
  card: CharacterCard;
  target: TargetView;
  onClose: () => void;
  onConfigured: (status: CredentialStatus) => void;
}

export function CredentialModal({ card, target, onClose, onConfigured }: Props) {
  const { t } = useI18n();
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
      setMessage(reason instanceof Error ? reason.message : t("credential.error"));
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
        <button className="close-button" onClick={onClose} aria-label={t("creator.cancel")}>
          ×
        </button>
        <p className="tape-label">{t("credential.label")}</p>
        <h2 id="credential-title">{t("credential.configure", { name: card.display_name })}</h2>
        <div className="connection-summary">
          <div><span>{t("credential.provider")}</span><strong>{provider}</strong></div>
          <div><span>{t("credential.model")}</span><strong>{model}</strong></div>
        </div>
        <form onSubmit={submit}>
          <label>
            {t("credential.apiKey")}
            <input
              name="api_key"
              type="password"
              required
              autoComplete="off"
              placeholder={t("credential.placeholder")}
            />
          </label>
          <p className="secret-note">{t("credential.security")}</p>
          <div className="form-actions">
            <button type="button" className="paper-button" onClick={onClose}>
              {t("creator.cancel")}
            </button>
            <button className="ink-button" disabled={saving}>
              {saving ? t("credential.connecting") : t("credential.save")}
            </button>
          </div>
          {message && <p className="error-note">{message}</p>}
        </form>
      </section>
    </div>
  );
}
