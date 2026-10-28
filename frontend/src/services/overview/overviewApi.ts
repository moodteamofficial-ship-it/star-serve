import { apiRequest } from "@/services/api/client";

export type OverviewPeriodKey = "7d" | "30d" | "90d" | "ytd";

export type OverviewChannel = {
  key: string;
  label: string;
  amount: number;
  share: number;
};

export type OverviewGrowthMonth = {
  key: string;
  label: string;
  amount: number;
};

export type OverviewRecentApplication = {
  id: string;
  status: string;
  product_code: string;
  cover_option: string;
  gross_premium: number;
  currency: string;
  customer_name?: string | null;
  customer_avatar_url?: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type OverviewRecentActivity = {
  id: string;
  kind: string;
  action: string;
  resource: string;
  result: string;
  title: string;
  detail: string;
  actor_name: string | null;
  actor_avatar_url?: string | null;
  created_at: string | null;
};

export type OverviewQuickAction = {
  key: string;
  label: string;
  href: string;
  tone: "primary" | "default" | string;
};

export type OverviewSummary = {
  period: {
    key: OverviewPeriodKey;
    start: string;
    end: string;
    compare_start: string;
    compare_end: string;
  };
  capabilities: {
    payments: boolean;
    wallet: boolean;
    policies: boolean;
    customers: boolean;
    customer_create?: boolean;
    proposals: boolean;
    quote: boolean;
    certificates: boolean;
    agents: boolean;
    products: boolean;
    audit?: boolean;
    claims?: boolean;
    claim_create?: boolean;
  };
  sections: string[];
  headline: Record<string, number | string | undefined>;
  payments: {
    initiated: number;
    successful: number;
    pending: number;
    failed: number;
    success_rate: number;
    volume: number;
    volume_prior: number;
    volume_delta_pct: number;
    currency: string;
    daily: { date: string; count: number; success: number }[];
  } | null;
  premium: {
    gross: number;
    avg: number;
    settled: number;
    currency: string;
    volume_delta_pct: number;
    channels: OverviewChannel[];
    wallet_balance: number | null;
    growth?: OverviewGrowthMonth[];
  } | null;
  policies: {
    total: number;
    active: number;
    pending_payment: number;
    pending_certificate: number;
    cancelled: number;
    expired: number;
    created_in_period: number;
    cancelled_in_period: number;
    in_force_premium: number;
    sum_insured: number;
    avg_in_force_premium: number;
    expiring_30d: number;
    top_products: { code: string; count: number }[];
    currency: string;
    peak_weekday: string | null;
    week: number[];
  } | null;
  customers: {
    total: number;
    active: number;
    with_kra: number;
    linked: number;
    created_in_period: number;
    peak_weekday: string | null;
    week: number[];
  } | null;
  proposals: {
    created_in_period: number;
    drafts: number;
    approved: number;
    converted: number;
    rejected: number;
    converted_in_period: number;
    double_insurance_hits: number;
    pipeline_premium: number;
    in_pipeline: number;
    issuance_pct: number;
    conversion_pct: number;
    currency: string;
  } | null;
  certificates: {
    total: number;
    generated: number;
    pending: number;
    failed: number;
    revoked: number;
    generated_in_period: number;
  } | null;
  agents: {
    total: number;
    approved: number;
    pending: number;
    suspended: number;
    rejected: number;
    created_in_period: number;
  } | null;
  products: {
    total: number;
    active: number;
  } | null;
  wallet: {
    available_balance: number;
    ledger_balance: number;
    currency: string;
    status: string;
  } | null;
  activity: {
    months: { key: string; label: string; count: number }[];
    latest: number;
    peak: number;
    prior: number;
    total_6mo: number;
    delta_pct: number;
    of_peak_pct: number;
  } | null;
  premium_growth: {
    months: OverviewGrowthMonth[];
    latest: number;
    prior: number;
    peak: number;
    total_6mo: number;
    delta_pct: number;
    currency: string;
  } | null;
  claims: {
    total: number;
    open: number;
    unassigned: number;
    assigned: number;
    guest_intake: number;
    guest_open: number;
    intake: number;
    assessing: number;
    with_insurer: number;
    settling: number;
    closed: number;
    created_in_period: number;
    closed_in_period: number;
    claimed_open: number;
    approved_open: number;
    currency: string;
    queues: { key: string; label: string; count: number; amount: number }[];
    recent: {
      id: string;
      claim_number: string;
      status: string;
      channel: string;
      claimed_amount: number;
      approved_amount: number | null;
      currency: string;
      vehicle_registration: string | null;
      assigned: boolean;
      assigned_to_name: string | null;
      customer_name: string;
      updated_at: string | null;
    }[];
    week: number[];
  } | null;
  followups: {
    total: number;
    open: number;
    overdue: number;
    due_soon: number;
    waiting_client: number;
    waiting_desk: number;
    completed_in_period: number;
    created_in_period: number;
    by_type: { type: string; label: string; count: number }[];
    recent: {
      id: string;
      subject: string;
      type: string;
      label: string;
      status: string;
      due_at: string | null;
      claim_id: string;
      claim_number: string;
      customer_name: string;
      overdue: boolean;
    }[];
  } | null;
  recent_applications: OverviewRecentApplication[] | null;
  recent_activity: OverviewRecentActivity[] | null;
  quick_actions: OverviewQuickAction[] | null;
};

export const overviewApi = {
  summary(period: OverviewPeriodKey = "30d") {
    return apiRequest<OverviewSummary>(`/overview/summary?period=${period}`);
  },
};
