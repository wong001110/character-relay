export const portalRoutes = {
  dashboard: "/",
  characters: "/characters",
  characterNew: "/characters/new",
  deployments: "/deployments",
  rooms: "/rooms",
  toolbox: "/toolbox",
  settings: "/settings",
  componentLibrary: "/dev/ui"
} as const;

export type SettingsWorkspaceTab = "account" | "server-access" | "administration";
export type AdministrationRouteTab = "users" | "servers" | "connector" | "knowledge";
export interface SettingsRouteState {
  tab: SettingsWorkspaceTab;
  administrationTab: AdministrationRouteTab;
}

const SETTINGS_TABS = new Set<SettingsWorkspaceTab>(["account", "server-access", "administration"]);
const ADMINISTRATION_TABS = new Set<AdministrationRouteTab>(["users", "servers", "connector", "knowledge"]);

export function settingsRoute(
  tab: SettingsWorkspaceTab = "account",
  administrationTab: AdministrationRouteTab = "users"
): string {
  const params = new URLSearchParams({tab});
  if (tab === "administration") params.set("admin", administrationTab);
  return `${portalRoutes.settings}?${params.toString()}`;
}

export function settingsRouteForSearch(search: string): SettingsRouteState {
  const params = new URLSearchParams(search);
  const requestedTab = params.get("tab") as SettingsWorkspaceTab | null;
  const requestedAdministration = params.get("admin") as AdministrationRouteTab | null;
  return {
    tab: requestedTab && SETTINGS_TABS.has(requestedTab) ? requestedTab : "account",
    administrationTab:
      requestedAdministration && ADMINISTRATION_TABS.has(requestedAdministration)
        ? requestedAdministration
        : "users"
  };
}

export type DeploymentNotebookTab = "characters" | "knowledge" | "notes" | "operations";
export interface DeploymentRouteState {
  serverProfileId: string | null;
  notebookTab: DeploymentNotebookTab;
}

export type CharacterFileSection =
  | "profile"
  | "persona"
  | "prompt"
  | "memory"
  | "runtime"
  | "deployments";

export type CharacterRouteView = "archive" | "file" | "edit" | "test" | "prompt-inspector" | "new";

export interface CharacterRouteState {
  view: CharacterRouteView;
  cardId: string | null;
  fileSection: CharacterFileSection | null;
}

function characterPath(cardId: string): string {
  return `${portalRoutes.characters}/${encodeURIComponent(cardId)}`;
}

export const characterRoutes = {
  archive: portalRoutes.characters,
  new: portalRoutes.characterNew,
  file: (cardId: string): string => characterPath(cardId),
  fileSection: (cardId: string, section: Exclude<CharacterFileSection, "profile">): string =>
    `${characterPath(cardId)}/${section}`,
  edit: (cardId: string): string => `${characterPath(cardId)}/edit`,
  test: (cardId: string): string => `${characterPath(cardId)}/test`,
  promptInspector: (cardId: string): string => `${characterPath(cardId)}/prompt/inspect`
} as const;

function deploymentPath(serverProfileId: string): string {
  return `${portalRoutes.deployments}/${encodeURIComponent(serverProfileId)}`;
}

export const deploymentRoutes = {
  index: portalRoutes.deployments,
  notebook: (serverProfileId: string, tab: DeploymentNotebookTab = "characters"): string =>
    `${deploymentPath(serverProfileId)}/${tab}`
} as const;

export type WorkspaceRouteSection =
  | "dashboard"
  | "characters"
  | "deployments"
  | "rooms"
  | "toolbox"
  | "settings";

const workspaceRoutes: Record<WorkspaceRouteSection, string> = {
  dashboard: portalRoutes.dashboard,
  characters: portalRoutes.characters,
  deployments: portalRoutes.deployments,
  rooms: portalRoutes.rooms,
  toolbox: portalRoutes.toolbox,
  settings: portalRoutes.settings
};

export function matchesPortalRoute(pathname: string, route: string): boolean {
  return (pathname.replace(/\/+$/, "") || "/") === route;
}

export function workspaceSectionForPath(pathname: string): WorkspaceRouteSection | null {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  if (normalized === portalRoutes.characters || normalized.startsWith(`${portalRoutes.characters}/`)) {
    return "characters";
  }
  if (deploymentRouteForPath(normalized)) return "deployments";
  return (
    (Object.keys(workspaceRoutes) as WorkspaceRouteSection[]).find((section) =>
      matchesPortalRoute(pathname, workspaceRoutes[section])
    ) ?? null
  );
}

function decodePathSegment(value: string): string | null {
  try {
    const decoded = decodeURIComponent(value);
    return decoded && !decoded.includes("/") ? decoded : null;
  } catch {
    return null;
  }
}

/**
 * Routes describe durable Character identity and the active work surface only.
 * Creator fields and a running Test Room session remain local, unsaved state.
 */
export function characterRouteForPath(pathname: string): CharacterRouteState | null {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  if (normalized === portalRoutes.characters) {
    return { view: "archive", cardId: null, fileSection: null };
  }
  if (normalized === portalRoutes.characterNew) {
    return { view: "new", cardId: null, fileSection: null };
  }
  if (!normalized.startsWith(`${portalRoutes.characters}/`)) return null;

  const parts = normalized.slice(`${portalRoutes.characters}/`.length).split("/");
  const cardId = parts.length > 0 ? decodePathSegment(parts[0]) : null;
  if (!cardId) return null;
  if (parts.length === 1) return { view: "file", cardId, fileSection: "profile" };
  if (parts.length === 3 && parts[1] === "prompt" && parts[2] === "inspect") {
    return { view: "prompt-inspector", cardId, fileSection: "prompt" };
  }
  if (parts.length !== 2) return null;

  const view = parts[1];
  if (view === "edit" || view === "test") {
    return { view, cardId, fileSection: "profile" };
  }
  if (["persona", "prompt", "memory", "runtime", "deployments"].includes(view)) {
    return { view: "file", cardId, fileSection: view as CharacterFileSection };
  }
  return null;
}

export function deploymentRouteForPath(pathname: string): DeploymentRouteState | null {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  if (normalized === portalRoutes.deployments) {
    return { serverProfileId: null, notebookTab: "characters" };
  }
  if (!normalized.startsWith(`${portalRoutes.deployments}/`)) return null;

  const parts = normalized.slice(`${portalRoutes.deployments}/`.length).split("/");
  const serverProfileId = parts.length > 0 ? decodePathSegment(parts[0]) : null;
  if (!serverProfileId) return null;
  if (parts.length === 1) {
    return { serverProfileId, notebookTab: "characters" };
  }
  if (parts.length === 2 && ["characters", "knowledge", "notes", "operations"].includes(parts[1])) {
    return {
      serverProfileId,
      notebookTab: parts[1] as DeploymentNotebookTab
    };
  }
  return null;
}
