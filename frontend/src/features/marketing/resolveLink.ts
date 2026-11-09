const QUOTE_BASE =
  import.meta.env.VITE_WEB_URL_PRODUCTION?.replace(/\/$/, "") ||
  "https://quote.starserveinsuranceagency.com/dashboard";

const PRODUCT_PATHS: Record<string, string> = {
  "motor-insurance": "/?product=motor",
  "medical-cover": "/?product=medical",
  "last-expense": "/?product=last-expense",
  "personal-accident": "/?product=personal-accident",
};

export function resolveMarketingLink(kind: string, value: string): string {
  const k = (kind || "").trim().toLowerCase();
  const raw = (value || "").trim();
  if (k === "internal") return raw.startsWith("/") ? raw : `/${raw}`;
  if (k === "quote") return raw || `${QUOTE_BASE}/`;
  if (k === "quote_product") {
    const slug = raw.replace(/^\/+/, "");
    return `${QUOTE_BASE}${PRODUCT_PATHS[slug] ?? "/"}`;
  }
  if (k === "agent_register") return raw || `${QUOTE_BASE}/register-agent`;
  if (k === "agent_login") return raw || `${QUOTE_BASE}/login`;
  if (k === "phone") {
    const digits = raw.replace(/[^\d+]/g, "");
    return digits ? `tel:${digits}` : raw;
  }
  if (k === "email") return raw.includes("@") ? `mailto:${raw}` : raw;
  if (k === "external") return raw;
  return raw;
}

export function isExternalMarketingLink(kind: string): boolean {
  const k = (kind || "").trim().toLowerCase();
  return (
    k === "quote" ||
    k === "quote_product" ||
    k === "agent_register" ||
    k === "agent_login" ||
    k === "external"
  );
}
