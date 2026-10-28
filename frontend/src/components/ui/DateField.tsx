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
import { IconCalendar, IconChevronLeft, IconChevronRight } from "./icons";

type DateFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  disabled?: boolean;
  required?: boolean;
  fieldClassName?: string;
  id?: string;
  /** Inclusive bounds as YYYY-MM-DD */
  min?: string;
  max?: string;
  placeholder?: string;
};

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"] as const;

function parseIsoDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return null;
  return date;
}

function toIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date: Date, delta: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1);
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatDisplay(value: string): string {
  const date = parseIsoDate(value);
  if (!date) return "";
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function monthLabel(date: Date): string {
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(date);
}

function buildGrid(viewMonth: Date): Array<Date | null> {
  const first = startOfMonth(viewMonth);
  const startPad = first.getDay();
  const daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const cells: Array<Date | null> = [];
  for (let i = 0; i < startPad; i += 1) cells.push(null);
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(new Date(first.getFullYear(), first.getMonth(), day));
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

export function DateField({
  label,
  value,
  onChange,
  hint,
  disabled = false,
  required = false,
  fieldClassName,
  id,
  min,
  max,
  placeholder = "Select date…",
}: DateFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const listId = `${inputId}-calendar`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const selected = useMemo(() => parseIsoDate(value), [value]);
  const minDate = useMemo(() => (min ? parseIsoDate(min) : null), [min]);
  const maxDate = useMemo(() => (max ? parseIsoDate(max) : null), [max]);
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(selected ?? new Date()));

  useEffect(() => {
    if (selected) setViewMonth(startOfMonth(selected));
  }, [selected]);

  const cells = useMemo(() => buildGrid(viewMonth), [viewMonth]);
  const today = useMemo(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }, []);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;

    function place() {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const gap = 6;
      const width = Math.min(Math.max(rect.width, 14.25 * 16), 15.5 * 16);
      const roomBelow = window.innerHeight - rect.bottom - 12;
      const roomAbove = rect.top - 12;
      const openUp = roomBelow < 240 && roomAbove > roomBelow;
      const left = Math.min(rect.left, window.innerWidth - width - 8);
      setMenuStyle({
        position: "fixed",
        left: Math.max(8, left),
        width,
        top: openUp ? undefined : rect.bottom + gap,
        bottom: openUp ? window.innerHeight - rect.top + gap : undefined,
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
  }, [open]);

  useEffect(() => {
    if (!open) return;

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
  }, [open]);

  function isDisabledDay(date: Date): boolean {
    if (minDate && date < minDate) return true;
    if (maxDate && date > maxDate) return true;
    return false;
  }

  function choose(date: Date) {
    if (isDisabledDay(date)) return;
    onChange(toIsoDate(date));
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  }

  const display = selected ? formatDisplay(value) : placeholder;

  return (
    <Field label={label} hint={hint} required={required} className={fieldClassName} htmlFor={inputId}>
      <button
        ref={triggerRef}
        id={inputId}
        type="button"
        className={`ui-select date-field-trigger${open ? " is-open" : ""}${!selected ? " is-placeholder" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={listId}
        aria-required={required || undefined}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="ui-select-value">{display}</span>
        <span className="date-field-icon" aria-hidden="true">
          <IconCalendar />
        </span>
      </button>

      {open
        ? createPortal(
            <div
              ref={menuRef}
              id={listId}
              className="date-calendar ui-select-menu"
              style={menuStyle}
              role="dialog"
              aria-label={label}
            >
              <div className="date-calendar-head">
                <button
                  type="button"
                  className="date-calendar-nav"
                  aria-label="Previous month"
                  onClick={() => setViewMonth((m) => addMonths(m, -1))}
                >
                  <IconChevronLeft />
                </button>
                <p className="date-calendar-title">{monthLabel(viewMonth)}</p>
                <button
                  type="button"
                  className="date-calendar-nav"
                  aria-label="Next month"
                  onClick={() => setViewMonth((m) => addMonths(m, 1))}
                >
                  <IconChevronRight />
                </button>
              </div>

              <div className="date-calendar-weekdays" aria-hidden="true">
                {WEEKDAYS.map((day) => (
                  <span key={day}>{day}</span>
                ))}
              </div>

              <div className="date-calendar-grid" role="grid" aria-label={monthLabel(viewMonth)}>
                {cells.map((date, index) => {
                  if (!date) {
                    return <span key={`pad-${index}`} className="date-calendar-day is-empty" />;
                  }
                  const iso = toIsoDate(date);
                  const disabledDay = isDisabledDay(date);
                  const isSelected = selected ? sameDay(date, selected) : false;
                  const isToday = sameDay(date, today);
                  return (
                    <button
                      key={iso}
                      type="button"
                      role="gridcell"
                      className={`date-calendar-day${isSelected ? " is-selected" : ""}${
                        isToday ? " is-today" : ""
                      }`}
                      disabled={disabledDay}
                      aria-selected={isSelected}
                      aria-current={isToday ? "date" : undefined}
                      onClick={() => choose(date)}
                    >
                      {date.getDate()}
                    </button>
                  );
                })}
              </div>

              <div className="date-calendar-footer">
                <button
                  type="button"
                  className="date-calendar-today"
                  disabled={isDisabledDay(today)}
                  onClick={() => {
                    setViewMonth(startOfMonth(today));
                    choose(today);
                  }}
                >
                  Today
                </button>
                {value ? (
                  <button
                    type="button"
                    className="date-calendar-clear"
                    onClick={() => {
                      onChange("");
                      setOpen(false);
                      triggerRef.current?.focus();
                    }}
                  >
                    Clear
                  </button>
                ) : null}
              </div>
            </div>,
            document.body,
          )
        : null}
    </Field>
  );
}
