import {
  forwardRef,
  useEffect,
  useId,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
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
  function requestClose() {
    if (leaving) return;
    setLeaving(true);
    window.setTimeout(onClose, 190);
  }
  return { leaving, requestClose };
}

function CloseButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" className="notebook-icon-button" onClick={onClick} aria-label={label}>
      <FunctionalIcon name="close" size={18} />
    </button>
  );
}

export function PaperDrawer({ children, onClose, ariaLabel, className = "" }: OverlayProps) {
  const titleId = useId();
  const { leaving, requestClose } = useAnimatedClose(onClose);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) { if (event.key === "Escape") requestClose(); }
    document.addEventListener("keydown", onKeyDown);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKeyDown); document.body.style.overflow = previous; };
  }, []);

  return createPortal(
    <div className={`paper-drawer-backdrop${leaving ? " is-leaving" : ""}`} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) requestClose(); }}>
      <aside className={`paper-drawer-panel ${className}${leaving ? " is-leaving" : ""}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="paper-drawer-topline"><span id={titleId}>{ariaLabel}</span><CloseButton onClick={requestClose} label={ariaLabel} /></div>
        {children}
      </aside>
    </div>,
    document.body
  );
}

export function PaperModal({ children, onClose, ariaLabel, className = "" }: OverlayProps) {
  const titleId = useId();
  const { leaving, requestClose } = useAnimatedClose(onClose);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) { if (event.key === "Escape") requestClose(); }
    document.addEventListener("keydown", onKeyDown);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKeyDown); document.body.style.overflow = previous; };
  }, []);

  return createPortal(
    <div className={`paper-modal-backdrop${leaving ? " is-leaving" : ""}`} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) requestClose(); }}>
      <section className={`paper-modal-sheet ${className}${leaving ? " is-leaving" : ""}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="paper-modal-topline"><span id={titleId}>{ariaLabel}</span><CloseButton onClick={requestClose} label={ariaLabel} /></div>
        {children}
      </section>
    </div>,
    document.body
  );
}