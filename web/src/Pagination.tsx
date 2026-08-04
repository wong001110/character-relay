import { useI18n } from "./i18n";

interface Props {
  page: number;
  pages: number;
  total: number;
  onPage: (page: number) => void;
  disabled?: boolean;
}

export function Pagination({ page, pages, total, onPage, disabled = false }: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  if (pages <= 1 && total <= 0) return null;
  return (
    <nav
      className="library-pagination"
      aria-label={zh ? "分页" : "Pagination"}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        flexWrap: "wrap",
        marginTop: 18
      }}
    >
      <button
        type="button"
        className="paper-button"
        disabled={disabled || page <= 1}
        onClick={() => onPage(Math.max(1, page - 1))}
      >
        {zh ? "上一页" : "Previous"}
      </button>
      <span>
        {zh ? `第 ${page} / ${pages} 页 · ${total} 条` : `Page ${page} / ${pages} · ${total} items`}
      </span>
      <button
        type="button"
        className="paper-button"
        disabled={disabled || page >= pages}
        onClick={() => onPage(Math.min(pages, page + 1))}
      >
        {zh ? "下一页" : "Next"}
      </button>
    </nav>
  );
}
