import {
  forwardRef,
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

export interface InspectorSectionProps extends HTMLAttributes<HTMLElement> {
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

export interface EmptyStateProps extends HTMLAttributes<HTMLDivElement> {
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
