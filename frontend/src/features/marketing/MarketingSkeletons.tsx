function Skel({ className = "" }: { className?: string }) {
  return <span className={`skeleton-block mkt-skel ${className}`.trim()} aria-hidden="true" />;
}

export function MarketingNavSkeleton() {
  return (
    <div className="mkt-nav mkt-nav--desktop mkt-nav-skel" aria-hidden="true">
      <Skel className="mkt-skel-nav-link" />
      <Skel className="mkt-skel-nav-link" />
      <Skel className="mkt-skel-nav-link" />
      <Skel className="mkt-skel-nav-btn" />
      <Skel className="mkt-skel-nav-btn mkt-skel-nav-btn--wide" />
    </div>
  );
}

function HeroSkeleton({ withMedia = true }: { withMedia?: boolean }) {
  return (
    <section className={`mkt-hero ${withMedia ? "mkt-hero--split" : "mkt-hero--text"}`} aria-hidden="true">
      <div className="mkt-hero-copy">
        <Skel className="mkt-skel-chip" />
        <Skel className="mkt-skel-title mkt-skel-title--xl" />
        <Skel className="mkt-skel-title mkt-skel-title--xl-short" />
        <Skel className="mkt-skel-line" />
        <Skel className="mkt-skel-line mkt-skel-line--mid" />
        <div className="mkt-hero-actions">
          <Skel className="mkt-skel-btn" />
          <Skel className="mkt-skel-btn mkt-skel-btn--ghost" />
        </div>
      </div>
      {withMedia ? <Skel className="mkt-skel-media mkt-hero-media" /> : null}
    </section>
  );
}

function StatsSkeleton() {
  return (
    <section className="mkt-section mkt-stats" aria-hidden="true">
      <div className="mkt-section-head mkt-stats-head">
        <Skel className="mkt-skel-chip" />
      </div>
      <div className="mkt-stats-grid">
        {Array.from({ length: 4 }, (_, i) => (
          <article key={i} className="mkt-stat">
            <Skel className="mkt-skel-title mkt-skel-stat-value" />
            <Skel className="mkt-skel-line mkt-skel-line--short" />
          </article>
        ))}
      </div>
    </section>
  );
}

function CarouselSkeleton() {
  return (
    <section className="mkt-section mkt-carousel" aria-hidden="true">
      <div className="mkt-skel-carousel-track">
        {Array.from({ length: 3 }, (_, i) => (
          <Skel key={i} className="mkt-skel-carousel-card" />
        ))}
      </div>
    </section>
  );
}

function ServicesSkeleton() {
  return (
    <section className="mkt-section mkt-services" aria-hidden="true">
      <div className="mkt-section-head mkt-services-head">
        <Skel className="mkt-skel-chip" />
        <Skel className="mkt-skel-title" />
        <Skel className="mkt-skel-line mkt-skel-line--mid" />
      </div>
      <div className="mkt-services-grid">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="mkt-service mkt-service--skel">
            <Skel className="mkt-skel-index" />
            <div className="mkt-service-body">
              <Skel className="mkt-skel-line mkt-skel-line--title" />
              <Skel className="mkt-skel-line mkt-skel-line--short" />
            </div>
            <Skel className="mkt-skel-line mkt-skel-line--cta" />
          </div>
        ))}
      </div>
    </section>
  );
}

