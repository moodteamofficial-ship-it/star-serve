/** Runtime API environment target — public URLs only, never DB credentials. */

export type ApiEnvironment = "development" | "staging" | "production" | "backup";

/** Product data plane — each backed by a separate DB / API process. */
export type DataPlane = "staging" | "live" | "backup";

const STORAGE_KEY = "ss_api_env";

export type EnvEndpoints = Record<ApiEnvironment, string>;

/**
 * Public API base URLs only (include /api/v1).
 * Secrets stay on each Cloud Run / local process via Secret Manager / .env.
 */
export function readEnvEndpoints(): EnvEndpoints {
  const development =
    import.meta.env.VITE_API_URL_DEVELOPMENT ||
    import.meta.env.VITE_API_BASE_URL ||
    "/api/v1";
  const staging =
    import.meta.env.VITE_API_URL_STAGING || development;
  const production =
    import.meta.env.VITE_API_URL_PRODUCTION || staging;
  const backup =
    import.meta.env.VITE_API_URL_BACKUP || production;
  return { development, staging, production, backup };
}

function applyDefaultLocalDevOnce(): void {
  if (typeof window === "undefined") return;
  const flag = "ss_api_env_local_dev_default_v1";
  try {
    if (localStorage.getItem(flag)) return;
    if ((import.meta.env.VITE_DEFAULT_API_ENV || "development") !== "development") {
      localStorage.setItem(flag, "1");
      return;
    }
    const raw = localStorage.getItem(STORAGE_KEY);
    // Prefer local uvicorn for localhost SPA; Staging/Live remain available in Data.
    if (!raw || raw === "staging") {
      localStorage.setItem(STORAGE_KEY, "development");
    }
    localStorage.setItem(flag, "1");
  } catch {
    /* private mode / disabled storage */
  }
}

export function getStoredApiEnvironment(): ApiEnvironment {
  applyDefaultLocalDevOnce();
  const raw = localStorage.getItem(STORAGE_KEY);
  if (
    raw === "development" ||
    raw === "staging" ||
    raw === "production" ||
    raw === "backup"
  ) {
    return raw;
  }
  const buildDefault = (import.meta.env.VITE_DEFAULT_API_ENV || "development") as string;
  if (
    buildDefault === "staging" ||
    buildDefault === "production" ||
    buildDefault === "backup"
  ) {
    return buildDefault;
  }
  return "development";
}

export function setStoredApiEnvironment(env: ApiEnvironment): void {
  localStorage.setItem(STORAGE_KEY, env);
}

function normalizeApiBase(url: string): string {
  return url.replace(/\/$/, "");
}

/** Apply server-stored user preference to localStorage; reload only if the API URL changes. */
export function syncStoredEnvFromUser(
  preferred: ApiEnvironment,
  currentProcessEnv: string,
): boolean {
  const stored = getStoredApiEnvironment();
  const urlBefore = normalizeApiBase(resolveApiBaseUrl(stored));
  if (stored !== preferred) {
    setStoredApiEnvironment(preferred);
  }
  const urlAfter = normalizeApiBase(resolveApiBaseUrl(preferred));
  if (preferred === currentProcessEnv) return false;
  return urlBefore !== urlAfter;
}

export function resolveApiBaseUrl(env: ApiEnvironment = getStoredApiEnvironment()): string {
  const endpoints = readEnvEndpoints();
  return endpoints[env].replace(/\/$/, "");
}

/** Map API env → product data plane (matches backend Settings.data_plane). */
export function dataPlaneForEnv(env: ApiEnvironment): DataPlane {
  if (env === "production") return "live";
  if (env === "backup") return "backup";
  return "staging";
}

export function envLabel(env: ApiEnvironment): string {
  switch (env) {
    case "development":
      return "Dev";
    case "staging":
      return "Staging";
    case "production":
      return "Live";
    case "backup":
      return "Backup";
  }
}

export function dataPlaneLabel(plane: DataPlane): string {
  switch (plane) {
    case "live":
      return "Live";
    case "backup":
      return "Backup";
    default:
      return "Staging";
  }
}

/** True when staging, live, and backup resolve to distinct API hosts. */
export function envEndpointsAreIsolated(endpoints: EnvEndpoints = readEnvEndpoints()): boolean {
  const normalize = (u: string) => u.replace(/\/$/, "");
  const stagingHost = normalize(endpoints.development);
  const live = normalize(endpoints.production);
  const backup = normalize(endpoints.backup);
  return stagingHost !== live && live !== backup && stagingHost !== backup;
}
