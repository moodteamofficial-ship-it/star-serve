import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { publicAsset } from "@/app/router/basePath";
import { websiteApi } from "@/services/website/websiteApi";
import { LINK_KIND_OPTIONS } from "@/features/website/adminLabels";

export function previewSrc(src: string): string {
  const value = src.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value) || value.startsWith("/api/") || value.startsWith("data:")) {
    return value;
  }
  return publicAsset(value.replace(/^\/+/, ""));
}

export function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="website-form-section">
      <header className="website-form-section-head">
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </header>
      <div className="website-form-section-body">{children}</div>
    </section>
  );
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={className ? `website-field ${className}` : "website-field"}>
      <span className="website-field-label">{label}</span>
      {children}
      {hint ? <span className="website-field-hint">{hint}</span> : null}
    </label>
  );
}

export function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      className="website-input"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function TextArea({
  value,
  onChange,
  rows = 3,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
}) {
  return (
    <textarea
      className="website-textarea"
      value={value}
      rows={rows}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function SelectInput({
  value,
  onChange,
  options,
  placeholder = "Choose…",
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<{ value: string; label: string }>;
  placeholder?: string;
  ariaLabel?: string;
}) {
  const autoId = useId();
  const listId = `${autoId}-list`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});

  const selected = options.find((option) => option.value === value);
  const display = selected?.label || placeholder;

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;

    function place() {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const gap = 6;
      const roomBelow = window.innerHeight - rect.bottom - 12;
      const roomAbove = rect.top - 12;
      const openUp = roomBelow < 160 && roomAbove > roomBelow;
      const maxHeight = Math.min(280, openUp ? roomAbove : roomBelow);
      setMenuStyle({
        position: "fixed",
        left: rect.left,
        width: Math.max(rect.width, 200),
        top: openUp ? undefined : rect.bottom + gap,
        bottom: openUp ? window.innerHeight - rect.top + gap : undefined,
        maxHeight,
        zIndex: 2600,
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

  function choose(next: string) {
    onChange(next);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  }

  return (
    <div className="website-select">
      <button
        ref={triggerRef}
        id={autoId}
        type="button"
        className={`website-select-trigger${open ? " is-open" : ""}${!selected ? " is-placeholder" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="website-select-value">{display}</span>
        <span className="website-select-chevron" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      {open
        ? createPortal(
            <div ref={menuRef} className="website-select-menu" style={menuStyle}>
              <div id={listId} className="website-select-options" role="listbox" aria-label={ariaLabel || "Options"}>
                {options.map((option) => {
                  const isActive = option.value === value;
                  return (
                    <button
                      key={option.value || "__empty"}
                      type="button"
                      role="option"
                      aria-selected={isActive}
                      className={`website-select-option${isActive ? " is-selected" : ""}`}
                      onClick={() => choose(option.value)}
                    >
                      <span>{option.label}</span>
                      {isActive ? (
                        <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="website-toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function LinkFields({
  labelPrefix,
  labelValue,
  kindValue,
  valueValue,
  onLabelChange,
  onKindChange,
  onValueChange,
}: {
  labelPrefix: string;
  labelValue: string;
  kindValue: string;
  valueValue: string;
  onLabelChange: (value: string) => void;
  onKindChange: (value: string) => void;
  onValueChange: (value: string) => void;
}) {
  return (
    <FormSection title={labelPrefix}>
      <div className="website-field-grid">
        <Field label="Button text">
          <TextInput value={labelValue} onChange={onLabelChange} placeholder="Get Instant Cover" />
        </Field>
        <Field label="Goes to">
          <SelectInput value={kindValue} onChange={onKindChange} options={LINK_KIND_OPTIONS} />
        </Field>
        <Field label="Destination" className="website-field--span-2">
          <TextInput
            value={valueValue}
            onChange={onValueChange}
            placeholder="/services or https://…"
          />
        </Field>
      </div>
    </FormSection>
  );
}

export function ImageField({
  label,
  src,
  alt,
  onSrcChange,
  onAltChange,
}: {
  label: string;
  src: string;
  alt: string;
  onSrcChange: (value: string) => void;
  onAltChange: (value: string) => void;
}) {
  const inputId = useId();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onUpload(file: File | null) {
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const res = await websiteApi.uploadMedia(file);
      onSrcChange(res.data.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <FormSection title={label}>
      <div className="website-image-layout">
        {src ? (
          <img className="website-image-preview" src={previewSrc(src)} alt="" />
        ) : (
          <div className="website-image-preview is-empty">No image yet</div>
        )}
        <div className="website-image-controls">
          <div className="website-upload-row">
            <label className="website-btn website-btn--ghost website-upload-btn" htmlFor={inputId}>
              {uploading ? "Uploading…" : "Choose image"}
            </label>
            <input
              id={inputId}
              className="website-file-input"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={uploading}
              onChange={(e) => void onUpload(e.target.files?.[0] ?? null)}
            />
          </div>
          <Field label="Image path">
            <TextInput
              value={src}
              onChange={onSrcChange}
              placeholder="/marketing/posts/example.jpg"
            />
          </Field>
          <Field label="Image description">
            <TextInput value={alt} onChange={onAltChange} placeholder="Describe the photo" />
          </Field>
          {error ? <p className="website-admin-banner is-error">{error}</p> : null}
        </div>
      </div>
    </FormSection>
  );
}

export function ItemCard({
  title,
  onMoveUp,
  onMoveDown,
  onRemove,
  canMoveUp,
  canMoveDown,
  children,
}: {
  title: string;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onRemove?: () => void;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  children: ReactNode;
}) {
  return (
    <article className="website-item-card">
      <header className="website-item-card-header">
        <strong>{title}</strong>
        <div className="website-item-card-actions">
          {onMoveUp ? (
            <button type="button" className="website-btn website-btn--ghost" onClick={onMoveUp} disabled={!canMoveUp}>
              Up
            </button>
          ) : null}
          {onMoveDown ? (
            <button
              type="button"
              className="website-btn website-btn--ghost"
              onClick={onMoveDown}
              disabled={!canMoveDown}
            >
              Down
            </button>
          ) : null}
          {onRemove ? (
            <button type="button" className="website-btn website-btn--ghost" onClick={onRemove}>
              Remove
            </button>
          ) : null}
        </div>
      </header>
      <div className="website-item-card-body">{children}</div>
    </article>
  );
}
