const STORAGE_KEY = "ss.guest.tenant_id";

/** Agency picker is public-safe and changes rarely — avoid remount refetches. */
export const GUEST_TENANTS_STALE_MS = 5 * 60 * 1000;

export function readGuestTenantId(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function writeGuestTenantId(tenantId: string): void {
  try {
    if (tenantId) sessionStorage.setItem(STORAGE_KEY, tenantId);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode / blocked storage */
  }
}
