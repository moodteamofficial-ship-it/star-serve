import { apiRequest } from "@/services/api/client";

export type Policy = {
  id: string;
  policy_number: string;
  customer_id: string;
  proposal_id: string | null;
  product_code: string;
  cover_option: string;
  vehicle_registration: string;
  vehicle_make?: string | null;
  vehicle_model?: string | null;
  status: string;
  gross_premium: string | number | null;
  created_at: string;
  updated_at?: string;
};

export type PolicyList = {
  items: Policy[];
  page: number;
  limit: number;
  total: number;
};

export const policyApi = {
  list(params: { page?: number; limit?: number; q?: string; status?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    return apiRequest<PolicyList>(`/policies?${qs.toString()}`);
  },
  cancel(id: string, reason_code: string) {
    return apiRequest<Policy>(`/policies/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason_code }),
    });
  },
  activate(id: string) {
    return apiRequest<Policy>(`/policies/${id}/activate`, { method: "POST" });
  },
};
