import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

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
import { CharacterCreator } from "./CharacterCreator";
import { CharacterShelf } from "./CharacterShelf";
import { DeploymentCenter } from "./DeploymentCenter";
import { deploymentApi, type CharacterDeployment } from "./deploymentApi";
import { useI18n } from "./i18n";
import { MatrixWorkspace } from "./MatrixWorkspace";
import { MockDeploymentWorkspace } from "./MockDeploymentWorkspace";
import { PackRunLauncher } from "./PackRunLauncher";
import { PortalDashboard } from "./PortalDashboard";
import { PortalShell, type PortalSection } from "./PortalShell";
import { PromptInspector } from "./PromptInspector";
import { isPublicDemoUser } from "./publicDemo";
import { isMockPortal } from "./portalEnvironment";
import {
  characterRouteForPath,
  characterRoutes,
  matchesPortalRoute,
  portalRoutes,
  workspaceSectionForPath
} from "./portalRoutes";
import { SettingsWorkspace } from "./SettingsWorkspace";
import { serverAccessApi } from "./serverAccessApi";
import { TestRoom } from "./TestRoom";
import { ToolboxWorkspace } from "./ToolboxWorkspace";
import { WorkspaceHub } from "./WorkspaceHub";
import "./styles.css";
import "./polish.css";
import "./auth-account.css";
import "./deployments.css";
import "./provider-traces.css";
import "./notebook-ui.css";
import "./admin-runtimes.css";
import "./portal-v2.css";
import "./portal-reference-shell.css";

const ComponentLibraryPage = lazy(() =>
  import("./ComponentLibraryPage").then((module) => ({
    default: module.ComponentLibraryPage
  }))
);
type PortalTheme = "light" | "dark";
const THEME_STORAGE_KEY = "character-relay-theme";

