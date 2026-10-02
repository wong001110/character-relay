import { useLocation, useNavigate } from "react-router-dom";
import { deploymentRouteForPath, deploymentRoutes, type DeploymentNotebookTab } from "./portalRoutes";

export function MockDeploymentWorkspace() {
  const location = useLocation();
  const navigate = useNavigate();
  const tab = deploymentRouteForPath(location.pathname)?.notebookTab ?? "characters";
  return <main className="deployment-workspace deployment-workspace-mock">
    <header className="deployment-workspace-header paper-sheet"><h1>Mock Server Notebook</h1><p>Layout preview only. No live room data, mutations or runtime results.</p></header>
    <nav className="server-notebook-tabs" aria-label="Mock notebook pages">
      {(["characters", "knowledge", "notes", "operations"] as DeploymentNotebookTab[]).map(item =>
        <button type="button" key={item} aria-current={tab === item ? "page" : undefined} onClick={() => navigate(deploymentRoutes.notebook("mock-server", item))}>{item}</button>)}
    </nav>
    <section className="paper-sheet"><h2>{tab}</h2><p>Use the live Portal to view authorized data. This mock does not simulate successful operations.</p></section>
  </main>;
}
