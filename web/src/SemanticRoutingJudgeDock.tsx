import { useEffect, useState } from "react";

import { api, type AdminRuntimeConfig, type AdminRuntimeView } from "./api";
import { useI18n } from "./i18n";
import {
  SemanticRoutingJudgePanel,
  type SemanticRoutingAdminView,
  type SemanticRoutingJudgeConfig
} from "./SemanticRoutingJudgePanel";
import {
  UtilityGatewayPanel,
  type UtilityCredentialStatus,
  type UtilityGatewayConfig
} from "./UtilityGatewayPanel";

type UtilityAdminView = SemanticRoutingAdminView & {
  config: SemanticRoutingAdminView["config"] & { utility_gateway: UtilityGatewayConfig };
};

async function loadUtilityCredentials(): Promise<UtilityCredentialStatus[]> {
  const response = await fetch("/api/admin/runtime/utility-credentials", {
    credentials: "include"
  });
  if (!response.ok) return [];
  return response.json() as Promise<UtilityCredentialStatus[]>;
}

export function SemanticRoutingJudgeDock() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [view, setView] = useState<UtilityAdminView | null>(null);
  const [credentialStatus, setCredentialStatus] = useState<UtilityCredentialStatus[]>([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    void Promise.all([api.getAdminRuntime(), loadUtilityCredentials()])
      .then(([value, credentials]) => {
        if (
          active
          && "semantic_routing" in value.config
          && "utility_gateway" in value.config
        ) {
          setView(value as UtilityAdminView);
          setCredentialStatus(credentials);
        }
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (!view) return null;

  function updateSemantic(config: SemanticRoutingJudgeConfig) {
    setView((current) => current ? ({
      ...current,
      config: { ...current.config, semantic_routing: config }
    } as UtilityAdminView) : current);
    setMessage("");
  }

  function updateUtility(config: UtilityGatewayConfig) {
    setView((current) => current ? ({
      ...current,
      config: { ...current.config, utility_gateway: config }
    } as UtilityAdminView) : current);
    setMessage("");
  }

  async function refreshCredentials() {
    setCredentialStatus(await loadUtilityCredentials());
  }

  async function save() {
    if (!view) return;
    try {
      setSaving(true);
      setMessage("");
      const next = await api.updateAdminRuntime(view.config as AdminRuntimeConfig);
      setView(next as AdminRuntimeView as UtilityAdminView);
      await refreshCredentials();
      setMessage(zh
        ? "System Intelligence 设置已保存，后续 Runtime 会读取新配置。"
        : "System Intelligence settings saved for subsequent Runtime use.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`semantic-routing-dock${open ? " is-open" : ""}`}>
      {!open ? (
        <button type="button" className="semantic-routing-dock-tab" onClick={() => setOpen(true)}>
          <span>SUPER ADMIN</span>
          <strong>System Intelligence</strong>
        </button>
      ) : (
        <div className="semantic-routing-drawer paper-sheet">
          <header className="semantic-routing-drawer-head">
            <div><span>SUPER ADMIN / SYSTEM RUNTIME</span><h2>System Intelligence</h2></div>
            <button type="button" className="close-button" onClick={() => setOpen(false)} aria-label="Close">×</button>
          </header>
          <UtilityGatewayPanel
            config={view.config.utility_gateway}
            credentialStatus={credentialStatus}
            zh={zh}
            onChange={updateUtility}
            onRefreshCredentials={refreshCredentials}
          />
          <SemanticRoutingJudgePanel view={view} zh={zh} onChange={updateSemantic} />
          {message && <p className={message.includes("保存") || message.includes("saved") ? "success-note" : "error-note"}>{message}</p>}
          <footer className="semantic-routing-drawer-actions">
            <button type="button" className="paper-button" onClick={() => setOpen(false)}>{zh ? "关闭" : "Close"}</button>
            <button type="button" className="ink-button" disabled={saving} onClick={() => void save()}>{saving ? (zh ? "保存中…" : "Saving…") : zh ? "保存 System Intelligence" : "Save System Intelligence"}</button>
          </footer>
        </div>
      )}
    </div>
  );
}
