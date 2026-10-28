/** Resolve same-origin media paths for <img src> (avatars, etc.). */

/**
 * DB stores root-absolute API paths like `/api/v1/users/{id}/avatar?v=…`.
 * Keep them host-root absolute so a `/dashboard` SPA base never rewrites them
 * to `/dashboard/api/v1/...`.
 */
export function mediaSrc(url: string | null | undefined): string | null {
  const raw = (url || "").trim();
  if (!raw) return null;
  if (/^https?:\/\//i.test(raw) || raw.startsWith("data:")) return raw;
  if (raw.startsWith("/")) return raw;
  return `/${raw.replace(/^\/+/, "")}`;
}
