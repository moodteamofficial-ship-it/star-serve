import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/services/api/client";
import { websiteApi, type WebsiteSectionAdmin } from "@/services/website/websiteApi";
import {
  CarouselAdminEditor,
  parseCarouselDraft,
  type CarouselDraft,
} from "@/features/website/CarouselAdminEditor";
import {
  PartnersAdminEditor,
  parsePartnersDraft,
  type PartnersSectionDraft,
} from "@/features/website/PartnersAdminEditor";
import {
  StoriesAdminEditor,
  parseStoriesDraft,
  type StoriesSectionDraft,
} from "@/features/website/StoriesAdminEditor";
import { SectionFormEditor, supportsGuidedForm } from "@/features/website/SectionFormEditor";
import { Toggle } from "@/features/website/AdminFormFields";
import {
  pageLabel,
  sectionHelp,
  sectionTitle,
  sectionTypeLabel,
} from "@/features/website/adminLabels";
import { marketingPublicSiteUrl } from "@/features/marketing/useMarketingPwa";
import {
  WebsiteAdminEditorSkeleton,
  WebsiteAdminListSkeleton,
  WebsiteAdminStatsSkeleton,
} from "@/features/website/WebsiteAdminSkeletons";
import "./website-admin.css";

const PAGE_TABS = [
  { value: "home", label: "Home" },
  { value: "services", label: "Services" },
  { value: "about", label: "About" },
  { value: "get-covered", label: "Get covered" },
] as const;

function stableJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {});
  } catch {
    return "";
  }
}

function hasPendingDraft(section: WebsiteSectionAdmin): boolean {
  return stableJson(section.draft_content) !== stableJson(section.published_content ?? {});
}

function livePreviewUrl(pageSlug: string): string {
  const base = marketingPublicSiteUrl().replace(/\/$/, "");
  if (pageSlug === "home") return `${base}/`;
  return `${base}/${pageSlug}`;
}

