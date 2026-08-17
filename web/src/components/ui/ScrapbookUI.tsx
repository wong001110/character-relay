import {
  Children,
  cloneElement,
  forwardRef,
  isValidElement,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useId
} from "react";
import { FunctionalIcon } from "./FunctionalIcon";
import "./tokens.css";
import "./scrapbook-ui.css";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ControlSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ControlSize;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className = "", variant = "secondary", size = "md", type = "button", ...props },
  ref
) {
  return <button ref={ref} type={type} className={cx("cr-button", `cr-button--${variant}`, `cr-control--${size}`, className)} {...props} />;
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  size?: ControlSize;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className = "", size = "md", type = "button", ...props },
  ref
) {
  return <button ref={ref} type={type} className={cx("cr-icon-button", `cr-control--${size}`, className)} {...props} />;
});

export interface FormFieldProps extends HTMLAttributes<HTMLDivElement> {
  label: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  children: ReactNode;
}

export function FormField({ label, htmlFor, hint, error, required = false, children, className = "", ...props }: FormFieldProps) {
  const generatedId = `cr-field-${useId().replaceAll(":", "")}`;
  const onlyChild = Children.count(children) === 1 && isValidElement<FormFieldControlProps>(children)
    ? children
    : null;
  const autoLabelable = onlyChild ? isAutoLabelableControl(onlyChild) : false;
  const controlId = htmlFor ?? (autoLabelable ? onlyChild?.props.id : undefined) ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = autoLabelable
    ? [onlyChild?.props["aria-describedby"], hintId, errorId].filter(Boolean).join(" ") || undefined
    : undefined;
  const fieldChildren = autoLabelable && onlyChild
    ? cloneElement(onlyChild, { id: controlId, "aria-describedby": describedBy })
    : children;

  return (
    <div className={cx("cr-form-field", Boolean(error) && "cr-form-field--error", className)} {...props}>
      <label className="cr-form-field__label" htmlFor={autoLabelable ? controlId : htmlFor}>{label}{required && <span className="cr-form-field__required" aria-hidden="true">*</span>}</label>
      {hint && <div className="cr-form-field__hint" id={hintId}>{hint}</div>}
      {fieldChildren}
      {error && <div className="cr-form-field__error" id={errorId} role="alert">{error}</div>}
    </div>
  );
}

interface FormFieldControlProps {
  id?: string;
  "aria-describedby"?: string;
}

function isAutoLabelableControl(child: ReactElement<FormFieldControlProps>): boolean {
  if (typeof child.type === "string") {
    return ["input", "select", "textarea"].includes(child.type);
  }
  return child.type === Input || child.type === Select || child.type === Textarea;
}

interface InvalidControlProp {
  invalid?: boolean;
  controlSize?: ControlSize;
}

export type InputProps = InputHTMLAttributes<HTMLInputElement> & InvalidControlProp;
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ className = "", invalid = false, controlSize = "md", ...props }, ref) {
  return <input ref={ref} className={cx("cr-control", "cr-input", `cr-control--${controlSize}`, className)} aria-invalid={invalid || undefined} {...props} />;
});

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & InvalidControlProp;
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea({ className = "", invalid = false, controlSize = "md", ...props }, ref) {
  return <textarea ref={ref} className={cx("cr-control", "cr-textarea", `cr-control--${controlSize}`, className)} aria-invalid={invalid || undefined} {...props} />;
});

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & InvalidControlProp;
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ className = "", invalid = false, controlSize = "md", children, ...props }, ref) {
  return (
    <span className={cx("cr-select-wrap", `cr-control--${controlSize}`)}>
      <select ref={ref} className={cx("cr-control", "cr-select", className)} aria-invalid={invalid || undefined} {...props}>{children}</select>
      <span className="cr-select__chevron" aria-hidden="true"><FunctionalIcon name="chevron" size={14} /></span>
    </span>
  );
});

export interface MarkControlProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: ReactNode;
  description?: ReactNode;
}

export const Checkbox = forwardRef<HTMLInputElement, MarkControlProps>(function Checkbox({ className = "", label, description, disabled, ...props }, ref) {
  return <label className={cx("cr-mark-control", disabled && "is-disabled", className)}><input ref={ref} type="checkbox" disabled={disabled} {...props} /><span className="cr-checkbox-mark" aria-hidden="true">✓</span><span className="cr-mark-control__copy"><span className="cr-mark-control__label">{label}</span>{description && <span className="cr-mark-control__description">{description}</span>}</span></label>;
});

export const Radio = forwardRef<HTMLInputElement, MarkControlProps>(function Radio({ className = "", label, description, disabled, ...props }, ref) {
  return <label className={cx("cr-mark-control", disabled && "is-disabled", className)}><input ref={ref} type="radio" disabled={disabled} {...props} /><span className="cr-radio-mark" aria-hidden="true"><span /></span><span className="cr-mark-control__copy"><span className="cr-mark-control__label">{label}</span>{description && <span className="cr-mark-control__description">{description}</span>}</span></label>;
});

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: ReactNode;
  description?: ReactNode;
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(function Switch({ className = "", label, description, disabled, ...props }, ref) {
  return <label className={cx("cr-switch", disabled && "is-disabled", className)}><input ref={ref} type="checkbox" role="switch" disabled={disabled} {...props} /><span className="cr-switch__track" aria-hidden="true"><span className="cr-switch__knob" /></span>{(label || description) && <span className="cr-mark-control__copy">{label && <span className="cr-mark-control__label">{label}</span>}{description && <span className="cr-mark-control__description">{description}</span>}</span>}</label>;
});

