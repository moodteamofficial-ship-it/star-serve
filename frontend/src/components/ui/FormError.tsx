import { useEffect, useRef, type ReactNode } from "react";
import { IconAlert } from "./icons";
import { scrollModalToIssue } from "@/utils/scrollModalToIssue";

type FormErrorProps = {
  children: ReactNode;
  title?: string;
  className?: string;
};

export function FormError({ children, title = "Something went wrong", className }: FormErrorProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (children == null || children === false || children === "") return;
    const panel = ref.current?.closest(".modal-panel");
    if (!panel) return;
    // Prefer an invalid field; otherwise land on this alert.
    if (!scrollModalToIssue(panel)) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      ref.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
    }
  }, [children, title]);

  if (children == null || children === false || children === "") return null;

  return (
    <div
      ref={ref}
      className={`form-error${className ? ` ${className}` : ""}`}
      role="alert"
      aria-live="polite"
    >
      <span className="form-error-icon" aria-hidden="true">
        <IconAlert />
      </span>
      <div className="form-error-copy">
        <strong>{title}</strong>
        <span>{children}</span>
      </div>
    </div>
  );
}
