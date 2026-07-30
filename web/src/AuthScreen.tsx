import { useState, type FormEvent } from "react";

import { api, type AuthConfig, type AuthUser } from "./api";
import { useI18n } from "./i18n";

interface Props {
  config: AuthConfig;
  onAuthenticated: (user: AuthUser) => void;
}

const copy = {
  en: {
    eyebrow: "Secure workspace",
    title: "Enter Echo Masque",
    intro:
      "Your Character Cards, experiments, and provider credentials are isolated behind an encrypted account workspace.",
    login: "Sign in",
    register: "Create account",
    email: "Email",
    displayName: "Display name",
    password: "Password",
    invitation: "Invitation code",
    invitationHint: "This deployment accepts new accounts by invitation.",
    submitLogin: "Sign in",
    submitRegister: "Create secure workspace",
    switchingLogin: "Already have an account?",
    switchingRegister: "Need an account?",
    working: "Checking…",
    security:
      "Sessions use an HttpOnly cookie. Raw session tokens and provider keys are never stored in the browser."
  },
  "zh-CN": {
    eyebrow: "安全工作区",
    title: "进入 Echo Masque",
    intro: "角色卡、实验与模型凭证会被隔离在你的加密账户工作区中。",
    login: "登录",
    register: "创建账户",
    email: "邮箱",
    displayName: "显示名称",
    password: "密码",
    invitation: "邀请码",
    invitationHint: "此部署仅允许受邀用户创建账户。",
    submitLogin: "登录",
    submitRegister: "创建安全工作区",
    switchingLogin: "已有账户？",
    switchingRegister: "需要账户？",
    working: "验证中…",
    security: "登录使用 HttpOnly Cookie。原始 Session Token 与模型凭证不会保存在浏览器中。"
  }
} as const;

export function AuthScreen({ config, onAuthenticated }: Props) {
  const { language, setLanguage } = useI18n();
  const t = copy[language];
  const [mode, setMode] = useState<"login" | "register">("login");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const email = String(values.get("email") ?? "");
    const password = String(values.get("password") ?? "");
    try {
      setWorking(true);
      setError(null);
      const response =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(
              email,
              String(values.get("display_name") ?? ""),
              password,
              String(values.get("invitation_code") ?? "") || undefined
            );
      onAuthenticated(response.user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card paper-sheet" aria-labelledby="auth-title">
        <div className="auth-topline">
          <span className="tape-label">{t.eyebrow}</span>
          <div className="language-toggle" role="group" aria-label="Language">
            <button
              className={language === "en" ? "active" : ""}
              onClick={() => setLanguage("en")}
              type="button"
            >
              EN
            </button>
            <button
              className={language === "zh-CN" ? "active" : ""}
              onClick={() => setLanguage("zh-CN")}
              type="button"
            >
              简中
            </button>
          </div>
        </div>
        <img src="/assets/masque-mark.svg" alt="" className="auth-mark" />
        <h1 id="auth-title">{t.title}</h1>
        <p className="auth-intro">{t.intro}</p>

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            className={mode === "login" ? "active" : ""}
            onClick={() => setMode("login")}
          >
            {t.login}
          </button>
          {config.registration_enabled && (
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => setMode("register")}
            >
              {t.register}
            </button>
          )}
        </div>

        <form className="auth-form" onSubmit={submit}>
          <label>
            {t.email}
            <input name="email" type="email" required autoComplete="email" />
          </label>
          {mode === "register" && (
            <label>
              {t.displayName}
              <input name="display_name" required autoComplete="name" />
            </label>
          )}
          <label>
            {t.password}
            <input
              name="password"
              type="password"
              required
              minLength={mode === "register" ? 12 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {mode === "register" && config.invitation_required && (
            <label>
              {t.invitation}
              <input name="invitation_code" required autoComplete="off" />
              <small>{t.invitationHint}</small>
            </label>
          )}
          {error && (
            <p className="error-note" role="alert">
              {error}
            </p>
          )}
          <button className="ink-button auth-submit" disabled={working}>
            {working
              ? t.working
              : mode === "login"
                ? t.submitLogin
                : t.submitRegister}
          </button>
        </form>

        {config.registration_enabled && (
          <button
            type="button"
            className="auth-switch"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? t.switchingRegister : t.switchingLogin}
          </button>
        )}
        <p className="secret-note auth-security">{t.security}</p>
      </section>
    </main>
  );
}
