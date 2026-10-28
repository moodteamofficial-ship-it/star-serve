import { apiRequest, getClientDeviceId } from "@/services/api/client";
import { resolveApiBaseUrl, type ApiEnvironment } from "@/services/api/envTarget";

/** Shell-safe profile from /auth/me and login — phone is masked; no lat/lng. */
export type UserPublic = {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  tenant_id: string;
  role_id: string;
  role_code: string;
  branch_id?: string | null;
  country_code?: string | null;
  phone_country_code?: string | null;
  country_id?: string | null;
  currency: string;
  timezone?: string | null;
  locale?: string | null;
  avatar_url?: string | null;
  permissions: string[];
  /** API deployment this session is bound to (server APP_ENV). */
  app_env: string;
  /** User's chosen target data plane — syncs frontend env switcher. */
  preferred_app_env: ApiEnvironment;
};

export type LoginData = {
  user: UserPublic;
  expires_in: number;
};

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export const authApi = {
  login(email: string, password: string) {
    return apiRequest<LoginData>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  me() {
    return apiRequest<UserPublic>("/auth/me");
  },
  logout() {
    return apiRequest<null>("/auth/logout", { method: "POST" });
  },
  refresh() {
    return apiRequest<LoginData>("/auth/refresh", { method: "POST" });
  },
  setPreferredEnv(app_env: ApiEnvironment) {
    return apiRequest<UserPublic>("/auth/preferred-env", {
      method: "PATCH",
      body: JSON.stringify({ app_env }),
    });
  },
  async uploadAvatar(file: File) {
    const headers = new Headers();
    headers.set("X-Client-Device-Id", getClientDeviceId());
    const csrf = readCookie("ss_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${resolveApiBaseUrl()}/auth/me/avatar`, {
      method: "POST",
      credentials: "include",
      headers,
      body: form,
    });
    const json = (await response.json()) as {
      success: boolean;
      data?: UserPublic;
      error?: { message?: string };
    };
    if (!response.ok || !json.success || !json.data) {
      throw new Error(json.error?.message || "Could not save your profile photo.");
    }
    return json.data;
  },
};
