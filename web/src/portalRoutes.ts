export const portalRoutes = {
  dashboard: "/",
  characters: "/characters",
  characterNew: "/characters/new",
  deployments: "/deployments",
  toolbox: "/toolbox",
  settings: "/settings",
  componentLibrary: "/dev/ui"
} as const;

export type DeploymentNotebookTab = "characters" | "knowledge" | "interactions" | "intelligence";
export type IntelligenceWorkspaceTab =
  | "presence"
  | "social"
  | "participation"
  | "conversation"
  | "discovery";

export interface DeploymentRouteState {
  serverProfileId: string | null;
  notebookTab: DeploymentNotebookTab;
  intelligenceTab: IntelligenceWorkspaceTab | null;
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
  notebook: (serverProfileId: string, tab: Exclude<DeploymentNotebookTab, "intelligence"> = "characters"): string =>
    `${deploymentPath(serverProfileId)}/${tab}`,
  intelligence: (serverProfileId: string, tab: IntelligenceWorkspaceTab = "presence"): string =>
    `${deploymentPath(serverProfileId)}/intelligence/${tab}`
} as const;

export type WorkspaceRouteSection =
  | "dashboard"
  | "characters"
  | "deployments"
  | "toolbox"
  | "settings";

const workspaceRoutes: Record<WorkspaceRouteSection, string> = {
  dashboard: portalRoutes.dashboard,
  characters: portalRoutes.characters,
  deployments: portalRoutes.deployments,
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
    return { serverProfileId: null, notebookTab: "characters", intelligenceTab: null };
  }
  if (!normalized.startsWith(`${portalRoutes.deployments}/`)) return null;

  const parts = normalized.slice(`${portalRoutes.deployments}/`.length).split("/");
  const serverProfileId = parts.length > 0 ? decodePathSegment(parts[0]) : null;
  if (!serverProfileId) return null;
  if (parts.length === 1) {
    return { serverProfileId, notebookTab: "characters", intelligenceTab: null };
  }
  if (parts.length === 2 && ["characters", "knowledge", "interactions"].includes(parts[1])) {
    return {
      serverProfileId,
      notebookTab: parts[1] as Exclude<DeploymentNotebookTab, "intelligence">,
      intelligenceTab: null
    };
  }
  if (parts.length === 2 && parts[1] === "intelligence") {
    return { serverProfileId, notebookTab: "intelligence", intelligenceTab: "presence" };
  }
  if (
    parts.length === 3 &&
    parts[1] === "intelligence" &&
    ["presence", "social", "participation", "conversation", "discovery"].includes(parts[2])
  ) {
    return {
      serverProfileId,
      notebookTab: "intelligence",
      intelligenceTab: parts[2] as IntelligenceWorkspaceTab
    };
  }
  return null;
}