function initialTheme(): PortalTheme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export default function App() {
  const { language, t } = useI18n();
  const location = useLocation();
  const navigateTo = useNavigate();
  const requestedComponentLibrary = matchesPortalRoute(
    location.pathname,
    portalRoutes.componentLibrary
  );
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [cards, setCards] = useState<CharacterCard[]>([]);
  const [targets, setTargets] = useState<TargetView[]>([]);
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const section = workspaceSectionForPath(location.pathname) ?? "dashboard";
  const characterRoute = characterRouteForPath(location.pathname);
  const routeCard = characterRoute?.cardId
    ? cards.find((card) => card.id === characterRoute.cardId) ?? null
    : null;
  const [theme, setTheme] = useState<PortalTheme>(initialTheme);
  const [adminOpen, setAdminOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [matrixOpen, setMatrixOpen] = useState(false);
  const [deploymentCharacterId, setDeploymentCharacterId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [componentLibraryAccess, setComponentLibraryAccess] = useState<
    "idle" | "checking" | "allowed" | "denied"
  >(requestedComponentLibrary ? "checking" : "idle");

  const workspaceAllowed =
    authConfig !== null && (!authConfig.authentication_required || user !== null);
  const publicDemo = isPublicDemoUser(user);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      if (isMockPortal) {
        setAuthConfig({
          registration_enabled: false,
          invitation_required: false,
          authentication_required: false
        });
        setUser({
          id: "mock-ui-reviewer",
          email: "mock-ui@local.invalid",
          display_name: "Mock UI Reviewer",
          role: "admin"
        });
        setBooting(false);
        return;
      }
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
    if (workspaceAllowed && !requestedComponentLibrary && !isMockPortal) void load();
  }, [workspaceAllowed, requestedComponentLibrary]);

  useEffect(() => {
    if (!requestedComponentLibrary || !workspaceAllowed) return;
    if (isMockPortal) {
      setComponentLibraryAccess("allowed");
      return;
    }
    let active = true;
    setComponentLibraryAccess("checking");
    void serverAccessApi.overview()
      .then((overview) => {
        if (active) {
          setComponentLibraryAccess(
            overview.is_super_admin && !publicDemo ? "allowed" : "denied"
          );
        }
      })
      .catch(() => {
        if (active) setComponentLibraryAccess("denied");
      });
    return () => {
      active = false;
    };
  }, [publicDemo, user?.id, workspaceAllowed]);

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Theme preference is cosmetic; rendering must not depend on storage access.
    }
  }, [theme]);

  async function load() {
    try {
      const [nextCards, nextTargets, nextDeployments, nextRuntime] = await Promise.all([
        api.listCharacters(),
        api.listTargets(),
        deploymentApi.listDeployments(),
        api.getRuntimeStatus()
      ]);
      setCards(nextCards);
      setTargets(nextTargets);
      setDeployments(nextDeployments);
      setRuntime(nextRuntime);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("app.openShelfError"));
    }
  }

  function clearWorkspaceState() {
    setCards([]);
    setTargets([]);
    setDeployments([]);
    setRuntime(null);
    navigateTo(portalRoutes.dashboard);
    setAdminOpen(false);
    setWorkspaceOpen(false);
    setMatrixOpen(false);
    setDeploymentCharacterId(null);
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
    setCards((current) =>
      current.some((item) => item.id === card.id)
        ? current.map((item) => (item.id === card.id ? card : item))
        : [card, ...current]
    );
    navigateTo(characterRoutes.file(card.id));
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

  function navigate(next: PortalSection) {
    navigateTo(portalRoutes[next]);
    setWorkspaceOpen(false);
    setMatrixOpen(false);
    if (next !== "deployments") setDeploymentCharacterId(null);
  }

  function openCharacterFile(card: CharacterCard) {
    navigateTo(characterRoutes.file(card.id));
  }

  function openCharacterFileSection(
    card: CharacterCard,
    section: "profile" | "persona" | "prompt" | "memory" | "runtime" | "deployments"
  ) {
    navigateTo(
      section === "profile"
        ? characterRoutes.file(card.id)
        : characterRoutes.fileSection(card.id, section)
    );
  }

  function openDeployments(characterId: string | null = null) {
    setDeploymentCharacterId(characterId);
    navigate("deployments");
  }

  function withShell(
    content: ReactNode,
    active: PortalSection = section
  ) {
    if (!user) return content;
    return (
      <>
        <PortalShell
          active={active}
          theme={theme}
          user={user}
          publicDemo={publicDemo}
          onNavigate={navigate}
          onThemeToggle={() => setTheme((current) => current === "light" ? "dark" : "light")}
        >
          {content}
        </PortalShell>
        {adminOpen && user.role === "admin" && (
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

  if (isMockPortal && !requestedComponentLibrary) {
    if (section === "deployments") {
      return withShell(<MockDeploymentWorkspace />, "deployments");
    }
    return (
      <main className="auth-page">
        <section className="auth-card paper-sheet">
          <h1>Mock UI mode</h1>
          <p>This build contains local UI fixtures and does not connect to a live API.</p>
          <a className="paper-button" href={portalRoutes.deployments}>
            Open Server Notebook preview
          </a>
          <a className="paper-button" href={portalRoutes.componentLibrary}>
            Open Component Library
          </a>
        </section>
      </main>
    );
  }

  if (requestedComponentLibrary) {
    if (componentLibraryAccess === "allowed") {
      return (
        <Suspense
          fallback={
            <main className="auth-page">
              <section className="auth-card paper-sheet">
                <h1>Component Library</h1>
                <p>Loading the Super Admin catalog…</p>
              </section>
            </main>
          }
        >
          {isMockPortal && (
            <div className="ui-mode-banner" role="status">
              MOCK DATA — NO LIVE CONNECTION
            </div>
          )}
          <ComponentLibraryPage />
        </Suspense>
      );
    }
    if (componentLibraryAccess === "denied") {
      return (
        <main className="auth-page">
          <section className="auth-card paper-sheet">
            <h1>Component Library</h1>
            <p className="error-note">This catalog is available only to the Super Admin.</p>
            <a className="paper-button" href="/">Return to Character Relay</a>
          </section>
        </main>
      );
    }
    return (
      <main className="auth-page">
        <section className="auth-card paper-sheet">
          <h1>Component Library</h1>
          <p>Checking Super Admin access…</p>
        </section>
      </main>
    );
  }

  if (matrixOpen) {
    return withShell(
      <MatrixWorkspace
        cards={cards}
        onClose={() => {
          setMatrixOpen(false);
          void load();
        }}
      />,
      "toolbox"
    );
  }
  if (workspaceOpen) {
    return withShell(
      <div className={publicDemo ? "demo-read-only" : undefined}>
        <WorkspaceHub
          cards={cards}
          onClose={() => {
            setWorkspaceOpen(false);
            void load();
          }}
        />
        <PackRunLauncher cards={cards} />
      </div>,
      "toolbox"
    );
  }

  const editingTarget = routeCard
    ? targets.find((item) => item.id === routeCard.target_id) ?? null
    : null;

  if (section === "dashboard") {
    return withShell(
      <PortalDashboard
        cards={cards}
        runtime={runtime}
        onNavigate={navigate}
        onCreateCharacter={() => {
          navigateTo(characterRoutes.new);
        }}
      />,
      "dashboard"
    );
  }

  if (section === "deployments") {
    return withShell(
      <DeploymentCenter
        cards={cards}
        initialCharacterId={deploymentCharacterId}
        demoMode={publicDemo}
      />,
      "deployments"
    );
  }

  if (section === "toolbox") {
    return withShell(
      <ToolboxWorkspace
        cards={cards}
        admin={user?.role === "admin"}
        publicDemo={publicDemo}
        onOpenLab={() => setWorkspaceOpen(true)}
        onOpenMatrix={() => setMatrixOpen(true)}
      />,
      "toolbox"
    );
  }

  if (section === "settings" && user) {
    return withShell(
      <SettingsWorkspace
        user={user}
        publicDemo={publicDemo}
        onAdmin={openAdmin}
        onLogout={logout}
        onAccountDeleted={accountDeleted}
      />,
      "settings"
    );
  }

  if (
    (characterRoute?.view === "new" || characterRoute?.view === "edit") &&
    !publicDemo &&
    (characterRoute.view === "new" || routeCard)
  ) {
    return withShell(
      <CharacterCreator
        targets={targets}
        card={characterRoute.view === "edit" ? routeCard : null}
        target={editingTarget}
        onClose={() => {
          navigateTo(
            characterRoute.view === "edit" && routeCard
              ? characterRoutes.file(routeCard.id)
              : characterRoutes.archive
          );
        }}
        onSaved={saved}
      />,
      "characters"
    );
  }

  if (characterRoute?.view === "test" && routeCard) {
    const target = targets.find((item) => item.id === routeCard.target_id);
    if (!target) {
      return withShell(
        <main className="room-page">
          <section className="paper-sheet missing-binding">
            <h1>{t("app.bindingMissingTitle")}</h1>
            <p>{t("app.bindingMissingBody")}</p>
            <button className="paper-button" onClick={() => navigateTo(characterRoutes.file(routeCard.id))}>
              {t("app.returnShelf")}
            </button>
          </section>
        </main>,
        "characters"
      );
    }
    return withShell(
      <TestRoom
        card={routeCard}
        target={target}
        runtime={runtime}
        onBack={() => navigateTo(characterRoutes.file(routeCard.id))}
        onAdmin={openAdmin}
      />,
      "characters"
    );
  }

  return withShell(
    <>
      <CharacterShelf
        cards={cards}
        targets={targets}
        deployments={deployments}
        selectedCard={
          characterRoute?.view === "file" || characterRoute?.view === "prompt-inspector"
            ? routeCard
            : null
        }
        selectedFileSection={
          characterRoute?.view === "file" || characterRoute?.view === "prompt-inspector"
            ? characterRoute.fileSection ?? "profile"
            : undefined
        }
        error={error}
        demoMode={publicDemo}
        onCreate={() => {
          navigateTo(characterRoutes.new);
        }}
        onOpenFile={openCharacterFile}
        onCloseFile={() => navigateTo(characterRoutes.archive)}
        onFileSectionChange={(section) => {
          if (routeCard) openCharacterFileSection(routeCard, section);
        }}
        onEdit={(card) => {
          navigateTo(characterRoutes.edit(card.id));
        }}
        onPrompt={(card) => navigateTo(characterRoutes.promptInspector(card.id))}
        onEnter={(card) => navigateTo(characterRoutes.test(card.id))}
        onDeploy={(card) => openDeployments(card.id)}
      />
      {characterRoute?.view === "prompt-inspector" && routeCard && (
        <PromptInspector
          card={routeCard}
          onClose={() => navigateTo(characterRoutes.fileSection(routeCard.id, "prompt"))}
        />
      )}
    </>,
    "characters"
  );
}
