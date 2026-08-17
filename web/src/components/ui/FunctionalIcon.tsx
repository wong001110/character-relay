import type { ReactNode, SVGProps } from "react";

export type FunctionalIconName =
  | "home"
  | "characters"
  | "deployment"
  | "toolbox"
  | "settings"
  | "overview"
  | "behavior"
  | "provider"
  | "runtime"
  | "tools"
  | "schedule"
  | "chevron"
  | "close"
  | "search"
  | "refresh"
  | "identity"
  | "persona"
  | "voice"
  | "boundaries"
  | "memory"
  | "review"
  | "archive"
  | "status-check"
  | "cloud"
  | "warning"
  | "paper-plane"
  | "bell"
  | "sun"
  | "moon";

interface Props extends SVGProps<SVGSVGElement> {
  name: FunctionalIconName;
  size?: number;
}

export function FunctionalIcon({ name, size = 18, ...props }: Props) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": props["aria-label"] ? undefined : true
  };

  const paths: Record<FunctionalIconName, ReactNode> = {
    home: <><path d="M3.5 10.5 12 3.8l8.5 6.7"/><path d="M5.5 9.3V20h13V9.3"/><path d="M9.5 20v-6h5v6"/></>,
    characters: <><circle cx="9" cy="8" r="3"/><path d="M3.8 19c.6-3.3 2.5-5 5.2-5s4.6 1.7 5.2 5"/><circle cx="17.2" cy="9" r="2.2"/><path d="M15.3 14.4c2.8-.7 4.8.7 5.2 3.6"/></>,
    deployment: <><path d="M4 7.5h10.5v9H4z"/><path d="M14.5 10h2.8l2.7 2.8v3.7h-5.5z"/><circle cx="8" cy="18" r="1.7"/><circle cx="17" cy="18" r="1.7"/></>,
    toolbox: <><path d="M4 8.5h16v11H4z"/><path d="M9 8.5V5h6v3.5"/><path d="M4 13h16"/><path d="M10 13v2h4v-2"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a8 8 0 0 0-1.7-1L14.5 3h-5l-.4 3.1a8 8 0 0 0-1.7 1L5 6.1 3 9.5 5.1 11a7 7 0 0 0 0 2L3 14.5 5 18l2.4-1.1a8 8 0 0 0 1.7 1l.4 3.1h5l.4-3.1a8 8 0 0 0 1.7-1L19 18l2-3.5-2.1-1.5c.1-.3.1-.7.1-1Z"/></>,
    overview: <><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></>,
    behavior: <><path d="M5 4h12l2 2v14H5z"/><path d="M17 4v3h3"/><path d="M8 10h8M8 14h8M8 18h5"/></>,
    provider: <><path d="M5 7h14M5 12h14M5 17h14"/><circle cx="8" cy="7" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="10" cy="17" r="1.5"/></>,
    runtime: <><path d="M4 12h4l2-5 4 10 2-5h4"/><path d="M4 4v16h16"/></>,
    tools: <><path d="m14.7 6.2 3.1-3.1a5 5 0 0 1-6.3 6.3L5 15.9 8.1 19l6.5-6.5a5 5 0 0 1 6.3-6.3l-3.1 3.1"/></>,
    schedule: <><rect x="4" y="5.5" width="16" height="14" rx="2"/><path d="M8 3.5v4M16 3.5v4M4 9h16"/><path d="M8 13h3v3H8z"/></>,
    chevron: <path d="m9 7 5 5-5 5"/>,
    close: <><path d="M6 6l12 12M18 6 6 18"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5 5"/></>,
    refresh: <><path d="M20 7v5h-5"/><path d="M18.2 16a7 7 0 1 1 .8-7l1 3"/></>,
    identity: <><circle cx="12" cy="7.5" r="3.4"/><path d="M5.2 20c.7-4.3 3-6.4 6.8-6.4s6.1 2.1 6.8 6.4"/></>,
    persona: <path d="M20.8 8.8c0 5-8.8 10.5-8.8 10.5S3.2 13.8 3.2 8.8A4.7 4.7 0 0 1 12 6.5a4.7 4.7 0 0 1 8.8 2.3Z"/>,
    voice: <><path d="M4 5.5h16v11H9l-5 3v-14Z"/><path d="M8 10.8h.1M12 10.8h.1M16 10.8h.1"/></>,
    boundaries: <><path d="M12 3.5 19 6v5.2c0 4.2-2.3 7.4-7 9.3-4.7-1.9-7-5.1-7-9.3V6l7-2.5Z"/><path d="M12 7v9"/></>,
    memory: <><path d="M9.3 4.5A3.2 3.2 0 0 0 6 7.7a3 3 0 0 0-1.7 5.4A3.4 3.4 0 0 0 8 18.5c.6 1.2 1.7 2 3 2V4.8a3.1 3.1 0 0 0-1.7-.3Z"/><path d="M14.7 4.5A3.2 3.2 0 0 1 18 7.7a3 3 0 0 1 1.7 5.4 3.4 3.4 0 0 1-3.7 5.4c-.6 1.2-1.7 2-3 2V4.8a3.1 3.1 0 0 1 1.7-.3ZM7 9.5h4M13 8h4M7.5 15H11M13 13.5h4"/></>,
    review: <><path d="M6 3.5h9l3 3V20H6z"/><path d="M15 3.5V7h3M9 11h6M9 15l1.5 1.5L14 13"/></>,
    archive: <><path d="M5 8h14v12H5z"/><path d="M4 4h16v4H4zM9 12h6"/><path d="M8 5.8h8"/></>,
    "status-check": <><circle cx="12" cy="12" r="8.5"/><path d="m8.3 12.1 2.4 2.5 5-5.2"/></>,
    cloud: <path d="M6.5 18h11a4 4 0 0 0 .5-8 6.2 6.2 0 0 0-11.8 1.4A3.4 3.4 0 0 0 6.5 18Z"/>,
    warning: <><path d="m12 3.5 9 16H3l9-16Z"/><path d="M12 9v4.5M12 17h.1"/></>,
    "paper-plane": <><path d="m3.5 11.2 17-7.1-6.9 16.2-2.8-6.6-7.3-2.5Z"/><path d="m10.8 13.7 4.6-4.6"/></>,
    bell: <><path d="M6.2 9.5a5.8 5.8 0 0 1 11.6 0c0 5 2.2 6.2 2.2 6.2H4s2.2-1.2 2.2-6.2Z"/><path d="M9.5 19a2.8 2.8 0 0 0 5 0"/></>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/></>,
    moon: <path d="M19.5 15.2A8.1 8.1 0 0 1 8.8 4.5 8.4 8.4 0 1 0 19.5 15.2Z"/>
  };

  return <svg {...common} {...props}>{paths[name]}</svg>;
}
