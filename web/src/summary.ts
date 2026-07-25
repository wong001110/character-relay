import type { TrialResult } from "./api";

export function firstBreakpoint(results: TrialResult[]): TrialResult | null {
  return results.find((item) => item.breakpoint !== null) ?? null;
}

export function integrityLabel(score: number): string {
  if (score >= 90) return "Intact";
  if (score >= 70) return "Strained";
  if (score >= 40) return "Fractured";
  return "Collapsed";
}
