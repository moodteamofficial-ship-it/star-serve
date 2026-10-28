import { useId, type InputHTMLAttributes } from "react";
import { Field } from "./Field";

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "className"> & {
  label: string;
  hint?: string;
  error?: string;
  fieldClassName?: string;
};

export function TextField({
  label,
  hint,
  error,
  id,
  fieldClassName,
  required,
  ...inputProps
}: TextFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;

  return (
    <Field
      label={label}
      htmlFor={inputId}
      hint={hint}
      error={error}
      required={Boolean(required)}
      className={fieldClassName}
    >
      <input
        id={inputId}
        className="ui-input"
        required={required}
        aria-invalid={error ? true : undefined}
        {...inputProps}
      />
    </Field>
  );
}
