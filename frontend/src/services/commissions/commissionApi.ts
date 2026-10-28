import { apiRequest } from "@/services/api/client";

export type CommissionSettings = {
  id: string;
  currency: string;
  payout_cadence: "WEEKLY" | "MONTHLY" | string;
  certificate_rate_percent: string | number;
  claim_rate_percent: string | number;
  enabled: boolean;
  customer_referral_amount?: string | number;
  customer_referrals_enabled?: boolean;
  notes: string | null;
  version: number;
  updated_at: string;
  created_at: string;
};

export type CommissionAccount = {
  intermediary_id: string | null;
  agent_code: string | null;
  name: string;
  balance: string | number;
  currency: string;
  accrued_total: string | number;
  paid_total: string | number;
  entry_count: number;
};

export type CommissionLedgerEntry = {
  id: string;
  statement_ref: string;
  entry_kind: string;
  direction: string;
  source_event: string;
  amount: string | number;
  balance_after: string | number;
  currency: string;
  intermediary_id: string | null;
  agent_code_snapshot: string | null;
  intermediary_name_snapshot: string | null;
  base_amount: string | number | null;
  rate_percent_snapshot: string | number | null;
  payment_id: string | null;
  policy_id: string | null;
  description: string;
  occurred_at: string;
  created_at: string;
};

export type CommissionStatement = {
  account: CommissionAccount;
  opening_balance: string | number;
  closing_balance: string | number;
  period_start: string | null;
  period_end: string | null;
  entries: CommissionLedgerEntry[];
};

export const commissionApi = {
  getSettings() {
    return apiRequest<CommissionSettings>("/commissions/settings");
  },
  updateSettings(body: {
    certificate_rate_percent: number;
    claim_rate_percent: number;
    payout_cadence: string;
    enabled: boolean;
    notes?: string | null;
    currency?: string;
    customer_referral_amount?: number;
    customer_referrals_enabled?: boolean;
  }) {
    return apiRequest<CommissionSettings>("/commissions/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  listAccounts() {
    return apiRequest<{ items: CommissionAccount[] }>("/commissions/accounts");
  },
  listLedger(params: {
    page?: number;
    limit?: number;
    q?: string;
    entry_kind?: string;
    intermediary_id?: string;
    house?: boolean;
  } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    if (params.entry_kind) qs.set("entry_kind", params.entry_kind);
    if (params.intermediary_id) qs.set("intermediary_id", params.intermediary_id);
    if (params.house) qs.set("house", "true");
    return apiRequest<{
      items: CommissionLedgerEntry[];
      page: number;
      limit: number;
      total: number;
    }>(`/commissions/ledger?${qs.toString()}`);
  },
  statement(params: { intermediary_id?: string; house?: boolean } = {}) {
    const qs = new URLSearchParams();
    if (params.intermediary_id) qs.set("intermediary_id", params.intermediary_id);
    if (params.house) qs.set("house", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiRequest<CommissionStatement>(`/commissions/statement${suffix}`);
  },
  payout(body: { intermediary_id?: string; house?: boolean; note?: string }) {
    return apiRequest<CommissionLedgerEntry>("/commissions/payouts", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
