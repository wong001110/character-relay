import { useEffect, useState } from "react";

import { api, type AdminRuntimeConfig, type AdminRuntimeView } from "./api";
import {
  ConversationBurstRuntimePanel,
  type ConversationBurstRuntimeConfig
} from "./ConversationBurstRuntimePanel";
import { useI18n } from "./i18n";
import {
  SemanticRoutingJudgePanel,
  type SemanticRoutingAdminView,
  type SemanticRoutingJudgeConfig
} from "./SemanticRoutingJudgePanel";
import { UtilityCredentialSaveProvider } from "./UtilityCredentialSaveContext";
import {
  UtilityGatewayPanel,
  type UtilityCredentialStatus,
  type UtilityGatewayConfig,
  type UtilityGatewayRuntimeSnapshot
} from "./UtilityGatewayPanel";

type UtilityAdminView = SemanticRoutingAdminView & {
  config: SemanticRoutingAdminView["config"] & {
    utility_gateway: UtilityGatewayConfig;
    conversation_burst: ConversationBurstRuntimeConfig;
  };
};

async function loadUtilityCredentials(): Promise<UtilityCredentialStatus[]> {
  const response = await fetch("/api/admin/runtime/utility-credentials", { credentials: "include" });
  if (!response.ok) return [];
  return response.json() as Promise<UtilityCredentialStatus[]>;
}

async function loadUtilitySnapshot(): Promise<UtilityGatewayRuntimeSnapshot | null> {
  const response = await fetch("/api/admin/runtime/utility-gateway/snapshot", { credentials: "include" });
  if (!response.ok) return null;
  return response.json() as Promise<UtilityGatewayRuntimeSnapshot>;
}

export function SemanticRoutingJudgeDock() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [view, setView] = useState<UtilityAdminView | null>(null);
  const [credentialStatus, setCredentialStatus] = useState<UtilityCredentialStatus[]>([]);
  const [runtimeSnapshot, setRuntimeSnapshot] = useState<UtilityGatewayRuntimeSnapshot | null>(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function refreshRuntimeObservation() {
    const [credentials, snapshot] = await Promise.all([loadUtilityCredentials(), loadUtilitySnapshot()]);
    setCredentialStatus(credentials);
    setRuntimeSnapshot(snapshot);
  }

  useEffect(() => {
    let active = true;
    void Promise.all([api.getAdminRuntime(), loadUtilityCredentials(), loadUtilitySnapshot()])
      .then(([value, credentials, snapshot]) => {
        if (active && "semantic_routing" in value.config && "utility_gateway" in value.config && "conversation_burst" in value.config) {
          setView(value as UtilityAdminView);
          setCredentialStatus(credentials);
          setRuntimeSnapshot(snapshot);
        }
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(() => { void loadUtilitySnapshot().then(setRuntimeSnapshot); }, 15_000);
    return () => window.clearInterval(timer);
  }, [open]);

  if (!view) return null;

  function updateSemantic(config: SemanticRoutingJudgeConfig) {
    setView((current) => current ? ({ ...current, config: { ...current.config, semantic_routing: config } } as UtilityAdminView) : current);
    setMessage("");
  }

  function updateUtility(config: UtilityGatewayConfig) {
    setView((current) => current ? ({ ...current, config: { ...current.config, utility_gateway: config } } as UtilityAdminView) : current);
    setMessage("");
  }

  function updateConversationBurst(config: ConversationBurstRuntimeConfig) {
    setView((current) => current ? ({ ...current, config: { ...current.config, conversation_burst: config } } as UtilityAdminView) : current);
    setMessage("");
  }

  async function persistUtilityConfigForCredential() {
    if (!view) throw new Error("System Intelligence configuration is not loaded.");
    setMessage("");
    const next = await api.updateAdminRuntime(view.config as AdminRuntimeConfig);
    setView(next as AdminRuntimeView as UtilityAdminView);
  }

  async function save() {
    if (!view) return;
    try {
      setSaving(true);
      setMessage("");
      const next = await api.updateAdminRuntime(view.config as AdminRuntimeConfig);
      setView(next as AdminRuntimeView as UtilityAdminView);
      await refreshRuntimeObservation();
      setMessage(zh ? "System Intelligence 已保存。Connector 会在运行中同步新 Burst 参数，无需重启。" : "System Intelligence saved. The Connector will sync new Burst settings live without restart.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`semantic-routing-dock${open ? " is-open" : ""}`}>
      {!open ? (
        <button type="button" className="semantic-routing-dock-tab" onClick={() => setOpen(true)}><span>SUPER ADMIN</span><strong>System Intelligence</strong></button>
      ) : (
        <div className="semantic-routing-drawer paper-sheet">
          <header className="semantic-routing-drawer-head"><div><span>SUPER ADMIN / SYSTEM RUNTIME</span><h2>System Intelligence</h2></div><button type="button" className="close-button" onClick={() => setOpen(false)} aria-label="Close">×</button></header>
          <ConversationBurstRuntimePanel config={view.config.conversation_burst} zh={zh} onChange={updateConversationBurst} />
          <UtilityCredentialSaveProvider beforeSave={persistUtilityConfigForCredential}>
            <UtilityGatewayPanel config={view.config.utility_gateway} credentialStatus={credentialStatus} runtimeSnapshot={runtimeSnapshot} zh={zh} onChange={updateUtility} onRefreshCredentials={refreshRuntimeObservation} />
          </UtilityCredentialSaveProvider>
          <SemanticRoutingJudgePanel view={view} zh={zh} onChange={updateSemantic} />
          {message && <p className={message.includes("保存") || message.includes("saved") ? "success-note" : "error-note"}>{message}</p>}
          <footer className="semantic-routing-drawer-actions"><button type="button" className="paper-button" onClick={() => setOpen(false)}>{zh ? "关闭" : "Close"}</button><button type="button" className="ink-button" disabled={saving} onClick={() => void save()}>{saving ? (zh ? "保存中…" : "Saving…") : zh ? "保存 System Intelligence" : "Save System Intelligence"}</button></footer>
        </div>
      )}
    </div>
  );
}
