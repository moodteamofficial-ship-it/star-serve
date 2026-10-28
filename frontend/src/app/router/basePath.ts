/** Vite `base` → React Router basename (no trailing slash, `/` for root). */
export function appBasename(): string {
  const raw = String(import.meta.env.BASE_URL || "/").trim() || "/";
  if (raw === "/") return "/";
  return raw.replace(/\/+$/, "") || "/";
}

/** Public file under Vite `base` (e.g. `/dashboard/star-serve-logo.png`). */
export function publicAsset(path: string): string {
  const base = String(import.meta.env.BASE_URL || "/").trim() || "/";
  const normalized = path.replace(/^\/+/, "");
  if (base === "/") return `/${normalized}`;
  return `${base.replace(/\/+$/, "")}/${normalized}`;
}
