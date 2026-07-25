export type ReportFormat = "markdown" | "json";

export function formatReportContent(content: string, format: ReportFormat): string {
  if (format !== "json") return content;
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

export function reportFilename(runId: string, format: ReportFormat): string {
  return `echo-masque-${runId}.${format === "json" ? "json" : "md"}`;
}