export function WebsiteAdminPage() {
  const queryClient = useQueryClient();
  const [pageFilter, setPageFilter] = useState("home");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formDraft, setFormDraft] = useState<Record<string, unknown> | null>(null);
  const [carouselDraft, setCarouselDraft] = useState<CarouselDraft | null>(null);
  const [partnersDraft, setPartnersDraft] = useState<PartnersSectionDraft | null>(null);
  const [storiesDraft, setStoriesDraft] = useState<StoriesSectionDraft | null>(null);
  const [sectionEnabled, setSectionEnabled] = useState(true);
  const [baseline, setBaseline] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [messageTone, setMessageTone] = useState<"ok" | "error">("ok");

  const overviewQuery = useQuery({
    queryKey: ["website-admin", "overview"],
    queryFn: async () => (await websiteApi.adminOverview()).data,
  });

  const sectionsQuery = useQuery({
    queryKey: ["website-admin", "sections", pageFilter],
    queryFn: async () =>
      (await websiteApi.adminSections(pageFilter || undefined)).data.items,
  });

  const sections = useMemo(() => {
    const items = [...(sectionsQuery.data ?? [])];
    items.sort((a, b) => a.sort_order - b.sort_order);
    return items;
  }, [sectionsQuery.data]);

  const selected: WebsiteSectionAdmin | undefined = useMemo(
    () => sections.find((s) => s.id === selectedId),
    [sections, selectedId],
  );

  function loadSectionDraft(section: WebsiteSectionAdmin) {
    setSelectedId(section.id);
    setSectionEnabled(section.enabled);
    setMessage(null);
    const draft = section.draft_content ?? {};
    if (section.section_type === "promo_carousel") {
      const parsed = parseCarouselDraft(draft);
      setCarouselDraft(parsed);
      setPartnersDraft(null);
      setStoriesDraft(null);
      setFormDraft(null);
      setBaseline(stableJson(parsed));
      return;
    }
    if (section.section_type === "partner_showcase") {
      const parsed = parsePartnersDraft(draft);
      setPartnersDraft(parsed);
      setCarouselDraft(null);
      setStoriesDraft(null);
      setFormDraft(null);
      setBaseline(stableJson(parsed));
      return;
    }
    if (section.section_type === "story_grid") {
      const parsed = parseStoriesDraft(draft);
      setStoriesDraft(parsed);
      setCarouselDraft(null);
      setPartnersDraft(null);
      setFormDraft(null);
      setBaseline(stableJson(parsed));
      return;
    }
    const parsed = { ...draft };
    setFormDraft(parsed);
    setCarouselDraft(null);
    setPartnersDraft(null);
    setStoriesDraft(null);
    setBaseline(stableJson(parsed));
  }

  useEffect(() => {
    setSelectedId(null);
    setFormDraft(null);
    setCarouselDraft(null);
    setPartnersDraft(null);
    setStoriesDraft(null);
    setBaseline("");
    setMessage(null);
  }, [pageFilter]);

  useEffect(() => {
    if (!sections.length) return;
    if (sections.some((section) => section.page_slug !== pageFilter)) return;
    if (selectedId && sections.some((section) => section.id === selectedId)) return;
    loadSectionDraft(sections[0]!);
  }, [sections, selectedId, pageFilter]);

  const isCarousel = selected?.section_type === "promo_carousel";
  const isPartners = selected?.section_type === "partner_showcase";
  const isStories = selected?.section_type === "story_grid";
  const isGuided = selected ? supportsGuidedForm(selected.section_type) : false;

  const currentContent = useMemo(() => {
    if (!selected) return null;
    if (isCarousel) return carouselDraft;
    if (isPartners) return partnersDraft;
    if (isStories) return storiesDraft;
    return formDraft;
  }, [
    selected,
    isCarousel,
    isPartners,
    isStories,
    carouselDraft,
    partnersDraft,
    storiesDraft,
    formDraft,
  ]);

  const isDirty =
    !!selected &&
    (sectionEnabled !== selected.enabled || stableJson(currentContent) !== baseline);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!selected || !currentContent) throw new Error("No section selected");
      return websiteApi.updateSection(
        selected.id,
        currentContent as unknown as Record<string, unknown>,
        sectionEnabled,
      );
    },
    onSuccess: async () => {
      setMessageTone("ok");
      setMessage("Draft saved. Publish when you are ready for the live website to update.");
      setBaseline(stableJson(currentContent));
      await queryClient.invalidateQueries({ queryKey: ["website-admin"] });
    },
    onError: (err) => {
      setMessageTone("error");
      setMessage(err instanceof ApiError ? err.message : "Save failed");
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => websiteApi.publish(),
    onSuccess: async (res) => {
      setMessageTone("ok");
      setMessage(`Published to the live website — version ${res.data.content_version}.`);
      await queryClient.invalidateQueries({ queryKey: ["website-admin"] });
      await queryClient.invalidateQueries({ queryKey: ["website"] });
    },
    onError: (err) => {
      setMessageTone("error");
      setMessage(err instanceof ApiError ? err.message : "Publish failed");
    },
  });

  const overview = overviewQuery.data;
  const pendingCount = overview?.sections_with_draft_changes ?? 0;
  const sectionsLoading = sectionsQuery.isLoading || (sectionsQuery.isFetching && sections.length === 0);
  const editorLoading = sectionsLoading || (!!selectedId && currentContent === null && sectionsQuery.isFetching);

  return (
    <div className="website-admin">
      <header className="website-admin-header">
        <div>
          <p className="website-admin-kicker">Website content</p>
          <h1>Edit your public website</h1>
          <p className="website-admin-muted">
            Change wording and images here, save a draft, then publish when everything looks right.
          </p>
        </div>
        <div className="website-admin-header-actions">
          <a
            className="website-btn website-btn--ghost"
            href={livePreviewUrl(pageFilter)}
            target="_blank"
            rel="noreferrer"
          >
            Open live website
          </a>
          <button
            type="button"
            className="website-btn website-btn--primary"
            disabled={publishMutation.isPending || pendingCount === 0}
            onClick={() => publishMutation.mutate()}
          >
            {publishMutation.isPending ? "Publishing…" : "Publish to live site"}
          </button>
        </div>
      </header>

      <ol className="website-admin-steps">
        <li>
          <strong>1.</strong> Choose a page
        </li>
        <li>
          <strong>2.</strong> Pick a section
        </li>
        <li>
          <strong>3.</strong> Edit and save draft
        </li>
        <li>
          <strong>4.</strong> Publish when ready
        </li>
      </ol>

      {overviewQuery.isLoading ? (
        <WebsiteAdminStatsSkeleton />
      ) : overview ? (
        <div className="website-admin-stats">
          <div>
            <span className="website-stat-label">Live version</span>
            <strong>{overview.content_version}</strong>
          </div>
          <div>
            <span className="website-stat-label">Pages live</span>
            <strong>
              {overview.pages_published}/{overview.pages_total}
            </strong>
          </div>
          <div>
            <span className="website-stat-label">Drafts waiting to publish</span>
            <strong>{pendingCount}</strong>
          </div>
        </div>
      ) : null}

      {message ? (
        <p className={messageTone === "error" ? "website-admin-banner is-error" : "website-admin-banner is-ok"}>
          {message}
        </p>
      ) : null}

      <div className="website-admin-tabs" role="tablist" aria-label="Website pages">
        {PAGE_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={pageFilter === tab.value}
            className={pageFilter === tab.value ? "website-admin-tab is-active" : "website-admin-tab"}
            onClick={() => setPageFilter(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="website-admin-grid">
        <aside className="website-admin-sidebar">
          <div className="website-admin-sidebar-head">
            <h2>{pageLabel(pageFilter)} page</h2>
            <p>Sections in live page order</p>
          </div>
          {sectionsLoading ? (
            <WebsiteAdminListSkeleton rows={pageFilter === "home" ? 12 : 4} />
          ) : (
            <ul className="website-admin-list">
              {sections.map((section, index) => {
                const pending = hasPendingDraft(section);
                return (
                  <li key={section.id}>
                    <button
                      type="button"
                      className={
                        section.id === selectedId
                          ? "website-admin-list-item is-active"
                          : "website-admin-list-item"
                      }
                      onClick={() => loadSectionDraft(section)}
                    >
                      <span className="website-admin-list-index" aria-hidden="true">
                        {index + 1}
                      </span>
                      <span className="website-admin-list-copy">
                        <span className="website-admin-list-title">
                          {sectionTitle(section.section_key, section.section_type)}
                        </span>
                        {pending ? (
                          <span className="website-admin-list-note">Unpublished edits</span>
                        ) : null}
                      </span>
                      <span
                        className={
                          section.enabled
                            ? "website-badge is-live"
                            : "website-badge is-hidden"
                        }
                      >
                        {section.enabled ? "On" : "Off"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        <div className="website-admin-editor">
          {editorLoading ? (
            <WebsiteAdminEditorSkeleton />
          ) : selected && currentContent !== null ? (
            <>
              <div className="website-admin-editor-head">
                <div className="website-admin-editor-title">
                  <p className="website-admin-kicker">
                    {pageLabel(selected.page_slug)} · {sectionTypeLabel(selected.section_type)}
                  </p>
                  <h2>{sectionTitle(selected.section_key, selected.section_type)}</h2>
                  <p className="website-admin-muted">{sectionHelp(selected.section_type)}</p>
                </div>
                <div className="website-admin-editor-visibility">
                  <span className="website-admin-editor-visibility-label">On website</span>
                  <Toggle
                    checked={sectionEnabled}
                    onChange={setSectionEnabled}
                    label={sectionEnabled ? "Visible" : "Hidden"}
                  />
                </div>
              </div>

              {isCarousel && carouselDraft ? (
                <CarouselAdminEditor value={carouselDraft} onChange={setCarouselDraft} />
              ) : null}
              {isPartners && partnersDraft ? (
                <PartnersAdminEditor value={partnersDraft} onChange={setPartnersDraft} />
              ) : null}
              {isStories && storiesDraft ? (
                <StoriesAdminEditor value={storiesDraft} onChange={setStoriesDraft} />
              ) : null}
              {isGuided && formDraft ? (
                <SectionFormEditor
                  sectionType={selected.section_type}
                  value={formDraft}
                  onChange={setFormDraft}
                />
              ) : null}
              {!isCarousel && !isPartners && !isStories && !isGuided ? (
                <SectionFormEditor
                  sectionType={selected.section_type}
                  value={formDraft ?? {}}
                  onChange={setFormDraft}
                />
              ) : null}

              <div className="website-admin-editor-footer">
                <p className="website-admin-muted">
                  {isDirty ? "Unsaved changes" : "Draft up to date"}
                </p>
                <button
                  type="button"
                  className="website-btn website-btn--primary"
                  disabled={saveMutation.isPending || !isDirty}
                  onClick={() => saveMutation.mutate()}
                >
                  {saveMutation.isPending ? "Saving…" : "Save draft"}
                </button>
              </div>
            </>
          ) : (
            <div className="website-admin-empty">
              <h2>Select a section</h2>
              <p className="website-admin-muted">
                Choose a page tab, then pick a section on the left to start editing.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
