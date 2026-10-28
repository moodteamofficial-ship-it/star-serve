import { apiRequest } from "@/services/api/client";

export type UssdOverview = {
  health: {
    service: string;
    published_version: number | null;
    provider_kind: string;
    provider_enabled: boolean;
    callback_path: string;
    callback_url?: string;
    service_code?: string;
  };
  metrics: Record<string, unknown>;
};

export type UssdConfig = {
  id: string;
  version: number;
  status: string;
  name: string;
  welcome_text: string;
  definition: {
    screens?: Record<
      string,
      {
        title?: string;
        options?: Array<{
          key: string;
          label: string;
          sort_order?: number;
          active?: boolean;
          workflow_action?: string | null;
          destination_screen?: string | null;
        }>;
        footer?: string;
      }
    >;
  };
  max_invalid_attempts: number;
  session_ttl_seconds: number;
  max_message_chars: number;
  nav_back: string;
  nav_home: string;
  published_at?: string | null;
};

export type SimulatorResult = {
  session_id: string;
  ussd_session_id: string | null;
  text: string;
  response_type: string;
  test_mode: boolean;
};

export const ussdApi = {
  overview(period = "last_7_days") {
    return apiRequest<UssdOverview>(`/ussd/admin/overview?period=${period}`);
  },
  configs() {
    return apiRequest<{ items: UssdConfig[] }>("/ussd/admin/configs");
  },
  createDraft(name: string) {
    return apiRequest<UssdConfig>("/ussd/admin/configs", {
      method: "POST",
      body: JSON.stringify({ name, from_published: true }),
    });
  },
  updateConfig(id: string, body: Record<string, unknown>) {
    return apiRequest<UssdConfig>(`/ussd/admin/configs/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  publish(id: string) {
    return apiRequest<UssdConfig>(`/ussd/admin/configs/${id}/publish`, { method: "POST" });
  },
  provider() {
    return apiRequest<Record<string, unknown>>("/ussd/admin/provider");
  },
  updateProvider(body: Record<string, unknown>) {
    return apiRequest<Record<string, unknown>>("/ussd/admin/provider", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  simulator(body: {
    session_id?: string;
    msisdn: string;
    text?: string | null;
    restart?: boolean;
    service_code?: string;
  }) {
    return apiRequest<SimulatorResult>("/ussd/admin/simulator", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  analytics(period = "last_7_days", workflow?: string, includeTest = false) {
    const qs = new URLSearchParams({ period });
    if (workflow) qs.set("workflow", workflow);
    qs.set("include_test", includeTest ? "true" : "false");
    return apiRequest<{ overview: Record<string, unknown>; funnel: unknown }>(
      `/ussd/admin/analytics?${qs}`,
    );
  },
  sessions(includeTest = true) {
    return apiRequest<{ items: Array<Record<string, unknown>> }>(
      `/ussd/admin/sessions?include_test=${includeTest ? "true" : "false"}`,
    );
  },
  session(id: string) {
    return apiRequest<Record<string, unknown>>(`/ussd/admin/sessions/${id}`);
  },
  audit() {
    return apiRequest<{ items: Array<Record<string, unknown>> }>("/ussd/admin/audit");
  },
};
