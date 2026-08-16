import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
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
import { DomainShowcase } from "./DomainShowcase";
import { I18nProvider } from "./i18n";
import { SemanticRoutingJudgeDock } from "./SemanticRoutingJudgeDock";
import { UIShowcase } from "./UIShowcase";

const normalizedPath = window.location.pathname.replace(/\/+$/, "") || "/";
const showUiShowcase = normalizedPath === "/dev/ui";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      {showUiShowcase ? (
        <>
          <UIShowcase />
          <DomainShowcase />
        </>
      ) : (
        <App />
      )}
      {!showUiShowcase && <SemanticRoutingJudgeDock />}
    </I18nProvider>
  </StrictMode>
);
