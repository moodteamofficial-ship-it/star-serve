import { useEffect, useMemo, useRef, useState } from "react";
import { publicAsset } from "@/app/router/basePath";
import { isExternalMarketingLink, resolveMarketingLink } from "@/features/marketing/resolveLink";

export type PromoSlide = {
  id?: string;
  image_src?: string;
  image_alt?: string;
  href?: string;
  href_kind?: string;
  enabled?: boolean;
};

function resolveImage(src: string): string {
  const value = src.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value) || value.startsWith("data:") || value.startsWith("/api/")) {
    return value;
  }
  return publicAsset(value.replace(/^\/+/, ""));
}

type PromoCarouselProps = {
  slides: PromoSlide[];
  autoplay?: boolean;
  intervalMs?: number;
};

export function PromoCarousel({
  slides,
  autoplay = true,
  intervalMs = 5500,
}: PromoCarouselProps) {
  const items = useMemo(
    () => slides.filter((slide) => Boolean(slide.image_src) && slide.enabled !== false),
    [slides],
  );
  const scrollerRef = useRef<HTMLDivElement>(null);
  const indexRef = useRef(0);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  function scrollToIndex(nextIndex: number, behavior: ScrollBehavior = "smooth") {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const cards = scroller.querySelectorAll<HTMLElement>("[data-promo-card]");
    const target = cards[nextIndex];
    if (!target) return;
    const left = target.offsetLeft - (scroller.clientWidth - target.clientWidth) / 2;
    scroller.scrollTo({ left: Math.max(0, left), behavior });
    indexRef.current = nextIndex;
    setIndex(nextIndex);
  }

  useEffect(() => {
    scrollToIndex(0, "auto");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length]);

  useEffect(() => {
    if (!autoplay || paused || items.length < 2) return;
    const timer = window.setInterval(() => {
      const next = (indexRef.current + 1) % items.length;
      scrollToIndex(next);
    }, Math.max(3200, intervalMs));
    return () => window.clearInterval(timer);
  }, [autoplay, paused, items.length, intervalMs]);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const onScroll = () => {
      const cards = [...scroller.querySelectorAll<HTMLElement>("[data-promo-card]")];
      if (cards.length === 0) return;
      const center = scroller.scrollLeft + scroller.clientWidth / 2;
      let closest = 0;
      let closestDistance = Number.POSITIVE_INFINITY;
      cards.forEach((card, cardIndex) => {
        const cardCenter = card.offsetLeft + card.clientWidth / 2;
        const distance = Math.abs(cardCenter - center);
        if (distance < closestDistance) {
          closestDistance = distance;
          closest = cardIndex;
        }
      });
      setIndex(closest);
    };

    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, [items.length]);

  if (items.length === 0) return null;

  return (
    <section
      className="mkt-section mkt-promo"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-roledescription="carousel"
      aria-label="Featured promotions"
    >
      <div className="mkt-promo-shell">
        <div className="mkt-promo-scroller" ref={scrollerRef}>
          {items.map((slide, slideIndex) => {
            const href = resolveMarketingLink(slide.href_kind || "external", slide.href || "");
            const external = isExternalMarketingLink(slide.href_kind || "external");
            const imageSrc = resolveImage(String(slide.image_src || ""));
            const media = (
              <img
                src={imageSrc}
                alt={String(slide.image_alt || "Star Serve promotion")}
                loading={slideIndex === 0 ? "eager" : "lazy"}
                decoding="async"
                draggable={false}
              />
            );

            if (href && href !== "/") {
              return external ? (
                <a
                  key={slide.id || slide.image_src || slideIndex}
                  className="mkt-promo-card"
                  data-promo-card
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {media}
                </a>
              ) : (
                <a
                  key={slide.id || slide.image_src || slideIndex}
                  className="mkt-promo-card"
                  data-promo-card
                  href={href}
                >
                  {media}
                </a>
              );
            }

            return (
              <div
                key={slide.id || slide.image_src || slideIndex}
                className="mkt-promo-card"
                data-promo-card
              >
                {media}
              </div>
            );
          })}
        </div>

        {items.length > 1 ? (
          <>
            <button
              type="button"
              className="mkt-promo-nav mkt-promo-nav--prev"
              aria-label="Previous promotion"
              onClick={() => scrollToIndex((index - 1 + items.length) % items.length)}
            >
              <span className="mkt-promo-nav-icon" aria-hidden="true">
                ‹
              </span>
            </button>
            <button
              type="button"
              className="mkt-promo-nav mkt-promo-nav--next"
              aria-label="Next promotion"
              onClick={() => scrollToIndex((index + 1) % items.length)}
            >
              <span className="mkt-promo-nav-icon" aria-hidden="true">
                ›
              </span>
            </button>
            <div className="mkt-promo-dots" role="tablist" aria-label="Promotion slides">
              {items.map((slide, slideIndex) => (
                <button
                  key={slide.id || slide.image_src || slideIndex}
                  type="button"
                  role="tab"
                  aria-selected={slideIndex === index}
                  className={slideIndex === index ? "mkt-promo-dot is-active" : "mkt-promo-dot"}
                  onClick={() => scrollToIndex(slideIndex)}
                  aria-label={`Show promotion ${slideIndex + 1}`}
                />
              ))}
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
