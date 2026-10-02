import { useEffect, useState } from "react";
import { roomRequest } from "./roomHttp";
import { UtilityGatewayPanel, type UtilityCredentialStatus, type UtilityGatewayConfig, type UtilityGatewayRuntimeSnapshot } from "./UtilityGatewayPanel";
import { UtilityCredentialSaveProvider } from "./UtilityCredentialSaveContext";
import { Button, FormField, Textarea, PaperCard } from "./components/ui";
interface Policy { enabled: boolean; deadline_seconds: number; max_attempts: number; qualifications: unknown[]; }
interface View { config: { utility_gateway: UtilityGatewayConfig; room_director: Policy; [key: string]: unknown }; }
export function RoomRuntimeSettings({ zh }: { zh: boolean }) {
  const [view, setView] = useState<View | null>(null);
  const [credentials, setCredentials] = useState<UtilityCredentialStatus[]>([]);
  const [snapshot, setSnapshot] = useState<UtilityGatewayRuntimeSnapshot | null>(null);
  const [qualificationText, setQualificationText] = useState("[]");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  async function refresh() {
    const [creds, state] = await Promise.all([roomRequest<UtilityCredentialStatus[]>("/api/admin/runtime/utility-credentials"), roomRequest<UtilityGatewayRuntimeSnapshot>("/api/admin/runtime/utility-gateway/snapshot")]);
    setCredentials(creds); setSnapshot(state);
  }
  useEffect(() => {
    let live = true;
    void roomRequest<View>("/api/admin/runtime").then(next => { if (live) { setView(next); setQualificationText(JSON.stringify(next.config.room_director.qualifications, null, 2)); } }).catch((e: unknown) => { if (live) setError(String(e)); });
    void refresh().catch((e: unknown) => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, []);
  async function save() {
    if (!view) throw new Error("Runtime not loaded");
    const qualifications: unknown = JSON.parse(qualificationText);
    if (!Array.isArray(qualifications)) throw new Error("Qualification data must be an array.");
    const next = await roomRequest<View>("/api/admin/runtime", { method: "PUT", body: JSON.stringify({ ...view.config, room_director: { ...view.config.room_director, qualifications } }) });
    setView(next); await refresh();
  }
  async function submit() {
    if (saving) return; setSaving(true); setError(""); setMessage("");
    try { await save(); setMessage(zh ? "运行配置已保存。" : "Runtime configuration saved."); } catch (e) { setError(String(e)); } finally { setSaving(false); }
  }
  return <PaperCard><h2>Free Token Pool / Room Director</h2>
    {error && <p className="error-note" role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {!view ? <p>{zh ? "读取管理员配置…" : "Loading administrator configuration…"}</p> : <>
      <UtilityCredentialSaveProvider beforeSave={save}><UtilityGatewayPanel config={view.config.utility_gateway} credentialStatus={credentials} runtimeSnapshot={snapshot} zh={zh} onChange={utility_gateway => setView({ ...view, config: { ...view.config, utility_gateway } })} onRefreshCredentials={refresh} /></UtilityCredentialSaveProvider>
      <label><input type="checkbox" checked={view.config.room_director.enabled} onChange={e => setView({ ...view, config: { ...view.config, room_director: { ...view.config.room_director, enabled: e.target.checked } } })} /> {zh ? "允许有资格记录的模型参与模糊群聊" : "Allow qualified models to route ambient chat"}</label>
      <p>{zh ? "明确提及不需要 Director。没有通过资格门槛、过期或模型变更时不会自动放行；真实测试未完成不能填写为通过。" : "Direct mentions bypass the Director. Missing, expired or mismatched qualifications do not activate ambient routing. Do not mark unperformed real tests as passed."}</p>
      <details><summary>{zh ? "导入经过审核的资格记录" : "Import reviewed qualification records"}</summary><FormField label="Qualification JSON" hint={zh ? "绑定 member、model、prompt、语料/报告 hash 与到期时间；由服务器校验。" : "Bound to member/model/prompt/corpus/report hashes and expiry; validated by the server."}><Textarea rows={10} maxLength={60000} value={qualificationText} onChange={e => setQualificationText(e.target.value)} /></FormField></details>
      <Button variant="primary" disabled={saving} onClick={() => void submit()}>{saving ? (zh ? "保存中…" : "Saving…") : (zh ? "保存配置" : "Save configuration")}</Button>
    </>}
  </PaperCard>;
}
