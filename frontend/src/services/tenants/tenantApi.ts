import { apiRequest } from "@/services/api/client";

export type TenantSettings = {
  id: string;
  legal_name: string;
  trading_name: string;
  status: string;
  database_mode: string;
  email: string | null;
  phone: string | null;
  branding: Record<string, unknown>;
  configuration: Record<string, unknown>;
};

export const tenantApi = {
  me() {
    return apiRequest<TenantSettings>("/tenants/me");
  },
  settings() {
    return apiRequest<TenantSettings>("/tenants/me/settings");
  },
  updateSettings(body: {
    trading_name?: string;
    email?: string;
    phone?: string;
    branding?: Record<string, unknown>;
    configuration?: Record<string, unknown>;
  }) {
    return apiRequest<TenantSettings>("/tenants/me", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  list(params: { page?: number; limit?: number; q?: string; status?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    return apiRequest<{ items: TenantSettings[]; total: number }>(`/tenants?${qs.toString()}`);
  },
  setStatus(id: string, status: string, reason: string) {
    return apiRequest<{ id: string; status: string }>(`/tenants/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status, reason }),
    });
  },
};
