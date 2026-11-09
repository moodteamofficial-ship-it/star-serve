import { useState } from "react";
import { publicAsset } from "@/app/router/basePath";
import { websiteApi } from "@/services/website/websiteApi";
import { SelectInput } from "@/features/website/AdminFormFields";

const DEST_OPTIONS = [
  { value: "external", label: "External website" },
  { value: "internal", label: "Page on this website" },
  { value: "quote", label: "Quote portal" },
  { value: "quote_product", label: "Quote a product" },
];

function previewSrc(src: string): string {
  const value = src.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value) || value.startsWith("/api/")) return value;
  return publicAsset(value.replace(/^\/+/, ""));
}

export type CarouselSlideDraft = {
  id: string;
  image_src: string;
  image_alt: string;
  href: string;
  href_kind: string;
  enabled: boolean;
};

export type CarouselDraft = {
  autoplay: boolean;
  interval_ms: number;
  slides: CarouselSlideDraft[];
};

function newSlideId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `slide-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function parseCarouselDraft(raw: Record<string, unknown>): CarouselDraft {
  const slidesRaw = Array.isArray(raw.slides) ? raw.slides : [];
  return {
    autoplay: raw.autoplay !== false,
    interval_ms: Number(raw.interval_ms || 5500),
    slides: slidesRaw.map((item, index) => {
      const slide = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
      return {
        id: String(slide.id || `slide-${index + 1}`),
        image_src: String(slide.image_src || ""),
        image_alt: String(slide.image_alt || ""),
        href: String(slide.href || ""),
        href_kind: String(slide.href_kind || "external"),
        enabled: slide.enabled !== false,
      };
    }),
  };
}

type CarouselAdminEditorProps = {
  value: CarouselDraft;
  onChange: (next: CarouselDraft) => void;
};

export function CarouselAdminEditor({ value, onChange }: CarouselAdminEditorProps) {
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateSlide(id: string, patch: Partial<CarouselSlideDraft>) {
    onChange({
      ...value,
      slides: value.slides.map((slide) => (slide.id === id ? { ...slide, ...patch } : slide)),
    });
  }

  function moveSlide(id: string, direction: -1 | 1) {
    const index = value.slides.findIndex((slide) => slide.id === id);
    if (index < 0) return;
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= value.slides.length) return;
    const slides = [...value.slides];
    const [item] = slides.splice(index, 1);
    slides.splice(nextIndex, 0, item!);
    onChange({ ...value, slides });
  }

  function removeSlide(id: string) {
    onChange({ ...value, slides: value.slides.filter((slide) => slide.id !== id) });
  }

  function addSlide() {
    onChange({
      ...value,
      slides: [
        ...value.slides,
        {
          id: newSlideId(),
          image_src: "",
          image_alt: "",
          href: "",
          href_kind: "external",
          enabled: true,
        },
      ],
    });
  }

  async function onUpload(id: string, file: File | null) {
    if (!file) return;
    setError(null);
    setUploadingId(id);
    try {
      const res = await websiteApi.uploadMedia(file);
      updateSlide(id, { image_src: res.data.path });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploadingId(null);
    }
  }

  return (
    <div className="website-carousel-editor">
      <div className="website-carousel-toolbar">
        <label className="website-carousel-check">
          <input
            type="checkbox"
            checked={value.autoplay}
            onChange={(e) => onChange({ ...value, autoplay: e.target.checked })}
          />
          Scroll banners automatically
        </label>
        <label>
          Seconds between banners
          <input
            type="number"
            min={3}
            step={0.5}
            value={Math.round(value.interval_ms / 100) / 10}
            onChange={(e) =>
              onChange({
                ...value,
                interval_ms: Math.max(3000, Math.round((Number(e.target.value) || 5.5) * 1000)),
              })
            }
          />
        </label>
        <button type="button" className="website-btn website-btn--ghost" onClick={addSlide}>
          Add banner
        </button>
      </div>

      {error ? <p className="website-admin-banner">{error}</p> : null}

      <div className="website-carousel-slides">
        {value.slides.map((slide, index) => (
          <article key={slide.id} className="website-carousel-slide">
            <header>
              <strong>Banner {index + 1}</strong>
              <div className="website-carousel-slide-actions">
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => moveSlide(slide.id, -1)}
                  disabled={index === 0}
                >
                  Up
                </button>
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => moveSlide(slide.id, 1)}
                  disabled={index === value.slides.length - 1}
                >
                  Down
                </button>
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => removeSlide(slide.id)}
                >
                  Remove
                </button>
              </div>
            </header>

            {slide.image_src ? (
              <img className="website-carousel-preview" src={previewSrc(slide.image_src)} alt="" />
            ) : (
              <div className="website-carousel-preview is-empty">No image yet</div>
            )}

            <label>
              Image upload
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                disabled={uploadingId === slide.id}
                onChange={(e) => void onUpload(slide.id, e.target.files?.[0] ?? null)}
              />
            </label>
            <label>
              Image path or URL
              <input
                value={slide.image_src}
                onChange={(e) => updateSlide(slide.id, { image_src: e.target.value })}
                placeholder="/marketing/banner.jpg"
              />
            </label>
            <label>
              Image description
              <input
                value={slide.image_alt}
                onChange={(e) => updateSlide(slide.id, { image_alt: e.target.value })}
              />
            </label>
            <label>
              Click destination
              <input
                value={slide.href}
                onChange={(e) => updateSlide(slide.id, { href: e.target.value })}
                placeholder="https://…"
              />
            </label>
            <label>
              Destination type
              <SelectInput
                value={slide.href_kind}
                onChange={(href_kind) => updateSlide(slide.id, { href_kind })}
                options={DEST_OPTIONS}
                ariaLabel="Destination type"
              />
            </label>
            <label className="website-carousel-check">
              <input
                type="checkbox"
                checked={slide.enabled}
                onChange={(e) => updateSlide(slide.id, { enabled: e.target.checked })}
              />
              Show this banner
            </label>
            {uploadingId === slide.id ? <p className="website-admin-muted">Uploading…</p> : null}
          </article>
        ))}
      </div>
    </div>
  );
}
