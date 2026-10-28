/** Session-scoped agent attribution from a welcome QR scan. */

const REFERRAL_KEY = "ss.guest.agent_referral";
const PENDING_KEY = "ss.guest.agent_pending";
const HASH_KEY = "a";
const QUERY_KEY = "a";

/** Survives React Strict Mode remount within the same page load after URL scrub. */
let consumedThisNavigation: string | null | undefined;

export type GuestAgentReferral = {
  id: string;
  name: string;
  agent_code: string;
  locked: true;
};

function normalizeAgentCode(value: string | null | undefined): string | null {
  const code = String(value ?? "").trim();
  return /^\d{6}$/.test(code) ? code : null;
}

export function readGuestAgentReferral(): GuestAgentReferral | null {
  try {
    const raw = sessionStorage.getItem(REFERRAL_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<GuestAgentReferral>;
    const code = normalizeAgentCode(parsed.agent_code);
    if (!code || !parsed.id || !parsed.name) return null;
    return {
      id: String(parsed.id),
      name: String(parsed.name),
      agent_code: code,
      locked: true,
    };
  } catch {
    return null;
  }
}

export function writeGuestAgentReferral(agent: {
  id: string;
  name: string;
  agent_code: string;
}): void {
  try {
    const payload: GuestAgentReferral = {
      id: agent.id,
      name: agent.name,
      agent_code: agent.agent_code,
      locked: true,
    };
    sessionStorage.setItem(REFERRAL_KEY, JSON.stringify(payload));
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* private mode / blocked storage */
  }
}

export function clearGuestAgentReferral(): void {
  try {
    sessionStorage.removeItem(REFERRAL_KEY);
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* ignore */
  }
}

export function readPendingGuestAgentCode(): string | null {
  try {
    return normalizeAgentCode(sessionStorage.getItem(PENDING_KEY));
  } catch {
    return null;
  }
}

/** Stash a scanned code before the URL hash is scrubbed so reload can re-validate. */
export function writePendingGuestAgentCode(code: string): void {
  const normalized = normalizeAgentCode(code);
  if (!normalized) return;
  try {
    sessionStorage.setItem(PENDING_KEY, normalized);
  } catch {
    /* ignore */
  }
}

export function clearPendingGuestAgentCode(): void {
  try {
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* ignore */
  }
}

/** Build the welcome URL encoded in agent QR codes (code lives in the hash only). */
const WEB_URL_STAGING_DEFAULT =
  "https://starserve-dashboard-staging-233389149626.europe-west1.run.app";
const WEB_URL_PRODUCTION_DEFAULT =
  "https://quote.starserveinsuranceagency.com/dashboard";

function resolveWelcomeQrOrigin(): string {
  const staging =
    (import.meta.env.VITE_WEB_URL_STAGING || "").trim() || WEB_URL_STAGING_DEFAULT;
  const production =
    (import.meta.env.VITE_WEB_URL_PRODUCTION || "").trim() || WEB_URL_PRODUCTION_DEFAULT;
  const development =
    (import.meta.env.VITE_WEB_URL_DEVELOPMENT || "").trim() || staging;
  const backup =
    (import.meta.env.VITE_WEB_URL_BACKUP || "").trim() || production;

  let plane = "staging";
  try {
    plane = localStorage.getItem("ss_api_env") || import.meta.env.VITE_DEFAULT_API_ENV || "staging";
  } catch {
    plane = import.meta.env.VITE_DEFAULT_API_ENV || "staging";
  }

  const byPlane: Record<string, string> = {
    development,
    staging,
    production,
    backup,
  };
  const chosen = (byPlane[plane] || staging).replace(/\/$/, "");
  // Localhost is only for the SPA shell — customer-facing QRs always use the public web origin.
  if (/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(chosen)) {
    return (plane === "production" || plane === "backup" ? production : staging).replace(
      /\/$/,
      "",
    );
  }
  return chosen;
}

export function buildWelcomeAgentQrUrl(agentCode: string): string {
  const code = agentCode.trim();
  const base = resolveWelcomeQrOrigin().replace(/\/$/, "");
  const url = new URL(`${base}/`);
  url.hash = `${HASH_KEY}=${encodeURIComponent(code)}`;
  return url.toString();
}

export function buildWelcomeReferralQrUrl(referralCode: string): string {
  const base = resolveWelcomeQrOrigin().replace(/\/$/, "");
  const url = new URL(`${base}/`);
  url.hash = `r=${encodeURIComponent(referralCode.trim())}`;
  return url.toString();
}

/**
 * Pull a pending agent code from the address bar. Persist it before scrubbing
 * the hash so a hard refresh can still re-validate the same scan.
 */
export function consumeAgentCodeFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  if (consumedThisNavigation !== undefined) return consumedThisNavigation;

  const { pathname, search, hash } = window.location;
  let code: string | null = null;

  const hashBody = hash.startsWith("#") ? hash.slice(1) : hash;
  if (hashBody) {
    const params = new URLSearchParams(hashBody.includes("=") ? hashBody : `a=${hashBody}`);
    code = normalizeAgentCode(params.get(HASH_KEY));
  }

  if (!code) {
    const params = new URLSearchParams(search);
    code = normalizeAgentCode(params.get(QUERY_KEY));
  }

  if (code) {
    writePendingGuestAgentCode(code);
    // A new scan replaces any previously validated referral.
    try {
      sessionStorage.removeItem(REFERRAL_KEY);
    } catch {
      /* ignore */
    }
  }

  const hadAgentParam =
    Boolean(hash && (hash.includes(`${HASH_KEY}=`) || /^#[\dA-Za-z]+$/.test(hash))) ||
    new URLSearchParams(search).has(QUERY_KEY);

  if (hadAgentParam) {
    const params = new URLSearchParams(search);
    params.delete(QUERY_KEY);
    const nextSearch = params.toString();
    const next = `${pathname}${nextSearch ? `?${nextSearch}` : ""}`;
    window.history.replaceState(window.history.state, "", next);
  }

  consumedThisNavigation = code;
  return code;
}

/** Prefer a fresh URL scan, then pending validate-on-reload, then locked referral. */
export function resolveGuestAgentBootstrap(): {
  pendingCode: string | null;
  referral: GuestAgentReferral | null;
} {
  const fromUrl = consumeAgentCodeFromLocation();
  if (fromUrl) {
    return { pendingCode: fromUrl, referral: null };
  }
  const pending = readPendingGuestAgentCode();
  if (pending) {
    return { pendingCode: pending, referral: null };
  }
  return { pendingCode: null, referral: readGuestAgentReferral() };
}
