import { useEffect, useState } from "react";

import { api, type AdminRuntimeConfig, type AdminRuntimeView } from "./api";
import { useI18n } from "./i18n";
import {
  SemanticRoutingJudgePanel,
  type SemanticRoutingAdminView,
  type SemanticRoutingJudgeConfig
} from "./SemanticRoutingJudgePanel";

export function SemanticRoutingJudgeDock() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [view, setView] = useState<SemanticRoutingAdminView | null>(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    void api.getAdminRuntime().then((value) => {
      if (active && "semantic_routing" in value.config) {
        setView(value as SemanticRoutingAdminView);
      }
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (!view) return null;

  function updateSemantic(config: SemanticRoutingJudgeConfig) {
    setView((current) => current ? ({
      ...current,
      config: { ...current.config, semantic_routing: config }
    } as SemanticRoutingAdminView) : current);
    setMessage("");
  }

  async function save() {
    if (!view) return;
    try {
      setSaving(true);
      setMessage("");
      const next = await api.updateAdminRuntime(view.config as AdminRuntimeConfig);
      setView(next as AdminRuntimeView as SemanticRoutingAdminView);
      setMessage(zh
        ? "Routing Judge 已保存，后续回合立即使用新策略。"
        : "Routing Judge saved. New turns use the updated policy immediately.");
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
          <strong>Routing Judge</strong>
        </button>
      ) : (
        <div className="semantic-routing-drawer paper-sheet">
          <header className="semantic-routing-drawer-head">
            <div><span>SUPER ADMIN / SEMANTIC RUNTIME</span><h2>Routing Judge</h2></div>
            <button type="button" className="close-button" onClick={() => setOpen(false)} aria-label="Close">×</button>
          </header>
          <SemanticRoutingJudgePanel view={view} zh={zh} onChange={updateSemantic} />
          {message && <p className={message.includes("保存") || message.includes("saved") ? "success-note" : "error-note"}>{message}</p>}
          <footer className="semantic-routing-drawer-actions">
            <button type="button" className="paper-button" onClick={() => setOpen(false)}>{zh ? "关闭" : "Close"}</button>
            <button type="button" className="ink-button" disabled={saving} onClick={() => void save()}>{saving ? (zh ? "保存中…" : "Saving…") : zh ? "保存 Routing Judge" : "Save Routing Judge"}</button>
          </footer>
        </div>
      )}
    </div>
  );
}
