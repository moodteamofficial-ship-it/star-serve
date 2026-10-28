/** Session-scoped customer referral from a scanned `#r=CODE` link. */

const REFERRAL_KEY = "ss.guest.customer_referral";
const PENDING_KEY = "ss.guest.customer_referral_pending";
const PARAM = "r";

let consumedThisNavigation: string | null | undefined;

export type GuestCustomerReferral = {
  referral_code: string;
  referrer_first_name: string | null;
};

export function normalizeReferralCode(value: string | null | undefined): string | null {
  const code = String(value ?? "")
    .replace(/[\s-]/g, "")
    .toUpperCase();
  return /^SS[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$/.test(code) ? code : null;
}

export function readGuestCustomerReferral(): GuestCustomerReferral | null {
  try {
    const raw = sessionStorage.getItem(REFERRAL_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<GuestCustomerReferral>;
    const code = normalizeReferralCode(parsed.referral_code);
    if (!code) return null;
    return { referral_code: code, referrer_first_name: parsed.referrer_first_name ?? null };
  } catch {
    return null;
  }
}

export function writeGuestCustomerReferral(referral: GuestCustomerReferral): void {
  try {
    sessionStorage.setItem(REFERRAL_KEY, JSON.stringify(referral));
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* private mode / blocked storage */
  }
}

export function clearGuestCustomerReferral(): void {
  try {
    sessionStorage.removeItem(REFERRAL_KEY);
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* ignore */
  }
}

function readPending(): string | null {
  try {
    return normalizeReferralCode(sessionStorage.getItem(PENDING_KEY));
  } catch {
    return null;
  }
}

/** Take `r` from the hash or query, stash it, and scrub it from the address bar. */
export function consumeReferralCodeFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  if (consumedThisNavigation !== undefined) return consumedThisNavigation;

  const { pathname, search, hash } = window.location;
  const hashParams = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  const queryParams = new URLSearchParams(search);
  const code =
    normalizeReferralCode(hashParams.get(PARAM)) ?? normalizeReferralCode(queryParams.get(PARAM));

  if (code) {
    try {
      sessionStorage.setItem(PENDING_KEY, code);
      sessionStorage.removeItem(REFERRAL_KEY);
    } catch {
      /* ignore */
    }
  }

  if (hashParams.has(PARAM) || queryParams.has(PARAM)) {
    hashParams.delete(PARAM);
    queryParams.delete(PARAM);
    const nextSearch = queryParams.toString();
    const nextHash = hashParams.toString();
    window.history.replaceState(
      window.history.state,
      "",
      `${pathname}${nextSearch ? `?${nextSearch}` : ""}${nextHash ? `#${nextHash}` : ""}`,
    );
  }

  consumedThisNavigation = code;
  return code;
}

/** Fresh scan first, then a pending code awaiting validation, then the validated one. */
export function resolveGuestReferralBootstrap(): {
  pendingCode: string | null;
  referral: GuestCustomerReferral | null;
} {
  const fromUrl = consumeReferralCodeFromLocation();
  if (fromUrl) return { pendingCode: fromUrl, referral: null };
  const pending = readPending();
  if (pending) return { pendingCode: pending, referral: null };
  return { pendingCode: null, referral: readGuestCustomerReferral() };
}
