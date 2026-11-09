import { useState } from "react";
import { publicAsset } from "@/app/router/basePath";
import { websiteApi } from "@/services/website/websiteApi";
import { SelectInput } from "@/features/website/AdminFormFields";

const DEST_OPTIONS = [
  { value: "external", label: "External website" },
  { value: "internal", label: "Page on this website" },
  { value: "quote", label: "Quote portal" },
];

export type PartnerDraft = {
  id: string;
  name: string;
  logo_src: string;
  summary: string;
  cta_label: string;
  cta_kind: string;
  cta_value: string;
  show_qr: boolean;
  qr_url: string;
  qr_caption: string;
  qr_note: string;
  enabled: boolean;
};

export type PartnersSectionDraft = {
  eyebrow: string;
  headline: string;
  partners: PartnerDraft[];
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `partner-${Date.now()}`;
}

function previewSrc(src: string): string {
  const value = src.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value) || value.startsWith("/api/")) return value;
  return publicAsset(value.replace(/^\/+/, ""));
}

export function parsePartnersDraft(raw: Record<string, unknown>): PartnersSectionDraft {
  const partnersRaw = Array.isArray(raw.partners) ? raw.partners : [];
  return {
    eyebrow: String(raw.eyebrow || "Our partners"),
    headline: String(raw.headline || "Trusted partners behind your cover"),
    partners: partnersRaw.map((item, index) => {
      const partner = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
      return {
        id: String(partner.id || `partner-${index + 1}`),
        name: String(partner.name || ""),
        logo_src: String(partner.logo_src || ""),
        summary: String(partner.summary || ""),
        cta_label: String(partner.cta_label || ""),
        cta_kind: String(partner.cta_kind || "external"),
        cta_value: String(partner.cta_value || ""),
        show_qr: Boolean(partner.show_qr),
        qr_url: String(partner.qr_url || ""),
        qr_caption: String(partner.qr_caption || ""),
        qr_note: String(partner.qr_note || ""),
        enabled: partner.enabled !== false,
      };
    }),
  };
}

type PartnersAdminEditorProps = {
  value: PartnersSectionDraft;
  onChange: (next: PartnersSectionDraft) => void;
};

export function PartnersAdminEditor({ value, onChange }: PartnersAdminEditorProps) {
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updatePartner(id: string, patch: Partial<PartnerDraft>) {
    onChange({
      ...value,
      partners: value.partners.map((partner) =>
        partner.id === id ? { ...partner, ...patch } : partner,
      ),
    });
  }

  function movePartner(id: string, direction: -1 | 1) {
    const index = value.partners.findIndex((partner) => partner.id === id);
    if (index < 0) return;
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= value.partners.length) return;
    const partners = [...value.partners];
    const [item] = partners.splice(index, 1);
    partners.splice(nextIndex, 0, item!);
    onChange({ ...value, partners });
  }

  function removePartner(id: string) {
    onChange({ ...value, partners: value.partners.filter((partner) => partner.id !== id) });
  }

  function addPartner() {
    onChange({
      ...value,
      partners: [
        ...value.partners,
        {
          id: newId(),
          name: "",
          logo_src: "",
          summary: "",
          cta_label: "Learn more",
          cta_kind: "external",
          cta_value: "",
          show_qr: false,
          qr_url: "",
          qr_caption: "Scan to quote",
          qr_note: "on your phone",
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
      updatePartner(id, { logo_src: res.data.path });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploadingId(null);
    }
  }

  return (
    <div className="website-carousel-editor">
      <label>
        Small label above the title
        <input
          value={value.eyebrow}
          onChange={(e) => onChange({ ...value, eyebrow: e.target.value })}
        />
      </label>
      <label>
        Section headline
        <input
          value={value.headline}
          onChange={(e) => onChange({ ...value, headline: e.target.value })}
        />
      </label>
      <div className="website-carousel-toolbar">
        <button type="button" className="website-btn website-btn--ghost" onClick={addPartner}>
          Add partner
        </button>
      </div>
      {error ? <p className="website-admin-banner">{error}</p> : null}
      <div className="website-carousel-slides">
        {value.partners.map((partner, index) => (
          <article key={partner.id} className="website-carousel-slide">
            <header>
              <strong>Partner {index + 1}</strong>
              <div className="website-carousel-slide-actions">
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => movePartner(partner.id, -1)}
                  disabled={index === 0}
                >
                  Up
                </button>
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => movePartner(partner.id, 1)}
                  disabled={index === value.partners.length - 1}
                >
                  Down
                </button>
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => removePartner(partner.id)}
                >
                  Remove
                </button>
              </div>
            </header>
            {partner.logo_src ? (
              <img className="website-carousel-preview" src={previewSrc(partner.logo_src)} alt="" />
            ) : (
              <div className="website-carousel-preview is-empty">No logo yet</div>
            )}
            <label>
              Logo upload
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                disabled={uploadingId === partner.id}
                onChange={(e) => void onUpload(partner.id, e.target.files?.[0] ?? null)}
              />
            </label>
            <label>
              Logo URL
              <input
                value={partner.logo_src}
                onChange={(e) => updatePartner(partner.id, { logo_src: e.target.value })}
              />
            </label>
            <label>
              Name
              <input
                value={partner.name}
                onChange={(e) => updatePartner(partner.id, { name: e.target.value })}
              />
            </label>
            <label>
              Summary
              <textarea
                value={partner.summary}
                onChange={(e) => updatePartner(partner.id, { summary: e.target.value })}
                rows={4}
              />
            </label>
            <label>
              Button label
              <input
                value={partner.cta_label}
                onChange={(e) => updatePartner(partner.id, { cta_label: e.target.value })}
              />
            </label>
            <label>
              Button link
              <input
                value={partner.cta_value}
                onChange={(e) => updatePartner(partner.id, { cta_value: e.target.value })}
              />
            </label>
            <label>
              Destination type
              <SelectInput
                value={partner.cta_kind}
                onChange={(cta_kind) => updatePartner(partner.id, { cta_kind })}
                options={DEST_OPTIONS}
                ariaLabel="Destination type"
              />
            </label>
            <label className="website-carousel-check">
              <input
                type="checkbox"
                checked={partner.show_qr}
                onChange={(e) => updatePartner(partner.id, { show_qr: e.target.checked })}
              />
              Show QR code
            </label>
            {partner.show_qr ? (
              <>
                <label>
                  QR destination URL
                  <input
                    value={partner.qr_url}
                    onChange={(e) => updatePartner(partner.id, { qr_url: e.target.value })}
                    placeholder="Defaults to button link"
                  />
                </label>
                <label>
                  QR caption
                  <input
                    value={partner.qr_caption}
                    onChange={(e) => updatePartner(partner.id, { qr_caption: e.target.value })}
                  />
                </label>
                <label>
                  QR note
                  <input
                    value={partner.qr_note}
                    onChange={(e) => updatePartner(partner.id, { qr_note: e.target.value })}
                  />
                </label>
              </>
            ) : null}
            <label className="website-carousel-check">
              <input
                type="checkbox"
                checked={partner.enabled}
                onChange={(e) => updatePartner(partner.id, { enabled: e.target.checked })}
              />
              Visible on site
            </label>
          </article>
        ))}
      </div>
    </div>
  );
}
