import { afterEach, describe, expect, it, vi } from "vitest";

import { parsePortalDataMode, shouldRenderSystemIntelligenceDock } from "./portalEnvironment";
import {
  characterRouteForPath,
  characterRoutes,
  deploymentRouteForPath,
  deploymentRoutes,
  matchesPortalRoute,
  portalRoutes,
  workspaceSectionForPath
} from "./portalRoutes";

describe("Portal route and data-mode foundation", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("uses live data unless mock mode is explicitly selected", () => {
    expect(parsePortalDataMode(undefined)).toBe("live");
    expect(parsePortalDataMode("production")).toBe("live");
    expect(parsePortalDataMode("mock")).toBe("mock");
  });

  it("keeps the System Intelligence dock out of the Component Library and mock mode", () => {
    expect(shouldRenderSystemIntelligenceDock(true, false)).toBe(false);
    expect(shouldRenderSystemIntelligenceDock(false, true)).toBe(false);
    expect(shouldRenderSystemIntelligenceDock(false, false)).toBe(true);
  });

  it("derives the import-time mock flag and default dock behavior from the environment", async () => {
    vi.stubEnv("VITE_PORTAL_DATA_MODE", "mock");
    vi.resetModules();
    const mockEnvironment = await import("./portalEnvironment");

    expect(mockEnvironment.isMockPortal).toBe(true);
    expect(mockEnvironment.shouldRenderSystemIntelligenceDock(false)).toBe(false);

    vi.stubEnv("VITE_PORTAL_DATA_MODE", "live");
    vi.resetModules();
    const liveEnvironment = await import("./portalEnvironment");

    expect(liveEnvironment.isMockPortal).toBe(false);
    expect(liveEnvironment.shouldRenderSystemIntelligenceDock(false)).toBe(true);
  });

  it("normalizes only the trailing slash for direct route matching", () => {
    expect(matchesPortalRoute("/dev/ui", portalRoutes.componentLibrary)).toBe(true);
    expect(matchesPortalRoute("/dev/ui/", portalRoutes.componentLibrary)).toBe(true);
    expect(matchesPortalRoute("/dev/ui/components", portalRoutes.componentLibrary)).toBe(false);
  });

  it("maps each top-level workspace path to one section", () => {
    expect(workspaceSectionForPath("/")).toBe("dashboard");
    expect(workspaceSectionForPath("/characters/")).toBe("characters");
    expect(workspaceSectionForPath("/dev/ui")).toBeNull();
    expect(workspaceSectionForPath("/characters/card-1/test")).toBe("characters");
    expect(workspaceSectionForPath("/deployments/server-1/intelligence/conversation")).toBe("deployments");
  });

  it("keeps Character identity and work surface in the URL", () => {
    expect(characterRouteForPath("/characters")).toEqual({ view: "archive", cardId: null, fileSection: null });
    expect(characterRouteForPath(characterRoutes.new)).toEqual({ view: "new", cardId: null, fileSection: null });
    expect(characterRouteForPath(characterRoutes.file("card with space"))).toEqual({
      view: "file",
      cardId: "card with space",
      fileSection: "profile"
    });
    expect(characterRouteForPath(characterRoutes.fileSection("card-1", "memory"))).toEqual({
      view: "file",
      cardId: "card-1",
      fileSection: "memory"
    });
    expect(characterRouteForPath(characterRoutes.promptInspector("card-1"))).toEqual({
      view: "prompt-inspector",
      cardId: "card-1",
      fileSection: "prompt"
    });
    expect(characterRouteForPath("/characters/card-1/unknown")).toBeNull();
  });

  it("keeps the selected Server Notebook page in the URL", () => {
    expect(deploymentRouteForPath("/deployments")).toEqual({
      serverProfileId: null,
      notebookTab: "characters",
      intelligenceTab: null
    });
    expect(deploymentRouteForPath(deploymentRoutes.notebook("server one", "knowledge"))).toEqual({
      serverProfileId: "server one",
      notebookTab: "knowledge",
      intelligenceTab: null
    });
    expect(deploymentRouteForPath(deploymentRoutes.intelligence("server-1", "conversation"))).toEqual({
      serverProfileId: "server-1",
      notebookTab: "intelligence",
      intelligenceTab: "conversation"
    });
    expect(deploymentRouteForPath("/deployments/server-1/not-a-page")).toBeNull();
  });
});
