import { useId, useState } from "react";
import { DEFAULT_ROOM_PIP_SIZE, ROOM_PIP_SIZE_LIMITS, isRoomPipSize, type RoomPipSize } from "./documentPip";
import { useI18n } from "./i18n";

export type RoomCompanionSizeOptions = {
  size: RoomPipSize;
  preferredSize?: RoomPipSize;
  onResize: (size: RoomPipSize) => boolean;
};

/** The host reports actual viewport size; editing a request never changes the room draft. */
export function RoomCompanionSizeControls({ size, onResize, id }: RoomCompanionSizeOptions & { id: string }) {
  const { language } = useI18n();
  const tx = (en: string, cn: string) => language === "zh-CN" ? cn : en;
  const { minWidth, maxWidth, minHeight, maxHeight } = ROOM_PIP_SIZE_LIMITS;
  const inputId = useId();
  // Mounting opens the disclosure. Later native resize events update Current,
  // while keeping a partially edited width or height intact.
  const [width, setWidth] = useState(String(size.width));
  const [height, setHeight] = useState(String(size.height));
  const [error, setError] = useState("");
  const [invalid, setInvalid] = useState(false);

  const resize = (requested: RoomPipSize) => {
    let accepted = false;
    try {
      accepted = onResize(requested);
    } catch {
      // A browser can deny a native window operation even after PiP opened.
    }
    setInvalid(false);
    setError(accepted ? "" : tx(
      "The browser could not resize this window. Try a smaller size or resize it manually.",
      "浏览器无法调整此窗口。请尝试更小的尺寸，或手动调整窗口。"
    ));
  };

  const preset = (requested: RoomPipSize) => {
    setWidth(String(requested.width));
    setHeight(String(requested.height));
    resize(requested);
  };

  const descriptionId = `${inputId}-description`;
  const errorId = `${inputId}-error`;
  const describedBy = `${descriptionId}${error ? ` ${errorId}` : ""}`;
  return (
    <form
      id={id}
      className="room-companion-size-controls"
      aria-label={tx("Window size", "窗口尺寸")}
      data-companion-reader-ignore="true"
      noValidate
      onSubmit={event => {
        event.preventDefault();
        const requested = { width: Number(width), height: Number(height) };
        if (!width.trim() || !height.trim() || !isRoomPipSize(requested)) {
          setInvalid(true);
          setError(tx(
            `Enter whole pixels: width ${minWidth}–${maxWidth} and height ${minHeight}–${maxHeight}.`,
            `请输入整数像素：宽度 ${minWidth}–${maxWidth}，高度 ${minHeight}–${maxHeight}。`
          ));
          return;
        }
        resize(requested);
      }}
    >
      <div className="room-companion-size-summary">
        <span role="status" data-companion-size-current="true">{tx(`Current: ${size.width}×${size.height}`, `当前：${size.width}×${size.height}`)}</span>
        <div className="room-companion-size-presets">
          <button type="button" onClick={() => preset(DEFAULT_ROOM_PIP_SIZE)}>{tx("Small · 380×480", "小窗 · 380×480")}</button>
          <button type="button" onClick={() => preset({ width: 480, height: 640 })}>{tx("Medium · 480×640", "中窗 · 480×640")}</button>
        </div>
      </div>
      <div className="room-companion-size-fields">
        <label htmlFor={`${inputId}-width`}>{tx("Width (content px)", "宽度（内容区像素）")}
          <input id={`${inputId}-width`} name="width" type="number" inputMode="numeric" min={minWidth} max={maxWidth} step={1} required value={width} aria-invalid={invalid || undefined} aria-describedby={describedBy} onChange={event => {
            setWidth(event.target.value);
            setError("");
            setInvalid(false);
          }} />
        </label>
        <label htmlFor={`${inputId}-height`}>{tx("Height (content px)", "高度（内容区像素）")}
          <input id={`${inputId}-height`} name="height" type="number" inputMode="numeric" min={minHeight} max={maxHeight} step={1} required value={height} aria-invalid={invalid || undefined} aria-describedby={describedBy} onChange={event => {
            setHeight(event.target.value);
            setError("");
            setInvalid(false);
          }} />
        </label>
        <button type="submit">{tx("Apply size", "应用尺寸")}</button>
      </div>
      <p id={descriptionId} className="room-companion-size-hint">{tx("Browser may limit size. Dimensions refer to the window content area.", "浏览器可能限制尺寸。此处尺寸指窗口内容区域。")}</p>
      {error && <p id={errorId} role="alert" className="room-companion-size-error">{error}</p>}
    </form>
  );
}
