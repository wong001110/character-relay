import { useEffect, useState } from "react";

import { cliAuthApi, cliErrorMessage, cliScopeLabel, type CliBrowserContext, type CliGrant } from "./cliAuthApi";
import { FunctionalIcon } from "./components/ui";
import { useI18n } from "./i18n";

export function CliGrantSettings({ disabled = false, userId }: { disabled?: boolean; userId: string }) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [grants, setGrants] = useState<CliGrant[]>([]);
  const [context, setContext] = useState<CliBrowserContext | null>(null);
  const [loading, setLoading] = useState(!disabled);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setContext(null); setGrants([]); setError(null); setLoading(!disabled);
    if (disabled) return;
    void Promise.all([cliAuthApi.context(), cliAuthApi.grants()]).then(([browserContext, result]) => {
      if (!active) return;
      if (browserContext.account.user_id !== userId) {
        setError(zh ? "账户已改变，请刷新页面后重试。" : "The signed-in account has changed. Refresh this page before continuing.");
        return;
      }
      setContext(browserContext); setGrants(result.grants);
    }).catch(reason => { if (active) setError(cliErrorMessage(reason, zh)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [disabled, userId, zh]);

  async function revoke(grantId: string) {
    if (!context || busy || disabled) return;
    setBusy(true); setError(null);
    try {
      await cliAuthApi.revoke(grantId, context.csrf_token);
      const result = await cliAuthApi.grants(); setGrants(result.grants);
    } catch (reason) { setError(cliErrorMessage(reason, zh)); }
    finally { setBusy(false); }
  }

  return <section className="settings-paper-card">
    <div className="settings-card-heading">
      <span className="settings-card-icon settings-card-icon-mint"><FunctionalIcon name="boundaries" size={18} /></span>
      <div><p className="settings-card-kicker">CLI</p><h3>{zh ? "CLI 只读授权" : "CLI read-only grants"}</h3>
        <p>{zh ? "查看已批准的应用、房间与到期时间，随时撤销访问。" : "Review approved applications, rooms and expiry times. Revoke access whenever you need."}</p></div>
    </div>
    {disabled ? <p className="settings-empty-copy">{zh ? "Demo 与预览模式无法管理真实 CLI 授权。" : "Demo and preview modes cannot manage real CLI grants."}</p> : <>
      {error && <p className="settings-inline-message" role="alert">{error}</p>}
      {loading && <p role="status">{zh ? "正在加载授权…" : "Loading grants…"}</p>}
      <div className="settings-list">{grants.map(grant => <div className="settings-list-row" key={grant.grant_id}>
        <div><strong>{grant.client_name}</strong><small>{grant.client_id} · {grant.grant_id}</small>
          <span>{grant.scopes.map(scope => cliScopeLabel(scope, zh)).join(" · ")}</span>
          <small>{zh ? "房间" : "Rooms"}: {grant.room_ids.join(", ")}</small>
          <small>{zh ? "批准时间" : "Approved"}: {new Date(grant.approved_at).toLocaleString()}</small>
          <small>{zh ? "到期时间" : "Expires"}: {new Date(grant.expires_at).toLocaleString()}</small>
          {grant.revoked_at && <small>{zh ? "已撤销" : "Revoked"}: {new Date(grant.revoked_at).toLocaleString()}</small>}
        </div>
        {!grant.revoked_at && new Date(grant.expires_at).getTime() > Date.now() && <button className="settings-text-button" type="button" disabled={busy || !context} onClick={() => void revoke(grant.grant_id)}>{zh ? "撤销" : "Revoke"}</button>}
      </div>)}</div>
      {!loading && !error && grants.length === 0 && <p className="settings-empty-copy">{zh ? "没有 CLI 授权。" : "No CLI grants."}</p>}
      <a className="settings-text-button" href="/cli/authorize">{zh ? "批准新的 CLI 请求" : "Approve a new CLI request"}</a>
    </>}
  </section>;
}