function PartnersSkeleton() {
  return (
    <section className="mkt-section mkt-partners" aria-hidden="true">
      <div className="mkt-section-head mkt-partners-head">
        <Skel className="mkt-skel-chip" />
        <Skel className="mkt-skel-title" />
      </div>
      <div className="mkt-partners-grid">
        {Array.from({ length: 2 }, (_, i) => (
          <article key={i} className="mkt-partner mkt-skel-partner">
            <Skel className="mkt-skel-partner-logo" />
            <div className="mkt-skel-partner-copy">
              <Skel className="mkt-skel-line mkt-skel-line--title" />
              <Skel className="mkt-skel-line" />
              <Skel className="mkt-skel-line mkt-skel-line--mid" />
              <Skel className="mkt-skel-btn" />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function StoriesSkeleton() {
  return (
    <section className="mkt-section mkt-stories" aria-hidden="true">
      <div className="mkt-section-head mkt-stories-head">
        <Skel className="mkt-skel-chip" />
        <Skel className="mkt-skel-title" />
        <Skel className="mkt-skel-line mkt-skel-line--mid" />
      </div>
      <div className="mkt-stories-grid">
        {Array.from({ length: 5 }, (_, i) => (
          <article key={i} className="mkt-story mkt-skel-story">
            <Skel className="mkt-skel-story-media" />
            <div className="mkt-story-body">
              <Skel className="mkt-skel-line mkt-skel-line--title" />
              <Skel className="mkt-skel-line" />
              <Skel className="mkt-skel-line mkt-skel-line--short" />
              <Skel className="mkt-skel-line mkt-skel-line--cta" />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function EditorialSkeleton({ layout = "image_right" }: { layout?: "image_left" | "image_right" }) {
  return (
    <section
      className={`mkt-section mkt-editorial ${layout === "image_left" ? "mkt-editorial--image-left" : "mkt-editorial--image-right"}`}
      aria-hidden="true"
    >
      <div className="mkt-editorial-copy">
        <Skel className="mkt-skel-chip" />
        <Skel className="mkt-skel-title" />
        <Skel className="mkt-skel-line" />
        <Skel className="mkt-skel-line mkt-skel-line--mid" />
        <Skel className="mkt-skel-btn" />
      </div>
      <Skel className="mkt-skel-media mkt-editorial-media" />
    </section>
  );
}

function AgentsSkeleton() {
  return (
    <section className="mkt-section mkt-agents" aria-hidden="true">
      <div className="mkt-agents-panel">
        <div className="mkt-agents-copy">
          <Skel className="mkt-skel-chip" />
          <Skel className="mkt-skel-title" />
          <Skel className="mkt-skel-line" />
          <Skel className="mkt-skel-line mkt-skel-line--mid" />
          <div className="mkt-hero-actions mkt-agents-actions">
            <Skel className="mkt-skel-btn" />
            <Skel className="mkt-skel-btn mkt-skel-btn--ghost" />
          </div>
        </div>
        <ul className="mkt-agents-points">
          {Array.from({ length: 3 }, (_, i) => (
            <li key={i} className="mkt-agents-point">
              <Skel className="mkt-skel-index" />
              <Skel className="mkt-skel-line mkt-skel-line--title" />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function BenefitsSkeleton() {
  return (
    <section className="mkt-section mkt-benefits" aria-hidden="true">
      <div className="mkt-section-head mkt-benefits-head">
        <Skel className="mkt-skel-chip" />
        <Skel className="mkt-skel-title" />
      </div>
      <div className="mkt-benefits-grid">
        {Array.from({ length: 4 }, (_, i) => (
          <article key={i} className="mkt-benefit">
            <Skel className="mkt-skel-index" />
            <div className="mkt-benefit-body">
              <Skel className="mkt-skel-line mkt-skel-line--title" />
              <Skel className="mkt-skel-line" />
              <Skel className="mkt-skel-line mkt-skel-line--short" />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function CtaSkeleton() {
  return (
    <section className="mkt-section mkt-cta" aria-hidden="true">
      <div className="mkt-cta-panel">
        <div className="mkt-cta-copy">
          <Skel className="mkt-skel-chip" />
          <Skel className="mkt-skel-title" />
          <Skel className="mkt-skel-line mkt-skel-line--mid" />
        </div>
        <Skel className="mkt-skel-btn" />
      </div>
    </section>
  );
}

function ContactSkeleton() {
  return (
    <section className="mkt-section mkt-contact" aria-hidden="true">
      <div className="mkt-contact-panel">
        <div className="mkt-contact-intro">
          <Skel className="mkt-skel-chip" />
          <Skel className="mkt-skel-title" />
        </div>
        <div className="mkt-contact-items">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="mkt-contact-item">
              <Skel className="mkt-skel-line mkt-skel-line--short" />
              <Skel className="mkt-skel-line mkt-skel-line--title" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function MissionSkeleton() {
  return (
    <section className="mkt-section mkt-mission" aria-hidden="true">
      <div className="mkt-mission-panel">
        <div className="mkt-mission-copy">
          <Skel className="mkt-skel-chip" />
          <Skel className="mkt-skel-title" />
          <Skel className="mkt-skel-line" />
          <Skel className="mkt-skel-line" />
          <Skel className="mkt-skel-line mkt-skel-line--mid" />
        </div>
        <Skel className="mkt-skel-media mkt-mission-media" />
      </div>
    </section>
  );
}

export function MarketingHomeSkeleton() {
  return (
    <div className="mkt-skel-page" aria-busy="true" aria-live="polite">
      <span className="config-sr-only">Loading site content</span>
      <div className="mkt-hero-stage">
        <HeroSkeleton withMedia />
      </div>
      <main className="mkt-main">
        <StatsSkeleton />
        <CarouselSkeleton />
        <ServicesSkeleton />
        <PartnersSkeleton />
        <StoriesSkeleton />
        <EditorialSkeleton layout="image_right" />
        <AgentsSkeleton />
        <BenefitsSkeleton />
        <EditorialSkeleton layout="image_left" />
        <CtaSkeleton />
        <ContactSkeleton />
      </main>
    </div>
  );
}

export function MarketingInnerSkeleton({ variant = "default" }: { variant?: "about" | "services" | "default" }) {
  return (
    <main className="mkt-main mkt-skel-page" aria-busy="true" aria-live="polite">
      <span className="config-sr-only">Loading page content</span>
      <HeroSkeleton withMedia={false} />
      {variant === "about" ? <MissionSkeleton /> : null}
      {variant === "services" ? <ServicesSkeleton /> : null}
      {variant === "default" ? (
        <>
          <CtaSkeleton />
          <ContactSkeleton />
        </>
      ) : null}
    </main>
  );
}
