import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import { Field } from "./Field";

export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
  /** Compact chip shown on the option and on the closed trigger when selected. */
  badge?: string;
};

type SelectProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  hint?: string;
  /** Soft status chip on the closed trigger (blends with the field). */
  badge?: string;
  fieldClassName?: string;
  /** Force search on/off. Default: on when there are 8+ options. */
  searchable?: boolean;
  searchThreshold?: number;
};

const DEFAULT_SEARCH_THRESHOLD = 8;

/** Title-case labels and collapse messy whitespace. */
export function formatSelectLabel(label: string): string {
  const cleaned = label.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  return cleaned
    .toLowerCase()
    .replace(/(^|[\s(/—-])([a-z])/g, (_, edge: string, letter: string) => edge + letter.toUpperCase())
    .replace(/\bTpo\b/g, "TPO")
    .replace(/\bPsv\b/g, "PSV")
    .replace(/\bIra\b/g, "IRA")
    .replace(/\bKes\b/g, "KES")
    .replace(/\bId\b/g, "ID")
    .replace(/\bSms\b/g, "SMS")
    .replace(/\bWhatsapp\b/g, "WhatsApp")
    .replace(/\bChauffer\b/gi, "Chauffeur");
}

export function Select({
  label,
  value,
  onChange,
  options,
  placeholder = "Select…",
  disabled = false,
  required = false,
  hint,
  badge,
  fieldClassName,
  searchable,
  searchThreshold = DEFAULT_SEARCH_THRESHOLD,
}: SelectProps) {
  const autoId = useId();
  const listId = `${autoId}-list`;
  const searchId = `${autoId}-search`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});

  const normalizedOptions = useMemo(
    () =>
      options.map((opt) => ({
        ...opt,
        label: formatSelectLabel(opt.label),
      })),
    [options],
  );

  const showSearch = searchable ?? normalizedOptions.length >= searchThreshold;
  const selected = normalizedOptions.find((opt) => opt.value === value);
  const display = selected?.label || placeholder;
  const triggerBadge = badge || selected?.badge;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return normalizedOptions;
    return normalizedOptions.filter((opt) => opt.label.toLowerCase().includes(q));
  }, [normalizedOptions, query]);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;

    function place() {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const gap = 6;
      const roomBelow = window.innerHeight - rect.bottom - 12;
      const roomAbove = rect.top - 12;
      const preferred = showSearch ? 340 : 280;
      const openUp = roomBelow < 160 && roomAbove > roomBelow;
      const maxHeight = Math.min(preferred, openUp ? roomAbove : roomBelow);
      setMenuStyle({
        position: "fixed",
        left: rect.left,
        width: Math.max(rect.width, showSearch ? 220 : rect.width),
        top: openUp ? undefined : rect.bottom + gap,
        bottom: openUp ? window.innerHeight - rect.top + gap : undefined,
        maxHeight,
        zIndex: 2500,
      });
    }

    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, showSearch]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }

    if (showSearch) {
      requestAnimationFrame(() => searchRef.current?.focus());
    }

    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    }

    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, showSearch]);

  function choose(next: string) {
    onChange(next);
    setOpen(false);
    setQuery("");
    triggerRef.current?.focus();
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  }

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      const first = filtered.find((opt) => !opt.disabled);
      if (first) choose(first.value);
    }
  }

  return (
    <Field label={label} hint={hint} required={required} className={fieldClassName}>
      <button
        ref={triggerRef}
        id={autoId}
        type="button"
        className={`ui-select${open ? " is-open" : ""}${!selected ? " is-placeholder" : ""}${triggerBadge ? " has-badge" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-required={required || undefined}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="ui-select-value">{display}</span>
        {triggerBadge ? <span className="ui-select-badge">{triggerBadge}</span> : null}
        <span className="ui-select-chevron" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      {open
        ? createPortal(
            <div
              ref={menuRef}
              className={`ui-select-menu${showSearch ? " has-search" : ""}`}
              style={menuStyle}
            >
              {showSearch ? (
                <div className="ui-select-search">
                  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                    <circle cx="11" cy="11" r="6.5" />
                    <path d="m16.2 16.2 3.3 3.3" strokeLinecap="round" />
                  </svg>
                  <input
                    ref={searchRef}
                    id={searchId}
                    type="search"
                    className="ui-select-search-input"
                    value={query}
                    placeholder={`Search ${label.toLowerCase()}…`}
                    aria-label={`Search ${label}`}
                    autoComplete="off"
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={onSearchKeyDown}
                  />
                </div>
              ) : null}

              <div id={listId} className="ui-select-options" role="listbox" aria-label={label}>
                {filtered.length === 0 ? (
                  <div className="ui-select-empty">
                    {normalizedOptions.length === 0 ? "No options" : "No matches"}
                  </div>
                ) : (
                  filtered.map((opt) => {
                    const isActive = opt.value === value;
                    return (
                      <button
                        key={opt.value || "__empty"}
                        type="button"
                        role="option"
                        aria-selected={isActive}
                        disabled={opt.disabled}
                        className={`ui-select-option${isActive ? " is-selected" : ""}${opt.badge ? " has-badge" : ""}`}
                        onClick={() => !opt.disabled && choose(opt.value)}
                      >
                        <span className="ui-select-option-main">
                          <span>{opt.label}</span>
                          {opt.badge ? <span className="ui-select-badge">{opt.badge}</span> : null}
                        </span>
                        {isActive ? (
                          <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        ) : null}
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
