import { ApiError, apiRequest, getClientDeviceId } from "@/services/api/client";
import { resolveApiBaseUrl } from "@/services/api/envTarget";

export type Certificate = {
  id: string;
  policy_id: string;
  payment_id: string | null;
  customer_id: string | null;
  customer_name: string | null;
  vehicle_registration: string | null;
  certificate_number: string;
  status: string;
  external_certificate_ref: string | null;
  file_available: boolean;
  local_copy_available: boolean;
  local_stored_at: string | null;
  content_sha256: string | null;
  file_size_bytes: number | null;
  access_count: number;
  last_accessed_at: string | null;
  last_accessed_by_user_id: string | null;
  download_url_expires_at: string | null;
  generated_at: string | null;
  failure_message: string | null;
  job_id: string | null;
  created_at: string;
  updated_at: string;
};

export type CertificateList = {
  items: Certificate[];
  page: number;
  limit: number;
  total: number;
};

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export const certificateApi = {
  list(params: { page?: number; limit?: number; status?: string; policy_id?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.status) qs.set("status", params.status);
    if (params.policy_id) qs.set("policy_id", params.policy_id);
    return apiRequest<CertificateList>(`/certificates?${qs.toString()}`);
  },

  get(id: string) {
    return apiRequest<Certificate>(`/certificates/${id}`);
  },

  async downloadPdf(
    certificateId: string,
    disposition: "inline" | "attachment" = "inline",
  ): Promise<Blob> {
    const qs = new URLSearchParams({ disposition });
    const headers = new Headers();
    headers.set("X-Client-Device-Id", getClientDeviceId());
    const csrf = readCookie("ss_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);

    const response = await fetch(
      `${resolveApiBaseUrl()}/certificates/${certificateId}/download?${qs.toString()}`,
      { credentials: "include", headers },
    );
    if (!response.ok) {
      const err = (await response.json().catch(() => null)) as {
        error?: { message?: string; code?: string; details?: unknown[] };
      } | null;
      throw new ApiError(
        err?.error?.message || "Certificate PDF is not available yet.",
        err?.error?.code || "HTTP_ERROR",
        response.status,
        err?.error?.details,
      );
    }
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength < 8) {
      throw new ApiError(
        "Certificate PDF is not available yet.",
        "PDF_EMPTY",
        404,
      );
    }
    const head = new Uint8Array(buffer.slice(0, 4));
    const isPdf =
      head[0] === 0x25 &&
      head[1] === 0x50 &&
      head[2] === 0x44 &&
      head[3] === 0x46;
    if (!isPdf) {
      throw new ApiError(
        "Certificate PDF is not available yet.",
        "PDF_INVALID",
        404,
      );
    }
    return new Blob([buffer], { type: "application/pdf" });
  },
};
