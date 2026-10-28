import { apiRequest } from "@/services/api/client";

export type Proposal = {
  id: string;
  customer_id: string;
  intermediary_id?: string | null;
  product_code: string;
  cover_option: string;
  cover_period: string;
  transaction_type?: string | null;
  vehicle_registration: string;
  vehicle_make: string;
  vehicle_model?: string | null;
  sum_insured: string | number;
  gross_premium: string | number | null;
  status: string;
  channel?: string | null;
  double_insurance_clear: boolean | null;
  job_id: string | null;
  created_at: string;
  updated_at?: string;
};

export type ProposalList = {
  items: Proposal[];
  page: number;
  limit: number;
  total: number;
};

export const proposalApi = {
  list(params: { page?: number; limit?: number; q?: string; status?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    return apiRequest<ProposalList>(`/proposals?${qs.toString()}`);
  },
  create(body: Record<string, unknown>, idempotencyKey?: string) {
    const headers: HeadersInit = {};
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    return apiRequest<{ proposal: Proposal; job_id: string }>("/proposals", {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  },
  approve(id: string) {
    return apiRequest<Proposal>(`/proposals/${id}/approve`, { method: "POST" });
  },
  issuePolicy(id: string) {
    return apiRequest(`/proposals/${id}/issue-policy`, { method: "POST" });
  },
  cancel(id: string) {
    return apiRequest<Proposal>(`/proposals/${id}/cancel`, { method: "POST" });
  },
};
