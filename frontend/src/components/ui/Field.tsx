import type { ReactNode } from "react";

type FieldProps = {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
};

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required = false,
  children,
  className,
}: FieldProps) {
  const message = error || hint;
  return (
    <label
      className={`ui-field${error ? " is-invalid" : ""}${className ? ` ${className}` : ""}`}
      htmlFor={htmlFor}
    >
      <span className="ui-field-label">
        {label}
        {required ? (
          <span className="field-req" aria-hidden="true">
            *
          </span>
        ) : null}
      </span>
      {children}
      {message ? (
        <span className={`ui-field-hint${error ? " is-error" : ""}`}>{message}</span>
      ) : null}
    </label>
  );
}
