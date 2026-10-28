import { apiRequest } from "@/services/api/client";

export type Intermediary = {
  id: string;
  name: string;
  email: string;
  phone: string;
  identification: string;
  agent_code: string;
  kra_pin: string | null;
  status: string;
  branch_id?: string | null;
  external_intermediary_ref?: string | null;
  approved_at?: string | null;
  has_login?: boolean;
  login_status?: string | null;
  created_at: string;
  updated_at?: string;
};

export type IntermediaryList = {
  items: Intermediary[];
  page: number;
  limit: number;
  total: number;
};

export const intermediaryApi = {
  list(params: { page?: number; limit?: number; q?: string; status?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    return apiRequest<IntermediaryList>(`/intermediaries?${qs.toString()}`);
  },
  create(body: {
    name: string;
    email: string;
    phone: string;
    identification: string;
    agent_code?: string;
    kra_pin?: string;
    password?: string;
  }) {
    return apiRequest<Intermediary>("/intermediaries", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  setLogin(id: string, password: string) {
    return apiRequest<Intermediary>(`/intermediaries/${id}/login`, {
      method: "POST",
      body: JSON.stringify({ password }),
    });
  },
  approve(id: string) {
    return apiRequest<Intermediary>(`/intermediaries/${id}/approve`, { method: "POST" });
  },
  update(
    id: string,
    body: {
      name?: string;
      email?: string;
      phone?: string;
      kra_pin?: string | null;
    },
  ) {
    return apiRequest<Intermediary>(`/intermediaries/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  kitChannels(id: string) {
    return apiRequest<{ channels: AgentKitChannel[] }>(`/intermediaries/${id}/kit-channels`);
  },
  resendKit(id: string, channel: AgentKitChannel) {
    return apiRequest<{ channel: AgentKitChannel; queued: AgentKitChannel[]; available: AgentKitChannel[] }>(
      `/intermediaries/${id}/resend-kit`,
      {
        method: "POST",
        body: JSON.stringify({ channel }),
      },
    );
  },
};

export type AgentKitChannel = "EMAIL" | "SMS" | "WHATSAPP";