export interface PaperCardProps extends HTMLAttributes<HTMLDivElement> { interactive?: boolean; }
export const PaperCard = forwardRef<HTMLDivElement, PaperCardProps>(function PaperCard({ className = "", interactive = false, ...props }, ref) {
  return <div ref={ref} className={cx("cr-paper-card", interactive && "cr-paper-card--interactive", className)} {...props} />;
});

export type StickyNoteVariant = "note" | "topic" | "reminder" | "character" | "memory" | "temporary" | "warning" | "system";
export interface StickyNoteProps extends HTMLAttributes<HTMLDivElement> { variant?: StickyNoteVariant; size?: "sm" | "md" | "lg"; pinned?: boolean; }
export const StickyNote = forwardRef<HTMLDivElement, StickyNoteProps>(function StickyNote({ className = "", variant = "note", size = "md", pinned = false, children, ...props }, ref) {
  return <div ref={ref} className={cx("cr-sticky-note", `cr-sticky-note--${variant}`, `cr-sticky-note--${size}`, pinned && "cr-sticky-note--pinned", className)} {...props}>{pinned && <span className="cr-sticky-note__pin" aria-hidden="true">●</span>}{children}</div>;
});

export type PageFlagTone = "rose" | "peach" | "yellow" | "mint" | "blue" | "lavender";
export interface PageFlagProps extends ButtonHTMLAttributes<HTMLButtonElement> { tone?: PageFlagTone; active?: boolean; }
export const PageFlag = forwardRef<HTMLButtonElement, PageFlagProps>(function PageFlag({ className = "", tone = "lavender", active = false, type = "button", ...props }, ref) {
  return <button ref={ref} type={type} aria-pressed={active} className={cx("cr-page-flag", `cr-page-flag--${tone}`, active && "is-active", className)} {...props} />;
});

export interface PageFlagGroupProps extends HTMLAttributes<HTMLDivElement> { orientation?: "horizontal" | "vertical"; label?: string; }
export function PageFlagGroup({ className = "", orientation = "vertical", label, ...props }: PageFlagGroupProps) {
  return <div role="group" aria-label={label} className={cx("cr-page-flag-group", `cr-page-flag-group--${orientation}`, className)} {...props} />;
}

export interface PaperTabProps extends ButtonHTMLAttributes<HTMLButtonElement> { tone?: PageFlagTone; active?: boolean; }
export const PaperTab = forwardRef<HTMLButtonElement, PaperTabProps>(function PaperTab({ className = "", tone = "lavender", active = false, type = "button", ...props }, ref) {
  return <button ref={ref} type={type} role="tab" aria-selected={active} className={cx("cr-paper-tab", `cr-paper-tab--${tone}`, active && "is-active", className)} {...props} />;
});

export type StickyLabelVariant = "neutral" | "vision" | "memory" | "tool" | "link" | "image" | "success" | "warning" | "danger";
export interface StickyLabelProps extends HTMLAttributes<HTMLSpanElement> { variant?: StickyLabelVariant; }
export function StickyLabel({ className = "", variant = "neutral", ...props }: StickyLabelProps) { return <span className={cx("cr-sticky-label", `cr-sticky-label--${variant}`, className)} {...props} />; }

export type StampVariant = "success" | "danger" | "info" | "accent";
export interface StampProps extends HTMLAttributes<HTMLSpanElement> { variant?: StampVariant; }
export function Stamp({ className = "", variant = "accent", ...props }: StampProps) { return <span className={cx("cr-stamp", `cr-stamp--${variant}`, className)} {...props} />; }

export interface AnnotationProps extends HTMLAttributes<HTMLSpanElement> { arrow?: boolean; }
export function Annotation({ className = "", arrow = false, children, ...props }: AnnotationProps) {
  return <span className={cx("cr-annotation", className)} {...props}>{children}{arrow && <span className="cr-annotation__arrow" aria-hidden="true">→</span>}</span>;
}

export type AvatarStatus = "active" | "listening" | "thinking" | "idle" | "offline";
export interface AvatarProps extends HTMLAttributes<HTMLSpanElement> { name: string; src?: string; alt?: string; size?: "sm" | "md" | "lg"; status?: AvatarStatus; }
export function Avatar({ className = "", name, src, alt, size = "md", status, ...props }: AvatarProps) {
  const initials = name.trim().split(/\s+/).filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  return <span className={cx("cr-avatar", `cr-avatar--${size}`, className)} role={src ? undefined : "img"} aria-label={src ? undefined : alt ?? name} {...props}>{src ? <img src={src} alt={alt ?? name} /> : <span aria-hidden="true">{initials || "?"}</span>}{status && <span className={cx("cr-avatar__status", `cr-avatar__status--${status}`, className)} aria-hidden="true" />}</span>;
}

export interface CharacterChipProps extends HTMLAttributes<HTMLDivElement> { name: string; avatarSrc?: string; onRemove?: () => void; }
export function CharacterChip({ className = "", name, avatarSrc, onRemove, ...props }: CharacterChipProps) {
  return <div className={cx("cr-character-chip", className)} {...props}><Avatar name={name} src={avatarSrc} size="sm" /><span className="cr-character-chip__name">{name}</span>{onRemove && <button type="button" className="cr-character-chip__remove" onClick={onRemove} aria-label={`Remove ${name}`}><FunctionalIcon name="close" size={13} /></button>}</div>;
}

export interface SettingsRowProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> { title: ReactNode; description?: ReactNode; control: ReactNode; }
export function SettingsRow({ className = "", title, description, control, ...props }: SettingsRowProps) {
  return <div className={cx("cr-settings-row", className)} {...props}><div className="cr-settings-row__copy"><div className="cr-settings-row__title">{title}</div>{description && <div className="cr-settings-row__description">{description}</div>}</div><div className="cr-settings-row__control">{control}</div></div>;
}
