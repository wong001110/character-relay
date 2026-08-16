import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode
} from "react";

import { Input } from "./ScrapbookUI";
import "./feedback-ui.css";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

export interface StatusIndicatorProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone;
  pulse?: boolean;
}

export function StatusIndicator({
  className = "",
  tone = "neutral",
  pulse = false,
  children,
  ...props
}: StatusIndicatorProps) {
  return (
    <span
      className={cx(
        "cr-status-indicator",
        `cr-status-indicator--${tone}`,
        pulse && "is-pulsing",
        className
      )}
      {...props}
    >
      <span className="cr-status-indicator__dot" aria-hidden="true" />
      {children}
    </span>
  );
}

export interface InspectorSectionProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  density?: "comfortable" | "compact";
  children: ReactNode;
}

export function InspectorSection({
  className = "",
  eyebrow,
  title,
  description,
  actions,
  density = "comfortable",
  children,
  ...props
}: InspectorSectionProps) {
  return (
    <section
      className={cx("cr-inspector-section", `cr-inspector-section--${density}`, className)}
      {...props}
    >
      <header className="cr-inspector-section__header">
        <div>
          {eyebrow && <span className="cr-inspector-section__eyebrow">{eyebrow}</span>}
          <h3>{title}</h3>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className="cr-inspector-section__actions">{actions}</div>}
      </header>
      <div className="cr-inspector-section__body">{children}</div>
    </section>
  );
}

export interface EmptyStateProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  illustration?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({
  className = "",
  title,
  description,
  illustration,
  action,
  ...props
}: EmptyStateProps) {
  return (
    <div className={cx("cr-empty-state", className)} {...props}>
      {illustration && <div className="cr-empty-state__illustration">{illustration}</div>}
      <strong>{title}</strong>
      {description && <p>{description}</p>}
      {action && <div className="cr-empty-state__action">{action}</div>}
    </div>
  );
}

export interface SearchFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const SearchField = forwardRef<HTMLInputElement, SearchFieldProps>(function SearchField(
  { className = "", label = "Search", ...props },
  ref
) {
  return (
    <label className={cx("cr-search-field", className)}>
      <span className="cr-search-field__icon" aria-hidden="true">⌕</span>
      <span className="cr-search-field__sr">{label}</span>
      <Input ref={ref} aria-label={props["aria-label"] ?? label} {...props} />
    </label>
  );
});

export interface TooltipProps extends HTMLAttributes<HTMLSpanElement> {
  content: ReactNode;
  side?: "top" | "bottom";
  children: ReactNode;
}

export function Tooltip({
  className = "",
  content,
  side = "top",
  children,
  ...props
}: TooltipProps) {
  const tooltipId = useId();
  return (
    <span
      className={cx("cr-tooltip", `cr-tooltip--${side}`, className)}
      aria-describedby={tooltipId}
      {...props}
    >
      {children}
      <span className="cr-tooltip__bubble" id={tooltipId} role="tooltip">
        {content}
      </span>
    </span>
  );
}

export interface PopoverProps extends Omit<HTMLAttributes<HTMLDivElement>, "content"> {
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "end";
  label?: string;
}

export function Popover({
  className = "",
  trigger,
  children,
  align = "start",
  label = "Open details",
  ...props
}: PopoverProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={cx("cr-popover", `cr-popover--${align}`, className)} {...props}>
      <button
        type="button"
        className="cr-popover__trigger"
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        {trigger}
      </button>
      {open && (
        <div className="cr-popover__panel" id={panelId} role="dialog" aria-label={label}>
          {children}
        </div>
      )}
    </div>
  );
}

export interface SpinnerProps extends HTMLAttributes<HTMLSpanElement> {
  size?: "sm" | "md" | "lg";
  label?: string;
}

export function Spinner({
  className = "",
  size = "md",
  label = "Loading",
  ...props
}: SpinnerProps) {
  return (
    <span
      className={cx("cr-spinner", `cr-spinner--${size}`, className)}
      role="status"
      aria-label={label}
      {...props}
    >
      <span aria-hidden="true" />
    </span>
  );
}

export interface SkeletonProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "text" | "block" | "circle";
  width?: CSSProperties["width"];
  height?: CSSProperties["height"];
}

export function Skeleton({
  className = "",
  variant = "text",
  width,
  height,
  style,
  ...props
}: SkeletonProps) {
  return (
    <span
      className={cx("cr-skeleton", `cr-skeleton--${variant}`, className)}
      aria-hidden="true"
      style={{ width, height, ...style }}
      {...props}
    />
  );
}

export interface DividerProps extends HTMLAttributes<HTMLDivElement> {
  label?: ReactNode;
}

export function Divider({ className = "", label, ...props }: DividerProps) {
  return (
    <div className={cx("cr-divider", className)} role="separator" {...props}>
      <span aria-hidden="true" />
      {label && <em>{label}</em>}
      <span aria-hidden="true" />
    </div>
  );
}

export interface ToastProps extends HTMLAttributes<HTMLDivElement> {
  tone?: StatusTone;
  title?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
}

export function Toast({
  className = "",
  tone = "neutral",
  title,
  action,
  children,
  ...props
}: ToastProps) {
  return (
    <div
      className={cx("cr-toast", `cr-toast--${tone}`, className)}
      role={tone === "danger" ? "alert" : "status"}
      {...props}
    >
      <span className="cr-toast__pin" aria-hidden="true" />
      <div className="cr-toast__copy">
        {title && <strong>{title}</strong>}
        {children && <p>{children}</p>}
      </div>
      {action && <div className="cr-toast__action">{action}</div>}
    </div>
  );
}
