export type PortalDataMode = "live" | "mock";

export function parsePortalDataMode(value: string | undefined): PortalDataMode {
  return value === "mock" ? "mock" : "live";
}

export const portalDataMode = parsePortalDataMode(import.meta.env.VITE_PORTAL_DATA_MODE);

export const isMockPortal = portalDataMode === "mock";

