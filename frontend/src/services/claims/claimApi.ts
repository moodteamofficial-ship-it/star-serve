import { apiRequest, getClientDeviceId } from "@/services/api/client";
import { resolveApiBaseUrl } from "@/services/api/envTarget";

export type ClaimCapabilities = {
  can_view: boolean;
  can_edit: boolean;
  can_assign: boolean;
  can_vet: boolean;
  can_request_information: boolean;
  can_recommend_approval: boolean;
  can_approve: boolean;
  already_approved: boolean;
  can_reject: boolean;
  can_forward: boolean;
  can_record_insurer_decision: boolean;
  can_record_settlement: boolean;
  can_view_sensitive: boolean;
  can_upload_document: boolean;
  can_delete_document: boolean;
  can_download_document: boolean;
  can_view_notes: boolean;
  can_add_note: boolean;
  can_send_client_message: boolean;
  can_create_followup: boolean;
  can_complete_followup: boolean;
  can_authorize_payment: boolean;
  can_execute_payment: boolean;
  can_view_payment: boolean;
  can_retry_payment: boolean;
  can_close: boolean;
  can_amend: boolean;
  visible_sections: string[];
};

export type ClaimListItem = {
  id: string;
  claim_number: string;
  status: string;
  claim_type: string;
  policy_id: string;
  customer_id: string;
  customer_name: string | null;
  agency_name: string | null;
  vehicle_registration: string | null;
  claimed_amount: string | number;
  approved_amount: string | number | null;
  currency: string;
  assigned_to_user_id: string | null;
  assigned_to_name: string | null;
  channel: string;
  version: number;
  created_at: string;
  updated_at: string;
  capabilities?: ClaimCapabilities;
};

export type ClaimDetail = {
  id: string;
  claim_number: string;
  status: string;
  claim_type: string;
  channel: string;
  agency_name?: string | null;
  version: number;
  policy: {
    id: string;
    policy_number: string | null;
    status: string | null;
    product_code: string | null;
    cover_option: string | null;
    cover_start_date: string | null;
    cover_end_date: string | null;
  };
  claimant: {
    id: string;
    name: string | null;
    phone: string | null;
    id_number: string | null;
  };
  accident: {
    incident_date: string | null;
    incident_time: string | null;
    incident_location: string | null;
    incident_description: string | null;
    police_abstract_number: string | null;
  };
  vehicle: {
    registration: string | null;
    make: string | null;
    model: string | null;
    chassis_number: string | null;
  };
  driver: { name: string | null; license_number: string | null };
  damage: { description: string | null };
  injuries: { summary: string | null; medical_notes: string | null };
  financial: {
    claimed_amount: string | number;
    approved_amount: string | number | null;
    currency: string;
    beneficiary_type: string | null;
    beneficiary_reference: string | null;
  };
  risk_assessment: string | null;
  assigned_to_user_id: string | null;
  assigned_to_name: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  closed_at: string | null;
  capabilities: ClaimCapabilities;
  vetting: Array<Record<string, unknown>>;
  assignments: Array<Record<string, unknown>>;
  definite_reviews: Array<Record<string, unknown>>;
  approvals: Array<Record<string, unknown>>;
  followups: Array<Record<string, unknown>>;
  documents: Array<Record<string, unknown>>;
  notes: Array<Record<string, unknown>>;
  timeline: Array<{
    id: string;
    actor_type: string;
    actor_display_name: string | null;
    actor_role: string | null;
    action: string;
    summary: string;
    previous_state: string | null;
    new_state: string | null;
    created_at: string;
    metadata: Record<string, unknown>;
  }>;
  amendments: Array<Record<string, unknown>>;
  payments?: Array<Record<string, unknown>>;
};

export type ClaimDashboard = {
  role_code: string;
  status_counts: Record<string, number>;
  assigned: ClaimListItem[];
  assigned_total: number;
  queues: Record<string, ClaimListItem[]>;
  queue_counts?: Record<string, number>;
  capabilities: {
    can_create: boolean;
    can_supervise: boolean;
    can_manage_policies: boolean;
  };
};

