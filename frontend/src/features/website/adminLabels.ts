export const PAGE_LABELS: Record<string, string> = {
  home: "Home",
  services: "Services",
  about: "About",
  "get-covered": "Get covered",
};

export const SECTION_TYPE_LABELS: Record<string, string> = {
  hero: "Hero banner",
  service_grid: "Services list",
  statistics: "Key numbers",
  promo_carousel: "Promo banners",
  partner_showcase: "Partners",
  story_grid: "Campaign stories",
  benefits: "Benefits",
  agent_promotion: "Become an agent",
  cta: "Call to action",
  editorial: "Story / mission",
  editorial_image: "Photo + story",
  contact_strip: "Contact details",
  faq: "FAQ",
};

export const SECTION_HELP: Record<string, string> = {
  hero: "The large opening message visitors see first on this page.",
  service_grid: "The insurance products shown as cards.",
  statistics: "Short proof points under the hero. Uncheck Verified to hide a number.",
  promo_carousel: "Sliding promo images after the stats strip.",
  partner_showcase: "Partner logos, short descriptions, and action buttons.",
  story_grid: "Campaign photos and short stories that give the site life.",
  benefits: "Reasons customers choose Star Serve.",
  agent_promotion: "Invite people to sell with Star Serve.",
  cta: "A final push to start a quote or contact the team.",
  editorial: "Longer text block without a photo.",
  editorial_image: "A photo beside a short story and button.",
  contact_strip: "Office location, email, and phone shown near the footer.",
  faq: "Common questions and answers.",
};

export const SECTION_KEY_LABELS: Record<string, string> = {
  hero: "Opening banner",
  statistics: "By the numbers",
  promos: "Promo banners",
  categories: "Cover categories",
  partners: "Partners",
  stories: "From our desk",
  people: "People first",
  agents: "Agent invitation",
  benefits: "Why Star Serve",
  office: "In Nairobi",
  cta: "Get covered",
  contact: "Contact strip",
  story: "Our mission",
};

export const LINK_KIND_OPTIONS = [
  { value: "quote", label: "Quote portal" },
  { value: "quote_product", label: "Quote a product" },
  { value: "internal", label: "Page on this website" },
  { value: "external", label: "External website" },
  { value: "agent_register", label: "Agent signup" },
  { value: "agent_login", label: "Agent login" },
  { value: "phone", label: "Phone number" },
  { value: "email", label: "Email address" },
] as const;

export function pageLabel(slug: string): string {
  return PAGE_LABELS[slug] || slug;
}

export function sectionTitle(sectionKey: string, sectionType: string): string {
  return SECTION_KEY_LABELS[sectionKey] || SECTION_TYPE_LABELS[sectionType] || sectionKey;
}

export function sectionHelp(sectionType: string): string {
  return SECTION_HELP[sectionType] || "Edit the wording and images for this part of the website.";
}

export function sectionTypeLabel(sectionType: string): string {
  return SECTION_TYPE_LABELS[sectionType] || sectionType.replaceAll("_", " ");
}
