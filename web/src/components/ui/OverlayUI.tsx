import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode
} from "react";
import { createPortal } from "react-dom";

import { Button } from "./ScrapbookUI";
import "./overlay-ui.css";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export interface MenuProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  trigger: ReactNode;
  label?: string;
  align?: "start" | "end";
  children: ReactNode;
}

export function Menu({ className = "", trigger, label = "Open menu", align = "end", children, ...props }: MenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

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
    <div ref={rootRef} className={cx("cr-menu", `cr-menu--${align}`, className)} {...props}>
      <button type="button" className="cr-menu__trigger" aria-label={label} aria-haspopup="menu" aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((current) => !current)}>{trigger}</button>
      {open && <div className="cr-menu__panel" id={menuId} role="menu" aria-label={label}>{children}</div>}
    </div>
  );
}

export interface MenuItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  destructive?: boolean;
}

export function MenuItem({ className = "", destructive = false, type = "button", ...props }: MenuItemProps) {
  return <button type={type} role="menuitem" className={cx("cr-menu-item", destructive && "cr-menu-item--danger", className)} {...props} />;
}

export interface ConfirmDialogProps {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: ReactNode;
  cancelLabel?: ReactNode;
  tone?: "default" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "default",
  busy = false,
  onConfirm,
  onCancel
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [open, busy, onCancel]);

  if (!open) return null;
  return createPortal(
    <div className="cr-confirm-dialog__backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
      <section className={cx("cr-confirm-dialog", tone === "danger" && "cr-confirm-dialog--danger")} role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}>
        <span className="cr-confirm-dialog__tape" aria-hidden="true" />
        <h2 id={titleId}>{title}</h2>
        {description && <p id={descriptionId}>{description}</p>}
        <div className="cr-confirm-dialog__actions">
          <Button variant="ghost" disabled={busy} onClick={onCancel}>{cancelLabel}</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} disabled={busy} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </section>
    </div>,
    document.body
  );
}
