import { apiRequest } from "@/services/api/client";

export type WebsiteNavLink = {
  label: string;
  kind: string;
  value: string;
};

export type WebsiteSection = {
  key: string;
  type: string;
  variant?: string | null;
  content: Record<string, unknown>;
};

export type WebsiteBootstrap = {
  content_version: number;
  settings: {
    location?: string;
    email?: string;
    phone?: string;
  };
  navigation: {
    header?: WebsiteNavLink[];
    footer?: WebsiteNavLink[];
  };
  homepage: {
    sections: WebsiteSection[];
  };
};

export type WebsitePagePayload = {
  slug: string;
  title: string;
  meta_title?: string | null;
  meta_description?: string | null;
  sections: WebsiteSection[];
  content_version: number;
};

export type WebsiteSectionAdmin = {
  id: string;
  page_slug: string;
  section_key: string;
  section_type: string;
  sort_order: number;
  enabled: boolean;
  draft_content: Record<string, unknown>;
  published_content: Record<string, unknown> | null;
};

export const websiteApi = {
  bootstrap() {
    return apiRequest<WebsiteBootstrap>("/website/bootstrap");
  },
  page(slug: string) {
    return apiRequest<WebsitePagePayload>(`/website/pages/${encodeURIComponent(slug)}`);
  },
  submitEnquiry(body: {
    full_name: string;
    phone: string;
    email?: string;
    cover_needed?: string;
    message?: string;
  }) {
    return apiRequest<{ id: string }>("/website/enquiries", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  adminOverview() {
    return apiRequest<{
      content_version: number;
      pages_total: number;
      pages_published: number;
      sections_total: number;
      sections_with_draft_changes: number;
    }>("/website/admin/overview");
  },
  adminSections(pageSlug?: string) {
    const q = pageSlug ? `?page_slug=${encodeURIComponent(pageSlug)}` : "";
    return apiRequest<{ items: WebsiteSectionAdmin[] }>(`/website/admin/sections${q}`);
  },
  updateSection(sectionId: string, content: Record<string, unknown>, enabled?: boolean) {
    return apiRequest<{ id: string; section_key: string }>(`/website/admin/sections/${sectionId}`, {
      method: "PATCH",
      body: JSON.stringify({ content, enabled }),
    });
  },
  uploadMedia(file: File) {
    const body = new FormData();
    body.append("file", file);
    return apiRequest<{ path: string; content_type: string; size_bytes: number }>(
      "/website/admin/media",
      { method: "POST", body },
    );
  },
  publish() {
    return apiRequest<{ content_version: number }>("/website/admin/publish", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },
};
