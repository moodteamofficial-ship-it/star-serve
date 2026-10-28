import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import { Field } from "./Field";
import { IconChevronDown } from "./icons";
import {
  flagEmoji,
  getPhoneCountry,
  nationalPlaceholder,
  normalizeNationalNumber,
} from "./phoneCountries";
import { usePhoneCountries } from "./usePhoneCountries";

type PhoneFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  country: string;
  onCountryChange: (iso: string) => void;
  hint?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  fieldClassName?: string;
  id?: string;
  autoComplete?: string;
};

export function PhoneField({
  label,
  value,
  onChange,
  country,
  onCountryChange,
  hint,
  error,
  disabled = false,
  required = false,
  placeholder,
  fieldClassName,
  id,
  autoComplete = "tel-national",
}: PhoneFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const listId = `${inputId}-countries`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const { countries, defaultIso } = usePhoneCountries();

  const selected = getPhoneCountry(country || defaultIso, countries);

  useEffect(() => {
    if (!countries.length) return;
    if (countries.some((row) => row.iso === country)) return;
    onCountryChange(defaultIso);
  }, [countries, country, defaultIso, onCountryChange]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return countries;
    return countries.filter(
      (row) =>
        row.name.toLowerCase().includes(q) ||
        row.iso.toLowerCase().includes(q) ||
        row.dial.includes(q.replace(/^\+/, "")),
    );
  }, [query, countries]);

  useEffect(() => {
    if (!open) return;

    function place() {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const width = Math.max(rect.width, 16.5 * 16);
      const left = Math.min(rect.left, window.innerWidth - width - 8);
      const spaceBelow = window.innerHeight - rect.bottom - 8;
      const openUp = spaceBelow < 240 && rect.top > spaceBelow;
      setMenuStyle({
        position: "fixed",
        left: Math.max(8, left),
        width,
        zIndex: 2500,
        ...(openUp
          ? { bottom: window.innerHeight - rect.top + 6, top: "auto" }
          : { top: rect.bottom + 6, bottom: "auto" }),
      });
    }

    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    const timer = window.setTimeout(() => searchRef.current?.focus(), 0);

    function onPointer(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
      setQuery("");
    }

    document.addEventListener("mousedown", onPointer);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  function onTriggerKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  }

  return (
    <Field
      label={label}
      htmlFor={inputId}
      hint={hint}
      error={error}
      required={required}
      className={fieldClassName}
    >
      <div className={`phone-field${open ? " is-open" : ""}${disabled ? " is-disabled" : ""}`}>
        <button
          ref={triggerRef}
          type="button"
          className="phone-field-code"
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listId}
          aria-label={`Country code ${selected.name} +${selected.dial}`}
          onClick={() => setOpen((prev) => !prev)}
          onKeyDown={onTriggerKey}
        >
          <span className="phone-field-flag" aria-hidden="true">
            {flagEmoji(selected.iso)}
          </span>
          <span className="phone-field-dial">+{selected.dial}</span>
          <IconChevronDown className={`phone-field-caret${open ? " is-open" : ""}`} />
        </button>
        <input
          id={inputId}
          className="phone-field-input"
          type="tel"
          inputMode="tel"
          autoComplete={autoComplete}
          disabled={disabled}
          required={required}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          value={value}
          placeholder={placeholder ?? nationalPlaceholder(selected.iso)}
          onChange={(e) => onChange(normalizeNationalNumber(e.target.value, "live"))}
          onBlur={() => {
            const next = normalizeNationalNumber(value, "blur");
            if (next !== value) onChange(next);
          }}
        />
      </div>

      {open
        ? createPortal(
            <div ref={menuRef} className="phone-field-menu ui-select-menu" style={menuStyle}>
              <div className="ui-select-search">
                <input
                  ref={searchRef}
                  className="ui-select-search-input"
                  type="search"
                  value={query}
                  placeholder="Search country or code"
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search countries"
                />
              </div>
              <div className="ui-select-options" role="listbox" id={listId}>
                {filtered.length === 0 ? (
                  <p className="ui-select-empty">No countries match</p>
                ) : (
                  filtered.map((row) => {
                    const active = row.iso === selected.iso;
                    return (
                      <button
                        key={row.iso}
                        type="button"
                        role="option"
                        aria-selected={active}
                        className={`ui-select-option phone-field-option${active ? " is-selected" : ""}`}
                        onClick={() => {
                          onCountryChange(row.iso);
                          setOpen(false);
                          setQuery("");
                        }}
                      >
                        <span className="phone-field-option-main">
                          <span className="phone-field-flag" aria-hidden="true">
                            {flagEmoji(row.iso)}
                          </span>
                          <span>{row.name}</span>
                        </span>
                        <span className="phone-field-option-dial">+{row.dial}</span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>,
            document.body,
          )
        : null}
    </Field>
  );
}
