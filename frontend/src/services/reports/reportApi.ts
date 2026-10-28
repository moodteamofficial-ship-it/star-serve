import { apiRequest } from "@/services/api/client";

export type ReportRun = {
  id: string;
  report_type: string;
  status: string;
  result_summary: Record<string, unknown>;
  failure_message: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at?: string;
};

export type ReportList = {
  items: ReportRun[];
  page: number;
  limit: number;
  total: number;
};

export const reportApi = {
  types() {
    return apiRequest<{ items: string[] }>("/reports/types");
  },
  list(params: { page?: number; limit?: number; report_type?: string; status?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.report_type) qs.set("report_type", params.report_type);
    if (params.status) qs.set("status", params.status);
    return apiRequest<ReportList>(`/reports?${qs.toString()}`);
  },
  run(report_type: string) {
    return apiRequest<ReportRun>("/reports", {
      method: "POST",
      body: JSON.stringify({ report_type, params: {} }),
    });
  },
};
