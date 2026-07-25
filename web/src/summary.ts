import type { TrialResult } from "./api";

export type IntegrityBand = "intact" | "strained" | "fractured" | "collapsed";

export function firstBreakpoint(results: TrialResult[]): TrialResult | null {
  return results.find((item) => item.breakpoint !== null) ?? null;
}

export function integrityBand(score: number): IntegrityBand {
  if (score >= 90) return "intact";
  if (score >= 70) return "strained";
  if (score >= 40) return "fractured";
  return "collapsed";
}

export function integrityLabel(score: number): string {
  const labels: Record<IntegrityBand, string> = {
    intact: "Intact",
    strained: "Strained",
    fractured: "Fractured",
    collapsed: "Collapsed"
  };
  return labels[integrityBand(score)];
}
