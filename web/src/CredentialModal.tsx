import { useState, type FormEvent } from "react";
import { createPortal } from "react-dom";

import { api, type CharacterCard, type CredentialStatus, type TargetView } from "./api";
import { useI18n } from "./i18n";
import { useBeforeUtilityCredentialSave } from "./UtilityCredentialSaveContext";

interface CharacterCredentialProps {
  card: CharacterCard;
  target: TargetView;
  onClose: () => void;
  onConfigured: (status: CredentialStatus) => void;
  utility?: never;
}

interface UtilityCredentialProps {
  utility: {
    memberId: string;
    name: string;
    provider: string;
    model: string;
    configured?: boolean;
  };
  onClose: () => void;
  onConfigured: () => void;
  card?: never;
  target?: never;
}

type Props = CharacterCredentialProps | UtilityCredentialProps;

async function utilityCredentialRequest(
  memberId: string,
  init: RequestInit,
): Promise<void> {
  const response = await fetch(
    `/api/admin/runtime/utility-credentials/${encodeURIComponent(memberId)}`,
    { ...init, credentials: "include" },
  );
  if (!response.ok) {
    const raw = await response.text();
    let detail = raw;
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // Keep the plain-text provider/API response when it is not JSON.
    }
    throw new Error(detail || `Request failed with ${response.status}`);
  }
}

async function configureUtilityCredential(memberId: string, value: string): Promise<void> {
  await utilityCredentialRequest(memberId, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: value }),
  });
}

export function CredentialModal(props: Props) {
  const { t } = useI18n();
  const beforeUtilityCredentialSave = useBeforeUtilityCredentialSave();
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const utility = props.utility;
  const provider = utility
    ? utility.provider
    : String(props.target.config.provider ?? "OpenAI-compatible");
  const model = utility
    ? utility.model
    : String(props.target.config.model ?? "Unspecified model");
  const displayName = utility ? utility.name : props.card.display_name;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const value = String(data.get("api_key"));
    try {
      setSaving(true);
      setMessage(null);
      if (utility) {
        if (beforeUtilityCredentialSave) {
          await beforeUtilityCredentialSave();
        }
        await configureUtilityCredential(utility.memberId, value);
        props.onConfigured();
      } else {
        const status = await api.configureCredential(props.card.id, value);
        props.onConfigured(status);
      }
      props.onClose();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("credential.error"));
    } finally {
      setSaving(false);
    }
  }

  async function clearUtilityCredential() {
    if (!utility) return;
    try {
      setSaving(true);
      setMessage(null);
      if (beforeUtilityCredentialSave) {
        await beforeUtilityCredentialSave();
      }
      await utilityCredentialRequest(utility.memberId, { method: "DELETE" });
      props.onConfigured();
      props.onClose();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("credential.error"));
    } finally {
      setSaving(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onMouseDown={props.onClose}>
      <section
        className="credential-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="credential-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          className="close-button"
          onClick={props.onClose}
          aria-label={t("creator.cancel")}
        >
          ×
        </button>
        <p className="tape-label">
          {utility ? "UTILITY PROVIDER KEY" : t("credential.label")}
        </p>
        <h2 id="credential-title">
          {utility ? `Configure ${displayName}` : t("credential.configure", { name: displayName })}
        </h2>
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
          <p className="secret-note">
            {utility
              ? "This API key is stored in the encrypted server Credential Vault. It is never returned to the browser, Character Cards, reports, or logs."
              : t("credential.security")}
          </p>
          <div className="form-actions">
            {utility && (
              <button
                type="button"
                className="paper-button"
                disabled={saving}
                onClick={() => void clearUtilityCredential()}
              >
                Clear current key
              </button>
            )}
            <button type="button" className="paper-button" onClick={props.onClose}>
              {t("creator.cancel")}
            </button>
            <button className="ink-button" disabled={saving}>
              {saving
                ? t("credential.connecting")
                : utility
                  ? "Save key"
                  : t("credential.save")}
            </button>
          </div>
          {message && <p className="error-note">{message}</p>}
        </form>
      </section>
    </div>,
    document.body
  );
}
