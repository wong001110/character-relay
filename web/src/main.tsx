import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, useLocation } from "react-router-dom";
import App from "./App";
import "./discordEventLog.css";
import "./discordServerProfiles.css";
import "./interactionSessions.css";
import "./smartParticipation.css";
import "./toolCalling.css";
import "./portal-v2-refine.css";
import "./deployment-notebook-v2.css";
import "./deployment-notebook-tabs.css";
import "./deployment-paper-tags.css";
import "./discord-connection-workspace.css";
import "./deployment-scrapbook-pages.css";
import "./character-portraits.css";
import "./key-groups-notebook.css";
import "./key-groups-bulk-apply-v2.css";
import "./semantic-routing-admin.css";
import "./utility-gateway.css";
import "./behavior-notebook-turns.css";
import "./scrapbook-character-workflow-v2.css";
import "./scrapbook-character-workflow-v2-components.css";
import "./scrapbook-behavior-notebook-v2.css";
import "./scrapbook-behavior-notebook-components.css";
import "./scrapbook-complete-migration.css";
import "./scheduled-reminders-v3.css";
import "./interaction-scrapbook-v3.css";
import "./lab-scrapbook-v3.css";
import "./ui-showcase-icons.css";
import "./overlay-layers.css";
import "./paper-texture-system.css";
import "./portal-environment.css";
// Keep the stabilization layer last so its cross-page responsive contracts
// do not depend on which feature component happens to load first.
import "./stabilization-hotfix.css";
import { I18nProvider } from "./i18n";
import { portalRoutes } from "./portalRoutes";
import { shouldRenderSystemIntelligenceDock } from "./portalEnvironment";
import { SemanticRoutingJudgeDock } from "./SemanticRoutingJudgeDock";

function PortalRoot() {
  const location = useLocation();
  const showUiShowcase = location.pathname.replace(/\/+$/, "") === portalRoutes.componentLibrary;

  return (
    <>
      <App />
      {shouldRenderSystemIntelligenceDock(showUiShowcase) && <SemanticRoutingJudgeDock />}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <PortalRoot />
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>
);
