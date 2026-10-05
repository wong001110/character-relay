import { useEffect, useState, type FormEvent } from "react";

import type { AuthUser } from "./api";
import { cliAuthApi, cliErrorMessage, cliScopeLabel, type CliAuthorizationReview, type CliBrowserContext } from "./cliAuthApi";
import { useI18n } from "./i18n";
import { NotebookField, NotebookInput } from "./NotebookUI";
import "./cli-auth.css";

export function CliAuthorizationDetails({ review, zh }: { review: CliAuthorizationReview; zh: boolean }) {
  return <div className="cli-authorization-details">
    <dl className="settings-detail-grid">
      <div><dt>{zh ? "应用" : "Application"}</dt><dd>{review.client_name}<small>{review.client_id}</small></dd></div>
      <div><dt>{zh ? "批准账户" : "Approving account"}</dt><dd>{review.account.display_name}<small>{review.account.email}</small><small>{review.account.user_id}</small></dd></div>
      <div><dt>{zh ? "代码有效至" : "Code expires"}</dt><dd>{new Date(review.device_expires_at).toLocaleString()}</dd></div>
      <div><dt>{zh ? "授权有效期" : "Access duration"}</dt><dd>{review.access_token_ttl_seconds} {zh ? "秒，批准后开始计时" : "seconds after approval"}</dd></div>
    </dl>
    <h2>{zh ? "仅允许以下房间" : "Only these rooms"}</h2>
    <ul className="cli-authorization-rooms">{review.rooms.map(room => <li key={room.id}><strong>{room.name}</strong><code>{room.id}</code></li>)}</ul>
    <h2>{zh ? "允许的读取操作" : "Allowed reads"}</h2>
    <ul>{review.scopes.map(scope => <li key={scope}>{cliScopeLabel(scope, zh)} <code>{scope}</code></li>)}</ul>
    <p>{zh ? "此授权只允许读取，不允许发送消息。你可在账户设置中撤销授权。" : "This grant allows reading only. It cannot send messages. You can revoke it in account settings."}</p>
  </div>;
}

export function CliAuthorize({ user, disabled = false, initialCode = "" }: {
  user: AuthUser | null; disabled?: boolean; initialCode?: string;
}) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [code, setCode] = useState(initialCode.slice(0, 32));
  const [context, setContext] = useState<CliBrowserContext | null>(null);
  const [review, setReview] = useState<CliAuthorizationReview | null>(null);
  const [reviewedCode, setReviewedCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<"approve" | "deny" | null>(null);

  useEffect(() => {
    let active = true;
    setContext(null); setReview(null); setResult(null); setError(null);
    if (disabled || !user) return;
    void cliAuthApi.context().then(value => {
      if (!active) return;
      if (value.account.user_id !== user.id) {
        setError(zh ? "账户已改变，请刷新页面后重试。" : "The signed-in account has changed. Refresh this page before continuing.");
        return;
      }
      setContext(value);
    }).catch(reason => { if (active) setError(cliErrorMessage(reason, zh)); });
    return () => { active = false; };
  }, [disabled, user?.id, zh]);

  async function reviewCode(event: FormEvent) {
    event.preventDefault();
    if (!context || busy || disabled) return;
    setBusy(true); setError(null); setReview(null); setResult(null);
    const requestedCode = code.trim().toUpperCase();
    try {
      const value = await cliAuthApi.review(requestedCode, context.csrf_token);
      if (value.account.user_id !== user?.id) throw new Error("Account changed");
      setReviewedCode(requestedCode); setReview(value);
    } catch (reason) { setError(cliErrorMessage(reason, zh)); }
    finally { setBusy(false); }
  }

  async function decide(decision: "approve" | "deny") {
    if (!context || !review || busy || disabled || review.account.user_id !== user?.id) return;
    setBusy(true); setError(null);
    try {
      await cliAuthApi.decide(reviewedCode, decision, context.csrf_token);
      setResult(decision); setReview(null);
    } catch (reason) { setError(cliErrorMessage(reason, zh)); }
    finally { setBusy(false); }
  }

  return <main className="auth-page cli-authorization-page">
    <section className="auth-card paper-sheet cli-authorization-card">
      <p className="settings-card-kicker">Character Relay</p>
      <h1>{zh ? "批准 CLI 读取" : "Approve CLI access"}</h1>
      {disabled ? <p role="status">{zh ? "Demo 与预览模式无法批准真实 CLI 授权。" : "Demo and preview modes cannot approve real CLI access."}</p>
        : !user ? <p role="status">{zh ? "请先使用官方网页登录账户。" : "Sign in to your account on the official website first."}</p>
        : <>
          <p>{zh ? "只输入你正在使用的 CLI 显示的代码，先查看请求，再明确批准或拒绝。" : "Enter the code displayed by the CLI you are using. Review the request before choosing Approve or Deny."}</p>
          <p className="cli-authorization-account">{user.display_name} · {user.email}</p>
          {error && <p className="error-note" role="alert">{error}</p>}
          {result ? <p role="status">{result === "approve"
            ? (zh ? "已批准。请返回 CLI 继续。" : "Approved. Return to your CLI to continue.")
            : (zh ? "已拒绝此请求。" : "This request has been denied.")}</p>
            : <>
              <form onSubmit={reviewCode} className="cli-authorization-code-form">
                <NotebookField label={zh ? "CLI 显示的代码" : "Code shown by your CLI"} required>
                  <NotebookInput name="user_code" value={code} required maxLength={32} autoComplete="off" spellCheck={false} disabled={busy}
                    onChange={event => { setCode(event.target.value); setReview(null); setError(null); }} />
                </NotebookField>
                <button className="settings-action-button" type="submit" disabled={busy || !context || !code.trim()}>{zh ? "查看授权请求" : "Review request"}</button>
              </form>
              {review && <>
                <CliAuthorizationDetails review={review} zh={zh} />
                <div className="cli-authorization-actions">
                  <button className="settings-action-button" type="button" disabled={busy} onClick={() => void decide("approve")}>{zh ? "批准只读访问" : "Approve read-only access"}</button>
                  <button className="settings-text-button" type="button" disabled={busy} onClick={() => void decide("deny")}>{zh ? "拒绝" : "Deny"}</button>
                </div>
              </>}
            </>}
        </>}
      <a className="settings-text-button" href="/settings?tab=account">{zh ? "前往账户设置" : "Go to account settings"}</a>
    </section>
  </main>;
}
