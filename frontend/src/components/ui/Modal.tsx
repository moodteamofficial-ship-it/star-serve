import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { scrollModalToIssue } from "@/utils/scrollModalToIssue";

const MODAL_ANIM_MS = 340;

type ModalProps = {
  open: boolean;
  title: string;
  subtitle?: ReactNode;
  icon?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg" | "xl" | "fit";
  bodyClassName?: string;
  /** Extra class on the dialog panel (e.g. welcome type scale). */
  panelClassName?: string;
  /** When false, Escape / backdrop / X cannot close the dialog. Default true. */
  dismissible?: boolean;
};

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" aria-hidden="true">
      <path
        d="M6 6l12 12M18 6 6 18"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Modal({
  open,
  title,
  subtitle,
  icon,
  onClose,
  children,
  footer,
  size = "md",
  bodyClassName,
  panelClassName,
  dismissible = true,
}: ModalProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [mounted, setMounted] = useState(open);
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (open) {
      setMounted(true);
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion) {
        setEntered(true);
        return;
      }
      let outer = 0;
      let inner = 0;
      outer = window.requestAnimationFrame(() => {
        inner = window.requestAnimationFrame(() => setEntered(true));
      });
      return () => {
        window.cancelAnimationFrame(outer);
        window.cancelAnimationFrame(inner);
      };
    }

    setEntered(false);
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const t = window.setTimeout(() => setMounted(false), reduceMotion ? 0 : MODAL_ANIM_MS);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!mounted) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    // Focus the dialog once on open so inputs keep focus while typing.
    if (panel && !panel.contains(document.activeElement)) {
      panel.focus();
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && dismissible) onCloseRef.current();
    }

    function onInvalid() {
      scrollModalToIssue(panelRef.current);
    }

    document.addEventListener("keydown", onKeyDown);
    panel?.addEventListener("invalid", onInvalid, true);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      panel?.removeEventListener("invalid", onInvalid, true);
      document.body.style.overflow = overflow;
      previousFocusRef.current?.focus?.();
      previousFocusRef.current = null;
    };
  }, [mounted, dismissible]);

  if (!mounted || typeof document === "undefined") return null;

  return createPortal(
    <div
      className={`modal-root${entered ? " is-open" : ""}${dismissible ? "" : " modal-root--locked"}`}
      role="presentation"
    >
      {dismissible ? (
        <button
          type="button"
          className="modal-backdrop"
          aria-label="Close dialog"
          onClick={() => onCloseRef.current()}
        />
      ) : (
        <div className="modal-backdrop" aria-hidden="true" />
      )}
      <div
        ref={panelRef}
        className={`modal-panel modal-panel--${size}${panelClassName ? ` ${panelClassName}` : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className={`modal-header${icon ? " modal-header--with-icon" : ""}`}>
          <div className="modal-heading">
            {icon ? (
              <span className="modal-heading-icon" aria-hidden="true">
                {icon}
              </span>
            ) : null}
            <div className="modal-heading-copy">
              <h2 id={titleId}>{title}</h2>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
          </div>
          {dismissible ? (
            <button
              type="button"
              className="modal-close"
              onClick={() => onCloseRef.current()}
              aria-label="Close"
            >
              <CloseIcon />
            </button>
          ) : null}
        </header>
        <div className={`modal-body${bodyClassName ? ` ${bodyClassName}` : ""}`}>{children}</div>
        {footer ? <footer className="modal-footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  );
}
