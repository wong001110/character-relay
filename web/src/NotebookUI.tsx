import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type RefObject,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes
} from "react";
import { createPortal } from "react-dom";

import { FunctionalIcon } from "./components/ui/FunctionalIcon";

interface FieldProps {
  label: ReactNode;
  guide?: ReactNode;
  className?: string;
  required?: boolean;
  children: ReactNode;
}

export function NotebookField({ label, guide, className = "", required = false, children }: FieldProps) {
  return (
    <label className={`notebook-field ${className}`.trim()}>
      <span className="notebook-field-label">{label}{required && <em aria-hidden="true">*</em>}</span>
      {guide && <small className="notebook-field-guide">{guide}</small>}
      {children}
    </label>
  );
}

export const NotebookInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function NotebookInput({ className = "", ...props }, ref) {
  return <input ref={ref} className={`notebook-control notebook-input ${className}`.trim()} {...props} />;
});

export const NotebookTextarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function NotebookTextarea({ className = "", ...props }, ref) {
  return <textarea ref={ref} className={`notebook-control notebook-textarea ${className}`.trim()} {...props} />;
});

export const NotebookSelect = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function NotebookSelect({ className = "", children, ...props }, ref) {
  return (
    <span className="notebook-select-wrap">
      <select ref={ref} className={`notebook-control notebook-select ${className}`.trim()} {...props}>{children}</select>
      <span className="notebook-select-chevron" aria-hidden="true"><FunctionalIcon name="chevron" size={14} /></span>
    </span>
  );
});

export function NotebookSection({
  label,
  title,
  guide,
  accent = "lavender",
  children
}: {
  label: string;
  title: ReactNode;
  guide: ReactNode;
  accent?: "lavender" | "mint" | "peach" | "rose";
  children: ReactNode;
}) {
  return (
    <section className={`notebook-form-section accent-${accent}`}>
      <div className="notebook-form-section-heading">
        <span className="notebook-section-tab">{label}</span>
        <div><h3>{title}</h3><p>{guide}</p></div>
      </div>
      <div className="notebook-form-section-body">{children}</div>
    </section>
  );
}

interface OverlayProps {
  children: ReactNode;
  onClose: () => void;
  ariaLabel: string;
  className?: string;
}

function useAnimatedClose(onClose: () => void) {
  const [leaving, setLeaving] = useState(false);
  const leavingRef = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const requestClose = useCallback(() => {
    if (leavingRef.current) return;
    leavingRef.current = true;
    setLeaving(true);
    window.setTimeout(() => onCloseRef.current(), 190);
  }, []);
  return { leaving, requestClose };
}

function CloseButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" className="notebook-icon-button" onClick={onClick} aria-label={label}>
      <FunctionalIcon name="close" size={18} />
    </button>
  );
}

const overlayFocusSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])'
].join(",");

function useOverlayLifecycle(
  panelRef: RefObject<HTMLElement | null>,
  requestClose: () => void
) {
  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    function focusableElements() {
      return Array.from(panelRef.current?.querySelectorAll<HTMLElement>(overlayFocusSelector) ?? [])
        .filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        requestClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      const focusable = focusableElements();
      if (!panel || focusable.length === 0) {
        event.preventDefault();
        panel?.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => {
      const first = focusableElements()[0];
      (first ?? panelRef.current)?.focus();
    }, 0);

    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [panelRef, requestClose]);
}

export function PaperDrawer({ children, onClose, ariaLabel, className = "" }: OverlayProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const { leaving, requestClose } = useAnimatedClose(onClose);
  useOverlayLifecycle(panelRef, requestClose);

  return createPortal(
    <div className={`paper-drawer-backdrop${leaving ? " is-leaving" : ""}`} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) requestClose(); }}>
      <aside ref={panelRef} tabIndex={-1} className={`paper-drawer-panel ${className}${leaving ? " is-leaving" : ""}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="paper-drawer-topline"><span id={titleId}>{ariaLabel}</span><CloseButton onClick={requestClose} label={ariaLabel} /></div>
        {children}
      </aside>
    </div>,
    document.body
  );
}

export function PaperModal({ children, onClose, ariaLabel, className = "" }: OverlayProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const { leaving, requestClose } = useAnimatedClose(onClose);
  useOverlayLifecycle(panelRef, requestClose);

  return createPortal(
    <div className={`paper-modal-backdrop${leaving ? " is-leaving" : ""}`} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) requestClose(); }}>
      <section ref={panelRef} tabIndex={-1} className={`paper-modal-sheet ${className}${leaving ? " is-leaving" : ""}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="paper-modal-topline"><span id={titleId}>{ariaLabel}</span><CloseButton onClick={requestClose} label={ariaLabel} /></div>
        {children}
      </section>
    </div>,
    document.body
  );
}
