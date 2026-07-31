import { useEffect, useState, type ReactNode } from "react";

import { AccountPanel } from "./AccountPanel";
import { AdminSettings } from "./AdminSettings";
import {
  api,
  type AdminRuntimeView,
  type AuthConfig,
  type AuthUser,
  type CharacterCard,
  type RuntimeStatus,
  type TargetView
} from "./api";
import { AuthScreen } from "./AuthScreen";
import { AuthoringLab } from "./AuthoringLab";
import { CalibrationLab } from "./CalibrationLab";
import { CharacterCreator } from "./CharacterCreator";
import { CharacterShelf } from "./CharacterShelf";
import { useI18n } from "./i18n";
import { MatrixWorkspace } from "./MatrixWorkspace";
import { PackRunLauncher } from "./PackRunLauncher";
import { TestRoom } from "./TestRoom";
import { WorkspaceHub } from "./WorkspaceHub";
import "./styles.css";
import "./polish.css";
import "./auth-account.css";

export default function App() {
  const { language, t } = useI18n();
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [cards, setCards] = useState<CharacterCard[]>([]);
  const [targets, setTargets] = useState<TargetView[]>([]);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [activeCard, setActiveCard] = useState<CharacterCard | null>(null);
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [editingCard, setEditingCard] = useState<CharacterCard | null>(null);
  const [adminOpen, setAdminOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [matrixOpen, setMatrixOpen] = useState(false);
  const [authoringOpen, setAuthoringOpen] = useState(false);
  const [calibrationOpen, setCalibrationOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const workspaceAllowed =
    authConfig !== null && (!authConfig.authentication_required || user !== null);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      try {
        const config = await api.getAuthConfig();
        if (!active) return;
        setAuthConfig(config);
        try {
          const currentUser = await api.getCurrentUser();
          if (active) setUser(currentUser);
        } catch (reason) {
          if (!config.authentication_required && active) setBootError(null);
          else if (active && reason instanceof Error && !reason.message.includes("401")) {
            setBootError(reason.message);
          }
        }
      } catch (reason) {
        if (active) setBootError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        if (active) setBooting(false);
      }
    }
    void bootstrap();
    return () => { active = false; };
  }, []);

  useEffect(() => { if (workspaceAllowed) void load(); }, [workspaceAllowed]);

  async function load() {
    try {
      const [nextCards, nextTargets, nextRuntime] = await Promise.all([
        api.listCharacters(), api.listTargets(), api.getRuntimeStatus()
      ]);
      setCards(nextCards); setTargets(nextTargets); setRuntime(nextRuntime);
      setActiveCard((current) => current ? nextCards.find((item) => item.id === current.id) ?? null : null);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("app.openShelfError"));
    }
  }

  function clearWorkspaceState() {
    setCards([]); setTargets([]); setRuntime(null); setActiveCard(null); setCreatorOpen(false);
    setEditingCard(null); setAdminOpen(false); setAccountOpen(false); setWorkspaceOpen(false);
    setMatrixOpen(false); setAuthoringOpen(false); setCalibrationOpen(false);
  }

  async function logout() { try { await api.logout(); } finally { setUser(null); clearWorkspaceState(); } }
  function accountDeleted() { setUser(null); clearWorkspaceState(); }
  function saved(card: CharacterCard) {
    setCreatorOpen(false); setEditingCard(null);
    setCards((current) => current.some((item) => item.id === card.id) ? current.map((item) => item.id === card.id ? card : item) : [card, ...current]);
    setActiveCard((current) => current?.id === card.id ? card : current); void load();
  }
  function runtimeUpdated(view: AdminRuntimeView) { setRuntime(view.status); }
  function openAdmin() {
    if (user?.role === "admin") { setAdminOpen(true); return; }
    if (user) { setAccountOpen(true); return; }
    setError(language === "zh-CN" ? "需要管理员账户。" : "An Admin account is required.");
  }

  function withAccount(content: ReactNode) {
    return <>{content}{user && <div style={{ position:"fixed", top:16, right:16, zIndex:40, display:"flex", gap:8, flexWrap:"wrap", justifyContent:"flex-end" }}>
      <button type="button" className="paper-button" onClick={() => setAuthoringOpen(true)}>{language === "zh-CN" ? "评测编写" : "Authoring Lab"}</button>
      <button type="button" className="paper-button" onClick={() => setCalibrationOpen(true)}>{language === "zh-CN" ? "校准数据" : "Calibration Lab"}</button>
      <button type="button" className="paper-button" onClick={() => setAccountOpen(true)}>{language === "zh-CN" ? "账户与安全" : "Account & security"}</button>
    </div>}
    {accountOpen && user && <AccountPanel user={user} onClose={() => setAccountOpen(false)} onLogout={logout} onDeleted={accountDeleted} />}
    {adminOpen && user?.role === "admin" && <AdminSettings onClose={() => setAdminOpen(false)} onUpdated={runtimeUpdated} />}</>;
  }

  if (booting) return <main className="auth-page"><section className="auth-card paper-sheet"><h1>Echo Masque</h1><p>{language === "zh-CN" ? "正在验证安全 Session…" : "Checking secure Session…"}</p></section></main>;
  if (!authConfig) return <main className="auth-page"><section className="auth-card paper-sheet"><h1>Echo Masque</h1><p className="error-note">{bootError ?? t("app.openShelfError")}</p></section></main>;
  if (authConfig.authentication_required && !user) return <AuthScreen config={authConfig} onAuthenticated={(authenticatedUser) => { setBootError(null); setUser(authenticatedUser); }} />;

  if (calibrationOpen && user) return withAccount(<CalibrationLab onClose={() => { setCalibrationOpen(false); void load(); }} />);
  if (authoringOpen && user) return withAccount(<AuthoringLab user={user} cards={cards} onClose={() => { setAuthoringOpen(false); void load(); }} />);
  if (matrixOpen) return withAccount(<MatrixWorkspace cards={cards} onClose={() => { setMatrixOpen(false); void load(); }} />);
  if (workspaceOpen) return withAccount(<><WorkspaceHub cards={cards} onClose={() => { setWorkspaceOpen(false); void load(); }} /><PackRunLauncher cards={cards} /></>);

  if (activeCard) {
    const target = targets.find((item) => item.id === activeCard.target_id);
    if (!target) return withAccount(<main className="room-page"><section className="paper-sheet missing-binding"><h1>{t("app.bindingMissingTitle")}</h1><p>{t("app.bindingMissingBody")}</p><button className="paper-button" onClick={() => setActiveCard(null)}>{t("app.returnShelf")}</button></section></main>);
    return withAccount(<TestRoom card={activeCard} target={target} runtime={runtime} onBack={() => setActiveCard(null)} onAdmin={openAdmin} />);
  }

  const editingTarget = editingCard ? targets.find((item) => item.id === editingCard.target_id) ?? null : null;
  return withAccount(<><CharacterShelf cards={cards} error={error} onCreate={() => { setEditingCard(null); setCreatorOpen(true); }} onEdit={(card) => { setEditingCard(card); setCreatorOpen(true); }} onEnter={setActiveCard} onAdmin={openAdmin} onWorkspace={() => setWorkspaceOpen(true)} onMatrix={() => setMatrixOpen(true)} />{creatorOpen && <CharacterCreator targets={targets} card={editingCard} target={editingTarget} onClose={() => { setCreatorOpen(false); setEditingCard(null); }} onSaved={saved} />}</>);
}
