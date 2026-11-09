import { Link } from "react-router-dom";
import { publicAsset } from "@/app/router/basePath";
import { isExternalMarketingLink, resolveMarketingLink } from "@/features/marketing/resolveLink";

export type StoryPost = {
  id?: string;
  title?: string;
  summary?: string;
  image_src?: string;
  image_alt?: string;
  cta_label?: string;
  cta_kind?: string;
  cta_value?: string;
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

function StoryCta({ label, kind, value }: { label: string; kind: string; value: string }) {
  if (!label) return null;
  const href = resolveMarketingLink(kind || "quote", value || "");
  const external = isExternalMarketingLink(kind || "quote");
  if (external) {
    return (
      <a className="mkt-link" href={href} rel="noopener noreferrer">
        {label}
      </a>
    );
  }
  return (
    <Link className="mkt-link" to={href}>
      {label}
    </Link>
  );
}

type StoryGridProps = {
  eyebrow?: string;
  headline?: string;
  description?: string;
  posts: StoryPost[];
};

export function StoryGrid({ eyebrow, headline, description, posts }: StoryGridProps) {
  const items = posts.filter(
    (post) => post.enabled !== false && post.image_src && post.title,
  );
  if (items.length === 0) return null;

  return (
    <section className="mkt-section mkt-stories">
      <div className="mkt-section-head mkt-stories-head">
        <p className="mkt-eyebrow">{eyebrow || "From our desk"}</p>
        {headline ? <h2 className="mkt-section-title">{headline}</h2> : null}
        {description ? <p className="mkt-muted">{description}</p> : null}
      </div>
      <div className="mkt-stories-grid">
        {items.map((post, index) => {
          const imageSrc = resolveMedia(String(post.image_src || ""));
          return (
            <article key={post.id || post.title} className="mkt-story">
              <figure className="mkt-story-media">
                <img
                  src={imageSrc}
                  alt={String(post.image_alt || post.title)}
                  loading={index < 2 ? "eager" : "lazy"}
                  decoding="async"
                />
              </figure>
              <div className="mkt-story-body">
                <h3 className="mkt-story-title">{post.title}</h3>
                {post.summary ? <p className="mkt-story-summary">{post.summary}</p> : null}
                <div className="mkt-story-cta">
                  <StoryCta
                    label={String(post.cta_label || "Get Instant Cover")}
                    kind={String(post.cta_kind || "quote")}
                    value={String(post.cta_value || "")}
                  />
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
