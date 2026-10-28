import { apiRequest } from "@/services/api/client";

export type PlatformMetrics = {
  tenants: { total: number; active: number; dedicated_database: number };
  users: { total: number };
  policies: { total: number };
  payments: { total: number };
  customers: { total: number };
};

export const platformApi = {
  metrics() {
    return apiRequest<PlatformMetrics>("/platform/metrics");
  },
};
