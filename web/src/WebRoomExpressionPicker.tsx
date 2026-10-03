import { useMemo, useState } from "react";
import type { WebExpression } from "./webRoomApi";

export function WebRoomExpressionPicker({
  expressions,
  disabled,
  selectedStickerKey,
  onEmoji,
  onSticker,
  tx
}: {
  expressions: WebExpression[];
  disabled: boolean;
  selectedStickerKey: string;
  onEmoji: (token: string) => void;
  onSticker: (resource: WebExpression | null) => void;
  tx: (en: string, cn: string) => string;
}) {
  const [mode, setMode] = useState<"emoji" | "sticker" | null>(null);
  const [query, setQuery] = useState("");
  const items = useMemo(() => {
    if (!mode) return [];
    const normalized = query.trim().toLowerCase();
    return expressions
      .filter(item => item.resource_type === mode && item.asset_url)
      .filter(item => !normalized || item.name.toLowerCase().includes(normalized))
      .slice(0, 240);
  }, [expressions, mode, query]);

  const selected = expressions.find(item => item.resource_key === selectedStickerKey) ?? null;

  return (
    <div className="web-room-expression-picker">
      <div className="web-room-expression-actions">
        <button type="button" disabled={disabled} aria-expanded={mode === "emoji"} onClick={() => setMode(current => current === "emoji" ? null : "emoji")}>
          {tx("Emoji", "表情")}
        </button>
        <button type="button" disabled={disabled} aria-expanded={mode === "sticker"} onClick={() => setMode(current => current === "sticker" ? null : "sticker")}>
          {tx("Sticker", "贴图")}
        </button>
      </div>
      {selected && (
        <div className="web-room-selected-sticker">
          {selected.asset_url && !["3", "lottie"].includes(selected.format_type.toLowerCase())
            ? <img src={selected.asset_url} alt={selected.description || selected.name} loading="lazy" referrerPolicy="no-referrer" />
            : <span>🏷️</span>}
          <strong>{selected.name}</strong>
          <button type="button" disabled={disabled} onClick={() => onSticker(null)}>{tx("Remove", "移除")}</button>
        </div>
      )}
      {mode && (
        <div className="web-room-expression-panel" role="dialog" aria-label={mode === "emoji" ? tx("Server emoji", "服务器表情") : tx("Server stickers", "服务器贴图")}>
          <input
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder={tx("Search server expressions", "搜索服务器表情")}
            aria-label={tx("Search expressions", "搜索表情")}
          />
          <div className="web-room-expression-grid">
            {!items.length && <p>{tx("No available resources.", "没有可用资源。")}</p>}
            {items.map(item => {
              const lottie = item.resource_type === "sticker" && ["3", "lottie"].includes(item.format_type.toLowerCase());
              return (
                <button
                  type="button"
                  className={selectedStickerKey === item.resource_key ? "is-selected" : ""}
                  disabled={disabled || lottie}
                  key={item.resource_key}
                  title={lottie ? tx("Lottie stickers are not supported by webhook identity.", "Webhook 身份暂不支持 Lottie 贴图。") : item.name}
                  onClick={() => {
                    if (item.resource_type === "emoji") {
                      onEmoji(`<${item.animated ? "a" : ""}:${item.name}:${item.resource_id}>`);
                    } else {
                      onSticker(item);
                    }
                    setMode(null);
                    setQuery("");
                  }}
                >
                  <img src={item.asset_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
                  <span>{item.name}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
