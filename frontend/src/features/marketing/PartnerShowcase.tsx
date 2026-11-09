import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { publicAsset } from "@/app/router/basePath";
import { isExternalMarketingLink, resolveMarketingLink } from "@/features/marketing/resolveLink";

export type PartnerItem = {
  id?: string;
  name?: string;
  logo_src?: string;
  summary?: string;
  cta_label?: string;
  cta_kind?: string;
  cta_value?: string;
  show_qr?: boolean;
  qr_url?: string;
  qr_caption?: string;
  qr_note?: string;
  enabled?: boolean;
};

function resolveMedia(src: string): string {
  const value = src.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value) || value.startsWith("data:") || value.startsWith("/api/")) {
    return value;
  }
  return publicAsset(value.replace(/^\/+/, ""));
}

function PartnerQr({ url, alt }: { url: string; alt: string }) {
  const [dataUrl, setDataUrl] = useState("");

  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(url, {
      width: 180,
      margin: 1,
      color: { dark: "#1b1464", light: "#ffffff" },
      errorCorrectionLevel: "M",
    })
      .then((value) => {
        if (!cancelled) setDataUrl(value);
      })
      .catch(() => {
        if (!cancelled) setDataUrl("");
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (!dataUrl) return <div className="mkt-partner-qr-fallback">QR</div>;
  return <img className="mkt-partner-qr-image" src={dataUrl} alt={alt} width={148} height={148} />;
}

function PartnerCta({
  label,
  kind,
  value,
}: {
  label: string;
  kind: string;
  value: string;
}) {
  if (!label) return null;
  const href = resolveMarketingLink(kind || "external", value || "");
  const external = isExternalMarketingLink(kind || "external");
  if (external) {
    return (
      <a className="mkt-btn mkt-btn-primary" href={href} target="_blank" rel="noopener noreferrer">
        {label}
      </a>
    );
  }
  return (
    <Link className="mkt-btn mkt-btn-primary" to={href}>
      {label}
    </Link>
  );
}

type PartnerShowcaseProps = {
  eyebrow?: string;
  headline?: string;
  partners: PartnerItem[];
};

export function PartnerShowcase({ eyebrow, headline, partners }: PartnerShowcaseProps) {
  const items = partners.filter((partner) => partner.enabled !== false && partner.name);
  if (items.length === 0) return null;

  return (
    <section className="mkt-section mkt-partners">
      <div className="mkt-section-head mkt-partners-head">
        <p className="mkt-eyebrow">{eyebrow || "Our partners"}</p>
        {headline ? <h2 className="mkt-section-title">{headline}</h2> : null}
      </div>
      <div className="mkt-partners-grid">
        {items.map((partner) => {
          const logo = resolveMedia(String(partner.logo_src || ""));
          const qrTarget = String(partner.qr_url || partner.cta_value || "").trim();
          return (
            <article key={partner.id || partner.name} className="mkt-partner-card">
              <div className="mkt-partner-main">
                {logo ? (
                  <img
                    className="mkt-partner-logo"
                    src={logo}
                    alt={`${partner.name} logo`}
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <div className="mkt-partner-logo-fallback">{partner.name}</div>
                )}
                <h3 className="mkt-partner-name">{partner.name}</h3>
                {partner.summary ? <p className="mkt-partner-summary">{partner.summary}</p> : null}
                <PartnerCta
                  label={String(partner.cta_label || "")}
                  kind={String(partner.cta_kind || "external")}
                  value={String(partner.cta_value || "")}
                />
              </div>
              {partner.show_qr && qrTarget ? (
                <div className="mkt-partner-qr">
                  <PartnerQr url={qrTarget} alt={`QR code for ${partner.name}`} />
                  {partner.qr_caption ? (
                    <p className="mkt-partner-qr-caption">{partner.qr_caption}</p>
                  ) : null}
                  {partner.qr_note ? <p className="mkt-partner-qr-note">{partner.qr_note}</p> : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
