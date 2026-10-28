import { ApiError, apiRequest, getClientDeviceId } from "@/services/api/client";
import { resolveApiBaseUrl } from "@/services/api/envTarget";

export type CoverOption = { id: string; name: string };

export type CatalogProduct = {
  external_id: string;
  code: string;
  name: string;
  description: string | null;
  category: string;
  cover_options: CoverOption[];
};

export type CatalogCategory = {
  category: string;
  product_count: number;
  products: CatalogProduct[];
};

export type CatalogMake = {
  external_id: string;
  code: string;
  name: string;
  models: { id: string; name: string }[];
};

export type CatalogResponse = {
  categories: CatalogCategory[];
  products: CatalogProduct[];
  makes: CatalogMake[];
  source: string;
};

export type PremiumResult = {
  job_id: string;
  premium: {
    basic_premium: number | null;
    phcf: number | null;
    training_levy: number | null;
    stamp_duty: number | null;
    gross_premium: number | null;
    cover_period_used?: string | null;
  };
};

export type CustomerLocal = {
  id: string;
  first_name: string;
  last_name: string;
  id_number: string;
  phone: string;
  kra_pin?: string | null;
  email?: string | null;
  external_client_ref?: string | null;
};

export type IssuanceClientResult = {
  job_id: string;
  provider: Record<string, unknown> | null;
  local: CustomerLocal;
};

/** Masked values only — real ones are applied server-side. */
export type GuestReturningLookup = {
  found: boolean;
  masked_name: string | null;
  client: {
    first_name: string;
    last_name: string;
    phone: string | null;
    email: string | null;
  } | null;
  vehicle: {
    registration: string | null;
    chassis_number: string | null;
    engine_number: string | null;
    vehicle_year: number | null;
    engine_rating: number | null;
    make_code: string | null;
    make_name: string | null;
    model_code: string | null;
    model_name: string | null;
  } | null;
};

export type IssuanceSubmitResult = {
  job_id: string;
  premium: PremiumResult["premium"];
  proposal: { id: string; status: string; gross_premium?: number | string | null };
  policy: {
    id: string;
    policy_number: string;
    status: string;
    gross_premium?: number | string | null;
    vehicle_registration?: string;
  };
  provider: {
    proposal_oid?: string;
    note_oid?: string | number;
    insured_item?: string | number;
    document_number?: string;
    amount_to_pay?: number | string;
  };
  /** Buyer's referral credit; the discount only applies on BirdView M-Pesa. */
  referral?: {
    code_applied: string | null;
    credit_balance: string;
    discount: string;
    /** Agency fee on monthly cover — always on top of Definite's total. */
    referral_cost?: string;
    amount_payable: string;
  };
};

export type IssuancePayResult = {
  payment: {
    id: string;
    status: string;
    method?: string;
    amount?: number | string;
    job_id?: string;
  };
  policy: {
    id: string;
    policy_number: string;
    status: string;
    certificate_ref?: string | null;
  };
  certificate: {
    id: string;
    certificate_number?: string;
    external_certificate_ref?: string | null;
    file_available?: boolean;
    local_copy_available?: boolean;
    access_count?: number;
    last_accessed_at?: string | null;
    status?: string;
  } | null;
};

export type GuestTenant = {
  id: string;
  name: string;
  tenant_type: string;
};

