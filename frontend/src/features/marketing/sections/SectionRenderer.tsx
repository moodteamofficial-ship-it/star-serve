import { Link } from "react-router-dom";
import { publicAsset } from "@/app/router/basePath";
import { PartnerShowcase, type PartnerItem } from "@/features/marketing/PartnerShowcase";
import { PromoCarousel, type PromoSlide } from "@/features/marketing/PromoCarousel";
import { StoryGrid, type StoryPost } from "@/features/marketing/StoryGrid";
import { isExternalMarketingLink, resolveMarketingLink } from "@/features/marketing/resolveLink";
import type { WebsiteSection } from "@/services/website/websiteApi";

type LinkButtonProps = {
  label: string;
  kind?: string;
  value?: string;
  className?: string;
};

function CmsLink({ label, kind, value, className }: LinkButtonProps) {
  if (!label) return null;
  const href = resolveMarketingLink(kind || "internal", value || "/");
  const external = isExternalMarketingLink(kind || "");
  if (external) {
    return (
      <a className={className} href={href} rel="noopener noreferrer">
        {label}
      </a>
    );
  }
  return (
    <Link className={className} to={href}>
      {label}
    </Link>
  );
}

function resolveCmsImage(src: unknown): string | null {
  if (typeof src !== "string" || !src.trim()) return null;
  const value = src.trim();
  if (/^https?:\/\//i.test(value) || value.startsWith("data:")) return value;
  return publicAsset(value.replace(/^\/+/, ""));
}

function HeroHeadline({ text }: { text: string }) {
  const accent = "Touch Away";
  const idx = text.indexOf(accent);
  if (idx === -1) {
    return <h1 className="mkt-hero-title">{text}</h1>;
  }
  return (
    <h1 className="mkt-hero-title">
      {text.slice(0, idx)}
      <span className="mkt-hero-accent">{accent}</span>
      {text.slice(idx + accent.length)}
    </h1>
  );
}

function HeroSection({ content }: { content: Record<string, unknown> }) {
  const imageSrc = resolveCmsImage(content.image_src);
  const imageAlt = String(content.image_alt || "Star Serve Insurance Agency");

  return (
    <section className={`mkt-hero${imageSrc ? " mkt-hero--split" : " mkt-hero--text"}`}>
      <div className="mkt-hero-copy">
        {content.eyebrow ? <p className="mkt-eyebrow">{String(content.eyebrow)}</p> : null}
        {content.headline ? <HeroHeadline text={String(content.headline)} /> : null}
        {content.description ? <p className="mkt-lead">{String(content.description)}</p> : null}
        <div className="mkt-hero-actions">
          <CmsLink
            label={String(content.primary_label || "")}
            kind={String(content.primary_kind || "quote")}
            value={String(content.primary_value || "")}
            className="mkt-btn mkt-btn-primary"
          />
          <CmsLink
            label={String(content.secondary_label || "")}
            kind={String(content.secondary_kind || "internal")}
            value={String(content.secondary_value || "")}
            className="mkt-btn mkt-btn-ghost"
          />
        </div>
      </div>
      {imageSrc ? (
        <figure className="mkt-hero-media">
          <img src={imageSrc} alt={imageAlt} loading="eager" decoding="async" />
        </figure>
      ) : null}
    </section>
  );
}

function ServiceGridSection({ content }: { content: Record<string, unknown> }) {
  const services = (content.services as Array<Record<string, string>>) || [];
  return (
    <section className="mkt-section mkt-services">
      <div className="mkt-section-head mkt-services-head">
        <p className="mkt-eyebrow">Our cover</p>
        {content.headline ? <h2 className="mkt-section-title">{String(content.headline)}</h2> : null}
        {content.description ? <p className="mkt-muted">{String(content.description)}</p> : null}
      </div>
      <div className="mkt-services-grid">
        {services.map((svc, index) => (
          <a
            key={svc.slug || svc.title}
            className="mkt-service"
            href={resolveMarketingLink("quote_product", svc.slug || "")}
          >
            <span className="mkt-service-index" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="mkt-service-body">
              <span className="mkt-service-title">{svc.title}</span>
              <span className="mkt-service-summary">{svc.summary}</span>
            </span>
            <span className="mkt-service-cta">
              Get a quote
              <span aria-hidden="true">→</span>
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

function StatisticsSection({ content }: { content: Record<string, unknown> }) {
  const items = (content.items as Array<Record<string, string | boolean>>) || [];
  if (items.length === 0) return null;

  return (
    <section className="mkt-section mkt-stats">
      <div className="mkt-section-head mkt-stats-head">
        <p className="mkt-eyebrow">{String(content.eyebrow || "By the numbers")}</p>
      </div>
      <div className="mkt-stats-grid">
        {items.map((item) => (
          <article key={String(item.label)} className="mkt-stat">
            <p className="mkt-stat-value">{String(item.value)}</p>
            <p className="mkt-stat-label">{String(item.label)}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function BenefitsSection({ content }: { content: Record<string, unknown> }) {
  const items = (content.items as Array<Record<string, string>>) || [];
  return (
    <section className="mkt-section mkt-benefits">
      <div className="mkt-section-head mkt-benefits-head">
        <p className="mkt-eyebrow">Why Star Serve</p>
        {content.headline ? <h2 className="mkt-section-title">{String(content.headline)}</h2> : null}
      </div>
      <div className="mkt-benefits-grid">
        {items.map((item, index) => (
          <article key={item.title} className="mkt-benefit">
            <span className="mkt-service-index" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="mkt-benefit-body">
              <h3 className="mkt-benefit-title">{item.title}</h3>
              <p className="mkt-benefit-copy">{item.body}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function AgentPromotionSection({ content }: { content: Record<string, unknown> }) {
  const bullets = (content.bullets as string[]) || [];
  return (
    <section className="mkt-section mkt-agents">
      <div className="mkt-agents-panel">
        <div className="mkt-agents-copy">
          <p className="mkt-eyebrow">Independent agents</p>
          {content.headline ? (
            <h2 className="mkt-section-title">{String(content.headline)}</h2>
          ) : null}
          {content.description ? (
            <p className="mkt-muted">{String(content.description)}</p>
          ) : null}
          <div className="mkt-hero-actions mkt-agents-actions">
            <CmsLink
              label={String(content.primary_label || "")}
              kind={String(content.primary_kind || "")}
              value={String(content.primary_value || "")}
              className="mkt-btn mkt-btn-primary"
            />
            <CmsLink
              label={String(content.secondary_label || "")}
              kind={String(content.secondary_kind || "")}
              value={String(content.secondary_value || "")}
              className="mkt-btn mkt-btn-ghost"
            />
          </div>
        </div>
        {bullets.length > 0 ? (
          <ul className="mkt-agents-points">
            {bullets.map((bullet, index) => (
              <li key={bullet} className="mkt-agents-point">
                <span className="mkt-service-index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="mkt-agents-point-label">{bullet}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

function CtaSection({ content }: { content: Record<string, unknown> }) {
  return (
    <section className="mkt-section mkt-cta">
      <div className="mkt-cta-panel">
        <div className="mkt-cta-copy">
          <p className="mkt-eyebrow">Ready when you are</p>
          {content.headline ? (
            <h2 className="mkt-section-title">{String(content.headline)}</h2>
          ) : null}
          {content.description ? (
            <p className="mkt-muted">{String(content.description)}</p>
          ) : null}
        </div>
        <div className="mkt-hero-actions mkt-cta-actions">
          <CmsLink
            label={String(content.primary_label || "Get Instant Cover")}
            kind={String(content.primary_kind || "quote")}
            value={String(content.primary_value || "")}
            className="mkt-btn mkt-btn-primary"
          />
        </div>
      </div>
    </section>
  );
}

function EditorialSection({ content }: { content: Record<string, unknown> }) {
  return (
    <section className="mkt-section mkt-mission">
      <div className="mkt-mission-panel">
        <div className="mkt-mission-copy">
          <p className="mkt-eyebrow">{String(content.eyebrow || "About Star Serve")}</p>
          {content.headline ? (
            <h2 className="mkt-section-title">{String(content.headline)}</h2>
          ) : null}
          {content.body ? <p className="mkt-prose">{String(content.body)}</p> : null}
        </div>
        <figure className="mkt-mission-media">
          <img
            src={
              resolveCmsImage(content.image_src) ||
              publicAsset("starserve-team.jpg")
            }
            alt={String(content.image_alt || "Star Serve Insurance Agency team")}
            loading="lazy"
            decoding="async"
          />
        </figure>
      </div>
    </section>
  );
}

function EditorialImageSection({ content }: { content: Record<string, unknown> }) {
  const layout = String(content.layout || "image_right");
  const imageSrc = resolveCmsImage(content.image_src);
  if (!imageSrc) return null;

  const imageAlt = String(content.image_alt || "Star Serve Insurance Agency");
  const mediaStyle = String(content.media_style || "");
  const imageFit = String(content.image_fit || "contain");
  const layoutClass =
    layout === "image_left"
      ? "mkt-editorial mkt-editorial--image-left"
      : layout === "band"
        ? "mkt-editorial mkt-editorial--band"
        : "mkt-editorial mkt-editorial--image-right";
  const mediaClass = [
    "mkt-editorial-media",
    mediaStyle === "wide" ? "mkt-editorial-media--wide" : "",
    imageFit === "cover" ? "mkt-editorial-media--cover" : "mkt-editorial-media--contain",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={`mkt-section ${layoutClass}`}>
      <figure className={mediaClass}>
        <img src={imageSrc} alt={imageAlt} loading="lazy" decoding="async" />
      </figure>
      <div className="mkt-editorial-copy">
        {content.eyebrow ? <p className="mkt-eyebrow">{String(content.eyebrow)}</p> : null}
        {content.headline ? <h2 className="mkt-section-title">{String(content.headline)}</h2> : null}
        {content.body ? <p className="mkt-prose">{String(content.body)}</p> : null}
        {Boolean(content.primary_label || content.secondary_label) ? (
          <div className="mkt-hero-actions">
            <CmsLink
              label={String(content.primary_label || "")}
              kind={String(content.primary_kind || "internal")}
              value={String(content.primary_value || "")}
              className="mkt-btn mkt-btn-primary"
            />
            <CmsLink
              label={String(content.secondary_label || "")}
              kind={String(content.secondary_kind || "internal")}
              value={String(content.secondary_value || "")}
              className="mkt-btn mkt-btn-ghost"
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}

function ContactStripSection({ content }: { content: Record<string, unknown> }) {
  return (
    <section className="mkt-section mkt-contact" aria-label="Contact">
      <div className="mkt-contact-panel">
        <div className="mkt-contact-intro">
          <p className="mkt-eyebrow">Talk to us</p>
          <h2 className="mkt-section-title">We are here in Nairobi</h2>
        </div>
        <div className="mkt-contact-items">
          {content.location ? (
            <div className="mkt-contact-item">
              <span className="mkt-contact-label">Location</span>
              <span className="mkt-contact-value">{String(content.location)}</span>
            </div>
          ) : null}
          {content.email ? (
            <div className="mkt-contact-item">
              <span className="mkt-contact-label">Email</span>
              <a className="mkt-contact-value" href={`mailto:${content.email}`}>
                {String(content.email)}
              </a>
            </div>
          ) : null}
          {content.phone ? (
            <div className="mkt-contact-item">
              <span className="mkt-contact-label">Phone</span>
              <a
                className="mkt-contact-value"
                href={`tel:${String(content.phone).replace(/\s/g, "")}`}
              >
                {String(content.phone)}
              </a>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export function SectionRenderer({ section }: { section: WebsiteSection }) {
  const content = section.content || {};
  switch (section.type) {
    case "hero":
      return <HeroSection content={content} />;
    case "service_grid":
      return <ServiceGridSection content={content} />;
    case "statistics":
      return <StatisticsSection content={content} />;
    case "promo_carousel":
      return (
        <PromoCarousel
          slides={(content.slides as PromoSlide[]) || []}
          autoplay={content.autoplay !== false}
          intervalMs={Number(content.interval_ms || 5500)}
        />
      );
    case "partner_showcase":
      return (
        <PartnerShowcase
          eyebrow={content.eyebrow ? String(content.eyebrow) : undefined}
          headline={content.headline ? String(content.headline) : undefined}
          partners={(content.partners as PartnerItem[]) || []}
        />
      );
    case "story_grid":
      return (
        <StoryGrid
          eyebrow={content.eyebrow ? String(content.eyebrow) : undefined}
          headline={content.headline ? String(content.headline) : undefined}
          description={content.description ? String(content.description) : undefined}
          posts={(content.posts as StoryPost[]) || []}
        />
      );
    case "benefits":
      return <BenefitsSection content={content} />;
    case "agent_promotion":
      return <AgentPromotionSection content={content} />;
    case "cta":
      return <CtaSection content={content} />;
    case "editorial":
      return <EditorialSection content={content} />;
    case "editorial_image":
      return <EditorialImageSection content={content} />;
    case "contact_strip":
      return <ContactStripSection content={content} />;
    default:
      return null;
  }
}
