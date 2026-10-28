import { apiRequest } from "@/services/api/client";

export type Notification = {
  id: string;
  channel: string;
  template_code: string;
  recipient: string;
  recipient_name?: string | null;
  recipient_avatar_url?: string | null;
  subject: string | null;
  body: string;
  status: string;
  provider: string;
  provider_message_id: string | null;
  attempt_count: number;
  max_attempts?: number;
  last_error_message: string | null;
  created_at: string;
  updated_at?: string;
  sent_at?: string | null;
};

export type NotificationList = {
  items: Notification[];
  page: number;
  limit: number;
  total: number;
};

export const notificationApi = {
  list(params: {
    page?: number;
    limit?: number;
    q?: string;
    status?: string;
    channel?: string;
  } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    if (params.channel) qs.set("channel", params.channel);
    return apiRequest<NotificationList>(`/notifications?${qs.toString()}`);
  },
  templates() {
    return apiRequest<{ items: string[] }>("/notifications/templates");
  },
  send(
    body: {
      channel: string;
      template_code: string;
      recipient: string;
      context?: Record<string, string>;
      deliver_now?: boolean;
    },
    idempotencyKey: string,
  ) {
    return apiRequest<Notification>("/notifications", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    });
  },
  retry(id: string) {
    return apiRequest<Notification>(`/notifications/${id}/retry`, { method: "POST" });
  },
};
