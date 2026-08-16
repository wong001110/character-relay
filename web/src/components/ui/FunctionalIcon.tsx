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
  | "refresh";

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
    refresh: <><path d="M20 7v5h-5"/><path d="M18.2 16a7 7 0 1 1 .8-7l1 3"/></>
  };

  return <svg {...common} {...props}>{paths[name]}</svg>;
}