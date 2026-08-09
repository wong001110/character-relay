export const PORTAL_TIMEZONE = "Asia/Kuala_Lumpur";

const EXPLICIT_TIMEZONE = /(Z|[+-]\d{2}:?\d{2})$/u;

export function parsePortalTimestamp(value: string): Date {
  const normalized = value.trim();
  if (!normalized) return new Date(Number.NaN);
  return new Date(EXPLICIT_TIMEZONE.test(normalized) ? normalized : `${normalized}Z`);
}

export function formatPortalTimestamp(value: string, zh = false): string {
  const date = parsePortalTimestamp(value);
  if (Number.isNaN(date.getTime())) return value || "—";
  return `${date.toLocaleString(zh ? "zh-CN" : "en-MY", {
    timeZone: PORTAL_TIMEZONE,
    hour12: true
  })} MYT`;
}
