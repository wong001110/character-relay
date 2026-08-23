export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
}

export function pageItems<T>(items: T[], page: number, pageSize: number): T[] {
  const normalizedPage = Math.max(1, page);
  const normalizedSize = Math.max(1, pageSize);
  return items.slice((normalizedPage - 1) * normalizedSize, normalizedPage * normalizedSize);
}
