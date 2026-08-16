import { useState, type FormEvent } from "react";

import { api, type AuthConfig, type AuthUser } from "./api";
import {
  Button,
  FormField,
  Input,
  PaperCard,
  PaperTab,
  Spinner,
  StickyLabel,
  StickyNote,
  Toast
} from "./components/ui";
import { useI18n } from "./i18n";

interface Props {
  config: AuthConfig;
  onAuthenticated: (user: AuthUser) => void;
}

const copy = {
  en: {
    eyebrow: "Character studio pass",
    title: "Enter Character Relay",
    intro: "Create, test, deploy, and observe AI characters inside one scrapbook research workspace.",
    login: "Sign in",
    register: "Create account",
    email: "Email",
    displayName: "Display name",
    password: "Password",
    invitation: "Invitation code",
    invitationHint: "This deployment accepts new accounts by invitation.",
    submitLogin: "Enter studio",
    submitRegister: "Create studio pass",
    working: "Checking…",
    security: "Sessions use an HttpOnly cookie. Raw session tokens and provider keys are never stored in the browser.",
    noteTitle: "Inside the notebook",
    noteBody: "Character files → Test Room → Discord deployments → Behavior Notebook"
  },
  "zh-CN": {
    eyebrow: "角色研究室通行证",
    title: "进入 Character Relay",
    intro: "在同一本二次元手帐研究工作区里创作、测试、部署并观察 AI 角色。",
    login: "登录",
    register: "创建账户",
    email: "邮箱",
    displayName: "显示名称",
    password: "密码",
    invitation: "邀请码",
    invitationHint: "此部署仅允许受邀用户创建账户。",
    submitLogin: "进入研究室",
    submitRegister: "建立通行证",
    working: "验证中…",
    security: "登录使用 HttpOnly Cookie。原始 Session Token 与模型凭证不会保存在浏览器中。",
    noteTitle: "打开手帐之后",
    noteBody: "角色档案 → Test Room → Discord 部署 → Behavior Notebook"
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
    <main className="auth-page auth-v3-page">
      <div className="auth-v3-shell">
        <PaperCard className="auth-v3-card" aria-labelledby="auth-title">
          <div className="auth-v3-topline">
            <StickyLabel variant="link">{t.eyebrow}</StickyLabel>
            <div className="language-toggle auth-v3-language" role="group" aria-label="Language">
              <Button variant={language === "en" ? "secondary" : "ghost"} size="sm" onClick={() => setLanguage("en")} type="button">EN</Button>
              <Button variant={language === "zh-CN" ? "secondary" : "ghost"} size="sm" onClick={() => setLanguage("zh-CN")} type="button">简中</Button>
            </div>
          </div>

          <div className="auth-v3-heading">
            <img src="/assets/brand/character-relay-mark.png" alt="" className="auth-v3-mark" />
            <div><h1 id="auth-title">{t.title}</h1><p>{t.intro}</p></div>
          </div>

          <div className="auth-v3-tabs" role="tablist" aria-label={t.title}>
            <PaperTab tone="lavender" active={mode === "login"} onClick={() => { setMode("login"); setError(null); }}>{t.login}</PaperTab>
            {config.registration_enabled && <PaperTab tone="rose" active={mode === "register"} onClick={() => { setMode("register"); setError(null); }}>{t.register}</PaperTab>}
          </div>

          <form className="auth-v3-form" onSubmit={submit}>
            <FormField label={t.email} required><Input name="email" type="email" required autoComplete="email" /></FormField>
            {mode === "register" && <FormField label={t.displayName} required><Input name="display_name" required autoComplete="name" /></FormField>}
            <FormField label={t.password} required><Input name="password" type="password" required minLength={mode === "register" ? 12 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} /></FormField>
            {mode === "register" && config.invitation_required && <FormField label={t.invitation} hint={t.invitationHint} required><Input name="invitation_code" required autoComplete="off" /></FormField>}
            {error && <Toast tone="danger" title={language === "zh-CN" ? "无法进入研究室" : "Could not enter the studio"}>{error}</Toast>}
            <Button className="auth-v3-submit" variant="primary" size="lg" disabled={working}>
              {working ? <><Spinner size="sm" label={t.working} /> {t.working}</> : mode === "login" ? t.submitLogin : t.submitRegister}
            </Button>
          </form>

          <p className="secret-note auth-security auth-v3-security">{t.security}</p>
        </PaperCard>

        <aside className="auth-v3-scrapbook" aria-label={t.noteTitle}>
          <div className="auth-v3-polaroid" aria-hidden="true">
            <div><img src="/assets/masque-mark.svg" alt="" /></div>
            <span>CHARACTER RELAY</span>
          </div>
          <StickyNote variant="topic" size="lg" pinned><strong>{t.noteTitle}</strong><p>{t.noteBody}</p></StickyNote>
          <StickyNote variant="character"><span>✎</span><p>{language === "zh-CN" ? "角色负责二次元感，框架负责手帐感。" : "Characters carry the anime identity; the workspace carries the scrapbook language."}</p></StickyNote>
          <span className="auth-v3-doodle" aria-hidden="true">✦ ᓚᘏᗢ ✦</span>
        </aside>
      </div>
    </main>
  );
}