export type ClaimList = {
  items: ClaimListItem[];
  page: number;
  limit: number;
  total: number;
};

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export const claimApi = {
  dashboard() {
    return apiRequest<ClaimDashboard>("/claims/dashboard");
  },
  list(
    params: {
      page?: number;
      limit?: number;
      q?: string;
      status?: string;
      assigned_to_me?: boolean;
      queue?: string;
    } = {},
  ) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    if (params.assigned_to_me) qs.set("assigned_to_me", "true");
    if (params.queue) qs.set("queue", params.queue);
    return apiRequest<ClaimList>(`/claims?${qs.toString()}`);
  },
  get(id: string) {
    return apiRequest<ClaimDetail>(`/claims/${id}`);
  },
  recordView(id: string) {
    return apiRequest<ClaimDetail>(`/claims/${id}/view`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },
  listAssignees(id: string) {
    return apiRequest<{ items: Array<{ id: string; name: string; role: string }> }>(
      `/claims/${id}/assignees`,
    );
  },
  create(body: Record<string, unknown>) {
    return apiRequest<ClaimDetail>("/claims", { method: "POST", body: JSON.stringify(body) });
  },
  action(id: string, path: string, body: Record<string, unknown> = {}) {
    return apiRequest<ClaimDetail>(`/claims/${id}/${path}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  completeFollowup(claimId: string, followupId: string) {
    return apiRequest<ClaimDetail>(`/claims/${claimId}/followups/${followupId}/complete`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },
  async uploadDocument(claimId: string, file: File, kind: string) {
    const headers = new Headers();
    headers.set("X-Client-Device-Id", getClientDeviceId());
    const csrf = readCookie("ss_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    const response = await fetch(`${resolveApiBaseUrl()}/claims/${claimId}/documents`, {
      method: "POST",
      credentials: "include",
      headers,
      body: form,
    });
    const json = (await response.json()) as { success: boolean; data?: ClaimDetail; error?: { message?: string } };
    if (!response.ok || !json.success) {
      throw new Error(json.error?.message || "Upload failed");
    }
    return json.data as ClaimDetail;
  },
  async fetchDocument(claimId: string, documentId: string) {
    const headers = new Headers();
    headers.set("X-Client-Device-Id", getClientDeviceId());
    const csrf = readCookie("ss_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const response = await fetch(
      `${resolveApiBaseUrl()}/claims/${claimId}/documents/${documentId}`,
      { credentials: "include", headers },
    );
    if (!response.ok) throw new Error("Document is not available");
    return response.blob();
  },
  async downloadDocument(claimId: string, documentId: string, filename: string) {
    const blob = await claimApi.fetchDocument(claimId, documentId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },
  async fetchPdf(claimId: string, disposition: "inline" | "attachment" = "inline") {
    const headers = new Headers();
    headers.set("X-Client-Device-Id", getClientDeviceId());
    const csrf = readCookie("ss_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const qs = new URLSearchParams({ disposition });
    const response = await fetch(`${resolveApiBaseUrl()}/claims/${claimId}/pdf?${qs.toString()}`, {
      credentials: "include",
      headers,
    });
    if (!response.ok) {
      const json = (await response.json().catch(() => null)) as { error?: { message?: string } } | null;
      throw new Error(json?.error?.message || "Could not prepare the claim PDF");
    }
    const buffer = await response.arrayBuffer();
    const head = new Uint8Array(buffer.slice(0, 4));
    const isPdf =
      buffer.byteLength >= 8 &&
      head[0] === 0x25 &&
      head[1] === 0x50 &&
      head[2] === 0x44 &&
      head[3] === 0x46;
    if (!isPdf) {
      throw new Error("Could not prepare the claim PDF");
    }
    return new Blob([buffer], { type: "application/pdf" });
  },
  async downloadPdf(claimId: string, filename: string) {
    const blob = await claimApi.fetchPdf(claimId, "attachment");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
