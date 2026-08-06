import { useEffect, useState, type ReactNode } from "react";

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
import { CoverageLab } from "./CoverageLab";
import { DeploymentCenter } from "./DeploymentCenter";
import { EvaluationLab } from "./EvaluationLab";
import { useI18n } from "./i18n";
import { MatrixWorkspace } from "./MatrixWorkspace";
import { PackRunLauncher } from "./PackRunLauncher";
import { PortalToolbox } from "./PortalToolbox";
import { PromptInspector } from "./PromptInspector";
import { isPublicDemoUser } from "./publicDemo";
import { TemplateLab } from "./TemplateLab";
import { TestRoom } from "./TestRoom";
import { WorkspaceHub } from "./WorkspaceHub";
import "./styles.css";
import "./polish.css";
import "./auth-account.css";
import "./deployments.css";
import "./provider-traces.css";
import "./notebook-ui.css";
import "./admin-runtimes.css";

const SHOW_ADVANCED_LABS = false;

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
  const [promptCard, setPromptCard] = useState<CharacterCard | null>(null);
  const [adminOpen, setAdminOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [matrixOpen, setMatrixOpen] = useState(false);
  const [deploymentsOpen, setDeploymentsOpen] = useState(false);
  const [deploymentCharacterId, setDeploymentCharacterId] = useState<string | null>(null);
  const [authoringOpen, setAuthoringOpen] = useState(false);
  const [calibrationOpen, setCalibrationOpen] = useState(false);
  const [evaluationOpen, setEvaluationOpen] = useState(false);
  const [coverageOpen, setCoverageOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const workspaceAllowed =
    authConfig !== null && (!authConfig.authentication_required || user !== null);
  const publicDemo = isPublicDemoUser(user);

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
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (workspaceAllowed) void load();
  }, [workspaceAllowed]);

  async function load() {
    try {
      const [nextCards, nextTargets, nextRuntime] = await Promise.all([
        api.listCharacters(),
        api.listTargets(),
        api.getRuntimeStatus()
      ]);
      setCards(nextCards);
      setTargets(nextTargets);
      setRuntime(nextRuntime);
      setActiveCard((current) =>
        current ? nextCards.find((item) => item.id === current.id) ?? null : null
      );
      setPromptCard((current) =>
        current ? nextCards.find((item) => item.id === current.id) ?? null : null
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("app.openShelfError"));
    }
  }

  function clearWorkspaceState() {
    setCards([]);
    setTargets([]);
    setRuntime(null);
    setActiveCard(null);
    setCreatorOpen(false);
    setEditingCard(null);
    setPromptCard(null);
    setAdminOpen(false);
    setWorkspaceOpen(false);
    setMatrixOpen(false);
    setDeploymentsOpen(false);
    setDeploymentCharacterId(null);
    setAuthoringOpen(false);
    setCalibrationOpen(false);
    setEvaluationOpen(false);
    setCoverageOpen(false);
    setTemplateOpen(false);
  }

  async function logout() {
    try {
      await api.logout();
    } finally {
      setUser(null);
      clearWorkspaceState();
    }
  }

  function accountDeleted() {
    setUser(null);
    clearWorkspaceState();
  }

  function saved(card: CharacterCard) {
    setCreatorOpen(false);
    setEditingCard(null);
    setCards((current) =>
      current.some((item) => item.id === card.id)
        ? current.map((item) => (item.id === card.id ? card : item))
        : [card, ...current]
    );
    setActiveCard((current) => (current?.id === card.id ? card : current));
    void load();
  }

  function runtimeUpdated(view: AdminRuntimeView) {
    setRuntime(view.status);
  }

  function openAdmin() {
    if (publicDemo) {
      setError(
        language === "zh-CN"
          ? "共享 Demo 账户不开放管理员设置。"
          : "Admin settings are not available in the shared Demo account."
      );
      return;
    }
    if (user?.role === "admin") {
      setAdminOpen(true);
      return;
    }
    setError(language === "zh-CN" ? "需要管理员账户。" : "An Admin account is required.");
  }

  function openDeployments(characterId: string | null = null) {
    setDeploymentCharacterId(characterId);
    setDeploymentsOpen(true);
  }

  function withAccount(content: ReactNode) {
    return (
      <>
        {content}
        {user && (
          <PortalToolbox
            user={user}
            publicDemo={publicDemo}
            onDeployments={() => openDeployments()}
            onWorkspace={() => setWorkspaceOpen(true)}
            onMatrix={() => setMatrixOpen(true)}
            onAdmin={openAdmin}
            onLogout={logout}
            onAccountDeleted={accountDeleted}
          />
        )}
        {adminOpen && user?.role === "admin" && (
          <AdminSettings
            onClose={() => setAdminOpen(false)}
            onUpdated={runtimeUpdated}
          />
        )}
      </>
    );
  }

  if (booting) {
    return (
      <main className="auth-page">
        <section className="auth-card paper-sheet">
          <h1>Character Relay</h1>
          <p>
            {language === "zh-CN"
              ? "正在验证安全 Session…"
              : "Checking secure Session…"}
          </p>
        </section>
      </main>
    );
  }

  if (!authConfig) {
    return (
      <main className="auth-page">
        <section className="auth-card paper-sheet">
          <h1>Character Relay</h1>
          <p className="error-note">{bootError ?? t("app.openShelfError")}</p>
        </section>
      </main>
    );
  }

  if (authConfig.authentication_required && !user) {
    return (
      <AuthScreen
        config={authConfig}
        onAuthenticated={(authenticatedUser) => {
          setBootError(null);
          setUser(authenticatedUser);
        }}
      />
    );
  }

  if (SHOW_ADVANCED_LABS && templateOpen && user) {
    return withAccount(
      <TemplateLab
        cards={cards}
        onClose={() => {
          setTemplateOpen(false);
          void load();
        }}
      />
    );
  }
  if (SHOW_ADVANCED_LABS && coverageOpen && user) {
    return withAccount(
      <CoverageLab
        cards={cards}
        onClose={() => {
          setCoverageOpen(false);
          void load();
        }}
      />
    );
  }
  if (SHOW_ADVANCED_LABS && evaluationOpen && user) {
    return withAccount(
      <EvaluationLab
        onClose={() => {
          setEvaluationOpen(false);
          void load();
        }}
      />
    );
  }
  if (SHOW_ADVANCED_LABS && calibrationOpen && user) {
    return withAccount(
      <CalibrationLab
        onClose={() => {
          setCalibrationOpen(false);
          void load();
        }}
      />
    );
  }
  if (SHOW_ADVANCED_LABS && authoringOpen && user) {
    return withAccount(
      <AuthoringLab
        user={user}
        cards={cards}
        onClose={() => {
          setAuthoringOpen(false);
          void load();
        }}
      />
    );
  }
  if (matrixOpen) {
    return withAccount(
      <MatrixWorkspace
        cards={cards}
        onClose={() => {
          setMatrixOpen(false);
          void load();
        }}
      />
    );
  }
  if (workspaceOpen) {
    return withAccount(
      <div className={publicDemo ? "demo-read-only" : undefined}>
        <WorkspaceHub
          cards={cards}
          onClose={() => {
            setWorkspaceOpen(false);
            void load();
          }}
        />
        <PackRunLauncher cards={cards} />
      </div>
    );
  }
  if (deploymentsOpen) {
    return withAccount(
      <DeploymentCenter
        cards={cards}
        initialCharacterId={deploymentCharacterId}
        demoMode={publicDemo}
        onClose={() => {
          setDeploymentsOpen(false);
          setDeploymentCharacterId(null);
        }}
      />
    );
  }

  if (activeCard) {
    const target = targets.find((item) => item.id === activeCard.target_id);
    if (!target) {
      return withAccount(
        <main className="room-page">
          <section className="paper-sheet missing-binding">
            <h1>{t("app.bindingMissingTitle")}</h1>
            <p>{t("app.bindingMissingBody")}</p>
            <button className="paper-button" onClick={() => setActiveCard(null)}>
              {t("app.returnShelf")}
            </button>
          </section>
        </main>
      );
    }
    return withAccount(
      <TestRoom
        card={activeCard}
        target={target}
        runtime={runtime}
        onBack={() => setActiveCard(null)}
        onAdmin={openAdmin}
      />
    );
  }

  const editingTarget = editingCard
    ? targets.find((item) => item.id === editingCard.target_id) ?? null
    : null;
  return withAccount(
    <>
      <CharacterShelf
        cards={cards}
        error={error}
        demoMode={publicDemo}
        onCreate={() => {
          setEditingCard(null);
          setCreatorOpen(true);
        }}
        onEdit={(card) => {
          setEditingCard(card);
          setCreatorOpen(true);
        }}
        onPrompt={setPromptCard}
        onEnter={setActiveCard}
        onDeploy={(card) => openDeployments(card.id)}
      />
      {creatorOpen && !publicDemo && (
        <CharacterCreator
          targets={targets}
          card={editingCard}
          target={editingTarget}
          onClose={() => {
            setCreatorOpen(false);
            setEditingCard(null);
          }}
          onSaved={saved}
        />
      )}
      {promptCard && (
        <PromptInspector card={promptCard} onClose={() => setPromptCard(null)} />
      )}
    </>
  );
}
