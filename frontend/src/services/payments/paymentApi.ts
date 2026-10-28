import { apiRequest } from "@/services/api/client";

export type Payment = {
  id: string;
  reference: string;
  policy_id: string | null;
  method: string;
  amount: string | number;
  currency: string;
  status: string;
  provider_receipt: string | null;
  failure_message: string | null;
  created_at: string;
  updated_at?: string;
  intermediary_id?: string | null;
  intermediary_name?: string | null;
  agent_code?: string | null;
  commission_beneficiary?: "AGENT" | "HOUSE" | string | null;
};

export type PaymentList = {
  items: Payment[];
  page: number;
  limit: number;
  total: number;
};

export type Wallet = {
  id: string;
  currency: string;
  available_balance: string | number;
  ledger_balance: string | number;
  status: string;
};

export const paymentApi = {
  get(paymentId: string, options?: { guest?: boolean }) {
    const path = options?.guest
      ? `/insurance/guest/payments/${paymentId}`
      : `/payments/${paymentId}`;
    return apiRequest<Payment>(path);
  },
  list(params: { page?: number; limit?: number; q?: string; status?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    return apiRequest<PaymentList>(`/payments?${qs.toString()}`);
  },
  initiate(body: { policy_id: string; method: string; phone?: string }, idempotencyKey: string) {
    return apiRequest<Payment>("/payments", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    });
  },
  confirmReceipt(paymentId: string, receipt: string) {
    return apiRequest<Payment>(`/payments/${paymentId}/confirm-receipt`, {
      method: "POST",
      body: JSON.stringify({ receipt }),
    });
  },
};

export const walletApi = {
  me() {
    return apiRequest<Wallet>("/wallets/me");
  },
  topUp(amount: number, description: string) {
    return apiRequest<Wallet>("/wallets/me/top-up", {
      method: "POST",
      body: JSON.stringify({ amount, currency: "KES", description }),
    });
  },
};
