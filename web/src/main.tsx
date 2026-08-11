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
import { I18nProvider } from "./i18n";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);
