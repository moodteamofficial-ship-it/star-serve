/** Central API client — credentials via HttpOnly cookies; CSRF header on mutations. */

import { resolveApiBaseUrl } from "@/services/api/envTarget";
import { beginRequest, endRequest } from "@/services/api/requestActivity";
import { notifySessionUser } from "@/services/auth/sessionBridge";
import type { LoginData } from "@/services/auth/authApi";

export type ApiSuccess<T> = {
  success: true;
  data: T;
  message: string;
  requestId?: string | null;
  jobId?: string | null;
};

export type ApiFailure = {
  success: false;
  error: { code: string; message: string; details?: unknown[] };
  requestId?: string | null;
  jobId?: string | null;
};

export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

const DEVICE_STORAGE_KEY = "ss_client_device_id";
const AUTH_SKIP_REFRESH = new Set([
  "/auth/login",
  "/auth/refresh",
  "/auth/logout",
]);

let refreshInFlight: Promise<boolean> | null = null;

function apiBase(): string {
  return resolveApiBaseUrl();
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** True when the readable double-submit CSRF cookie is present. */
export function hasCsrfCookie(): boolean {
  return Boolean(readCookie("ss_csrf"));
}

/** Stable per-browser id used by progressive login lockouts. */
export function getClientDeviceId(): string {
  try {
    const existing = window.localStorage.getItem(DEVICE_STORAGE_KEY);
    if (existing && existing.length >= 8) return existing.slice(0, 128);
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `dev-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(DEVICE_STORAGE_KEY, id);
    return id;
  } catch {
    return "anonymous-device";
  }
}

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown[];

  constructor(message: string, code: string, status: number, details?: unknown[]) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function buildHeaders(options: RequestInit): Headers {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (!headers.has("X-Client-Device-Id")) {
    headers.set("X-Client-Device-Id", getClientDeviceId());
  }

  if (method !== "GET" && method !== "HEAD") {
    const csrf = readCookie("ss_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  return headers;
}

/** Top loader only for user-facing writes — not reads or silent session refresh. */
function shouldShowTopLoader(method: string, path: string): boolean {
  const m = method.toUpperCase();
  if (m === "GET" || m === "HEAD" || m === "OPTIONS") return false;
  if (path === "/auth/refresh") return false;
  return true;
}

async function tryRefreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const headers = new Headers();
      headers.set("X-Client-Device-Id", getClientDeviceId());
      const csrf = readCookie("ss_csrf");
      if (csrf) headers.set("X-CSRF-Token", csrf);

      const response = await fetch(`${apiBase()}/auth/refresh`, {
        method: "POST",
        headers,
        credentials: "include",
      });
      const payload = (await response.json()) as ApiResult<LoginData>;
      if (!response.ok || !payload.success) {
        // Only a confirmed unauthenticated refresh ends the shell session.
        // 403/5xx/config errors must not look like a logout.
        if (response.status === 401) {
          notifySessionUser(null);
        }
        return false;
      }
      notifySessionUser(payload.data.user);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<ApiSuccess<T>> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = buildHeaders(options);
  const skipRefresh = AUTH_SKIP_REFRESH.has(path);
  const trackLoader = shouldShowTopLoader(method, path);

  if (trackLoader) beginRequest();
  try {
    let response = await fetch(`${apiBase()}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
    let payload = (await response.json()) as ApiResult<T>;

    if (
      response.status === 401 &&
      !skipRefresh &&
      method !== "HEAD"
    ) {
      const refreshed = await tryRefreshSession();
      if (refreshed) {
        const retryHeaders = buildHeaders(options);
        response = await fetch(`${apiBase()}${path}`, {
          ...options,
          headers: retryHeaders,
          credentials: "include",
        });
        payload = (await response.json()) as ApiResult<T>;
      }
    }

    if (!response.ok || !payload.success) {
      const message =
        !payload.success && payload.error?.message
          ? payload.error.message
          : "Request failed";
      const code = !payload.success ? payload.error.code : "HTTP_ERROR";
      const details = !payload.success ? payload.error.details : undefined;
      throw new ApiError(message, code, response.status, details);
    }

    return payload;
  } finally {
    if (trackLoader) endRequest();
  }
}
