import { useState } from "react";
import { publicAsset } from "@/app/router/basePath";
import { websiteApi } from "@/services/website/websiteApi";
import { SelectInput } from "@/features/website/AdminFormFields";

const DEST_OPTIONS = [
  { value: "quote", label: "Quote portal" },
  { value: "quote_product", label: "Quote a product" },
  { value: "internal", label: "Page on this website" },
  { value: "external", label: "External website" },
];

export type StoryPostDraft = {
  id: string;
  title: string;
  summary: string;
  image_src: string;
  image_alt: string;
  cta_label: string;
  cta_kind: string;
  cta_value: string;
  enabled: boolean;
};

export type StoriesSectionDraft = {
  eyebrow: string;
  headline: string;
  description: string;
  posts: StoryPostDraft[];
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `story-${Date.now()}`;
}

function previewSrc(src: string): string {
  const value = src.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value) || value.startsWith("/api/")) return value;
  return publicAsset(value.replace(/^\/+/, ""));
}

export function parseStoriesDraft(raw: Record<string, unknown>): StoriesSectionDraft {
  const postsRaw = Array.isArray(raw.posts) ? raw.posts : [];
  return {
    eyebrow: String(raw.eyebrow || "From our desk"),
    headline: String(raw.headline || "Cover built for real Kenyan hustles"),
    description: String(raw.description || ""),
    posts: postsRaw.map((item, index) => {
      const post = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
      return {
        id: String(post.id || `story-${index + 1}`),
        title: String(post.title || ""),
        summary: String(post.summary || ""),
        image_src: String(post.image_src || ""),
        image_alt: String(post.image_alt || ""),
        cta_label: String(post.cta_label || "Get Instant Cover"),
        cta_kind: String(post.cta_kind || "quote"),
        cta_value: String(post.cta_value || ""),
        enabled: post.enabled !== false,
      };
    }),
  };
}

type StoriesAdminEditorProps = {
  value: StoriesSectionDraft;
  onChange: (next: StoriesSectionDraft) => void;
};

export function StoriesAdminEditor({ value, onChange }: StoriesAdminEditorProps) {
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updatePost(id: string, patch: Partial<StoryPostDraft>) {
    onChange({
      ...value,
      posts: value.posts.map((post) => (post.id === id ? { ...post, ...patch } : post)),
    });
  }

  function movePost(id: string, direction: -1 | 1) {
    const index = value.posts.findIndex((post) => post.id === id);
    if (index < 0) return;
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= value.posts.length) return;
    const posts = [...value.posts];
    const [item] = posts.splice(index, 1);
    posts.splice(nextIndex, 0, item!);
    onChange({ ...value, posts });
  }

  function removePost(id: string) {
    onChange({ ...value, posts: value.posts.filter((post) => post.id !== id) });
  }

  function addPost() {
    onChange({
      ...value,
      posts: [
        ...value.posts,
        {
          id: newId(),
          title: "",
          summary: "",
          image_src: "",
          image_alt: "",
          cta_label: "Get Instant Cover",
          cta_kind: "quote",
          cta_value: "",
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
      updatePost(id, { image_src: res.data.path });
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
      <label>
        Short introduction
        <textarea
          value={value.description}
          onChange={(e) => onChange({ ...value, description: e.target.value })}
          rows={3}
        />
      </label>
      <div className="website-carousel-toolbar">
        <button type="button" className="website-btn website-btn--ghost" onClick={addPost}>
          Add story
        </button>
      </div>
      {error ? <p className="website-admin-banner">{error}</p> : null}
      <div className="website-carousel-slides">
        {value.posts.map((post, index) => (
          <article key={post.id} className="website-carousel-slide">
            <header>
              <strong>Post {index + 1}</strong>
              <div className="website-carousel-slide-actions">
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => movePost(post.id, -1)}
                  disabled={index === 0}
                >
                  Up
                </button>
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => movePost(post.id, 1)}
                  disabled={index === value.posts.length - 1}
                >
                  Down
                </button>
                <button
                  type="button"
                  className="website-btn website-btn--ghost"
                  onClick={() => removePost(post.id)}
                >
                  Remove
                </button>
              </div>
            </header>
            {post.image_src ? (
              <img className="website-carousel-preview" src={previewSrc(post.image_src)} alt="" />
            ) : (
              <div className="website-carousel-preview is-empty">No image yet</div>
            )}
            <label>
              Image upload
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                disabled={uploadingId === post.id}
                onChange={(e) => void onUpload(post.id, e.target.files?.[0] ?? null)}
              />
            </label>
            <label>
              Image URL
              <input
                value={post.image_src}
                onChange={(e) => updatePost(post.id, { image_src: e.target.value })}
              />
            </label>
            <label>
              Alt text
              <input
                value={post.image_alt}
                onChange={(e) => updatePost(post.id, { image_alt: e.target.value })}
              />
            </label>
            <label>
              Title
              <input
                value={post.title}
                onChange={(e) => updatePost(post.id, { title: e.target.value })}
              />
            </label>
            <label>
              Summary
              <textarea
                value={post.summary}
                onChange={(e) => updatePost(post.id, { summary: e.target.value })}
                rows={3}
              />
            </label>
            <label>
              Button label
              <input
                value={post.cta_label}
                onChange={(e) => updatePost(post.id, { cta_label: e.target.value })}
              />
            </label>
            <label>
              Button link
              <input
                value={post.cta_value}
                onChange={(e) => updatePost(post.id, { cta_value: e.target.value })}
              />
            </label>
            <label>
              Destination type
              <SelectInput
                value={post.cta_kind}
                onChange={(cta_kind) => updatePost(post.id, { cta_kind })}
                options={DEST_OPTIONS}
                ariaLabel="Destination type"
              />
            </label>
            <label className="website-carousel-check">
              <input
                type="checkbox"
                checked={post.enabled}
                onChange={(e) => updatePost(post.id, { enabled: e.target.checked })}
              />
              Show this story
            </label>
          </article>
        ))}
      </div>
    </div>
  );
}
