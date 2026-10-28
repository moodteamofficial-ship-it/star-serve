import { useEffect, useState, type TransitionEvent } from "react";
import { FormError } from "./FormError";

type AnimatedFormErrorProps = {
  error: string | null;
  title?: string;
  className?: string;
};

/** Collapsible error slot — hides while calling, animates in like auth lockout. */
export function AnimatedFormError({
  error,
  title = "Something went wrong",
  className,
}: AnimatedFormErrorProps) {
  const [shown, setShown] = useState<string | null>(null);
  const open = Boolean(error);

  useEffect(() => {
    if (error) {
      setShown(error);
      return;
    }
    const t = window.setTimeout(() => setShown(null), 450);
    return () => window.clearTimeout(t);
  }, [error]);

  function onTransitionEnd(e: TransitionEvent<HTMLDivElement>) {
    if (e.target !== e.currentTarget) return;
    if (!error) setShown(null);
  }

  return (
    <div
      className={`auth-error-slot${className ? ` ${className}` : ""}${open ? " auth-error-slot--open" : ""}`}
      onTransitionEnd={onTransitionEnd}
    >
      <div className="auth-error-slot-inner">
        {shown ? (
          <FormError title={title} className="auth-form-error">
            {shown}
          </FormError>
        ) : null}
      </div>
    </div>
  );
}
