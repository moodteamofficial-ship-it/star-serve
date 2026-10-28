import { apiRequest } from "@/services/api/client";

export type AuditEvent = {
  id: string;
  user_id?: string | null;
  actor_name?: string | null;
  actor_email?: string | null;
  actor_avatar_url?: string | null;
  action: string;
  resource: string;
  resource_id: string | null;
  result: string;
  message: string | null;
  metadata?: Record<string, unknown>;
  request_id?: string | null;
  ip_address?: string | null;
  created_at: string;
};

export type AuditList = {
  items: AuditEvent[];
  page: number;
  limit: number;
  total: number;
};

export const auditApi = {
  list(params: {
    page?: number;
    limit?: number;
    q?: string;
    action?: string;
    resource?: string;
  } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.action) qs.set("action", params.action);
    if (params.resource) qs.set("resource", params.resource);
    return apiRequest<AuditList>(`/audit/events?${qs.toString()}`);
  },
};