export const insuranceApi = {
  listGuestTenants() {
    return apiRequest<{ items: GuestTenant[] }>("/insurance/guest/tenants");
  },
  ensureGuestCsrf() {
    return apiRequest<{ ok: boolean }>("/insurance/guest/csrf");
  },
  startGuestSession(tenantId?: string) {
    const body = JSON.stringify(tenantId ? { tenant_id: tenantId } : {});
    const post = () =>
      apiRequest<{
        expires_at: string;
        tenant_id: string;
        tenant_bound: boolean;
        session_minutes: number;
      }>("/insurance/guest/session", {
        method: "POST",
        body,
      });

    return post().catch(async (err: unknown) => {
      // Stale guest cookie / CSRF pair: remint readable CSRF, then retry once.
      const isCsrf =
        err instanceof ApiError &&
        (err.code === "CSRF_VALIDATION_FAILED" || /csrf/i.test(err.message));
      if (!isCsrf) throw err;
      await this.ensureGuestCsrf();
      return post();
    });
  },
  catalog(guest = false) {
    const path = guest ? "/insurance/guest/catalog" : "/insurance/catalog";
    const load = () => apiRequest<CatalogResponse>(path);
    if (!guest) return load();
    return load().catch(async (err: unknown) => {
      const needsSession =
        err instanceof ApiError &&
        err.status === 401 &&
        (err.code === "AUTHENTICATION_ERROR" || /guest quote session/i.test(err.message));
      if (!needsSession) throw err;
      await this.startGuestSession();
      return load();
    });
  },
  providerWalletBalance(agentCode?: string) {
    const qs = new URLSearchParams();
    if (agentCode) qs.set("agent_code", agentCode);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiRequest<{
      agent_code: string;
      balance: number | null;
      currency: string;
      source?: string | null;
    }>(`/insurance/provider-wallet/balance${suffix}`);
  },
  checkClient(id_number: string) {
    const qs = new URLSearchParams({ id_number });
    return apiRequest<{
      job_id: string;
      provider: Record<string, unknown> | null;
      local: CustomerLocal | null;
    }>(`/insurance/clients/check?${qs.toString()}`);
  },
  ensureClient(body: {
    first_name: string;
    last_name: string;
    id_number: string;
    phone: string;
    kra_pin?: string;
    email?: string;
    other_names?: string;
  }) {
    return apiRequest<IssuanceClientResult>("/insurance/clients/ensure", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  issuanceClient(
    body: {
      first_name: string;
      last_name: string;
      id_number: string;
      phone: string;
      kra_pin?: string;
      email: string;
      other_names?: string;
    },
    guest = false,
  ) {
    return apiRequest<IssuanceClientResult>(
      guest ? "/insurance/guest/client" : "/insurance/issuance/client",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );
  },
  guestClientLookup(idNumber: string) {
    return apiRequest<GuestReturningLookup>("/insurance/guest/client/lookup", {
      method: "POST",
      body: JSON.stringify({ id_number: idNumber.trim() }),
    });
  },
  guestReturningClient(idNumber: string) {
    return apiRequest<IssuanceClientResult>("/insurance/guest/client/returning", {
      method: "POST",
      body: JSON.stringify({ id_number: idNumber.trim() }),
    });
  },
  issuanceSubmit(body: {
    customer_id: string;
    product_external_id: string;
    product_code: string;
    product_name?: string;
    cover_option_id: string;
    cover_option_name?: string;
    cover_period: string;
    cover_period_used?: string;
    capacity: number;
    tonnage?: number;
    sum_insured: number;
    vehicle_registration: string;
    vehicle_make_code: string;
    vehicle_make_name: string;
    vehicle_model_code: string;
    vehicle_model_name: string;
    vehicle_year: number;
    chassis_number: string;
    engine_number?: string;
    engine_rating?: number;
    agent_code?: string;
    // The certificate's intermediary name and IRA number are read server-side from
    // this approved intermediary record.
    intermediary_id?: string;
    referral_code?: string;
    /** Guest only: server swaps in the returning client's stored vehicle identifiers. */
    use_last_vehicle?: boolean;
  },
    guest = false,
  ) {
    return apiRequest<IssuanceSubmitResult>(
      guest ? "/insurance/guest/submit" : "/insurance/issuance/submit",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );
  },
  /** Abandon an unconfirmed STK so the next pay sends a fresh prompt. */
  cancelPendingPayment(policyId: string, guest = false) {
    return apiRequest<{ cancelled: boolean; payment: { id: string; status: string } | null }>(
      guest ? "/insurance/guest/pay/cancel" : "/insurance/issuance/pay/cancel",
      {
        method: "POST",
        body: JSON.stringify({ policy_id: policyId }),
      },
    );
  },
  issuancePay(
    body: { policy_id: string; method?: string; phone?: string },
    guest = false,
    options: RequestInit = {},
  ) {
    return apiRequest<IssuancePayResult>(
      guest ? "/insurance/guest/pay" : "/insurance/issuance/pay",
      {
        method: "POST",
        body: JSON.stringify(body),
        ...options,
      },
    );
  },
  calculatePremium(body: {
    sum_insured: number;
    cover_period: string;
    product: string;
    cover_option: string;
    transaction_type: string;
    capacity?: number;
    tonnage?: number;
  },
    guest = false,
  ) {
    return apiRequest<PremiumResult>(
      guest ? "/insurance/guest/premium" : "/insurance/premium/calculate",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );
  },
  resolveGuestAgent(agentCode: string) {
    const code = agentCode.trim();
    return apiRequest<{ id: string; name: string; agent_code: string }>(
      `/insurance/guest/agents/${encodeURIComponent(code)}`,
    );
  },
  resolveGuestReferral(referralCode: string) {
    return apiRequest<{ referral_code: string; referrer_first_name: string | null }>(
      `/insurance/guest/referrals/${encodeURIComponent(referralCode.trim())}`,
    );
  },
  async uploadCustomerDocument(
    customerId: string,
    kind: "logbook" | "id_front" | "id_back",
    file: File,
    guest = false,
  ) {
    const headers = new Headers();
    headers.set("X-Client-Device-Id", getClientDeviceId());
    const csrfMatch = document.cookie.match(/(?:^|; )ss_csrf=([^;]*)/);
    if (csrfMatch) headers.set("X-CSRF-Token", decodeURIComponent(csrfMatch[1]));
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    const path = guest
      ? `/insurance/guest/customers/${customerId}/documents`
      : `/customers/${customerId}/documents`;
    const response = await fetch(`${resolveApiBaseUrl()}${path}`, {
      method: "POST",
      credentials: "include",
      headers,
      body: form,
    });
    const json = (await response.json()) as {
      success: boolean;
      data?: { kind: string; url: string };
      error?: { message?: string };
    };
    if (!response.ok || !json.success || !json.data) {
      throw new ApiError(
        json.error?.message || "Upload failed",
        "UPLOAD_FAILED",
        response.status,
      );
    }
    return json.data;
  },
  syncReference() {
    return apiRequest("/insurance/reference/sync", { method: "POST" });
  },
};
