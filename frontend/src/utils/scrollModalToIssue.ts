/** Smoothly scroll the open modal to the first invalid field or form alert. */

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function scrollModalToIssue(scope?: Element | null): boolean {
  const root =
    scope ??
    document.querySelector(".modal-root.is-open .modal-panel") ??
    document.querySelector(".modal-panel");
  if (!root) return false;

  const target =
    root.querySelector<HTMLElement>(
      "input[aria-invalid='true'], textarea[aria-invalid='true'], select[aria-invalid='true'], [aria-invalid='true']",
    ) ??
    root.querySelector<HTMLElement>(".ui-field.is-invalid") ??
    root.querySelector<HTMLElement>(
      "input:invalid:not(:disabled), select:invalid:not(:disabled), textarea:invalid:not(:disabled)",
    ) ??
    root.querySelector<HTMLElement>(".form-error[role='alert'], [role='alert'].form-error");

  if (!target) return false;

  const behavior: ScrollBehavior = prefersReducedMotion() ? "auto" : "smooth";
  target.scrollIntoView({ behavior, block: "center" });

  const focusable = target.matches("input, select, textarea, button")
    ? target
    : target.querySelector<HTMLElement>(
        "input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])",
      );
  focusable?.focus({ preventScroll: true });
  return true;
}
