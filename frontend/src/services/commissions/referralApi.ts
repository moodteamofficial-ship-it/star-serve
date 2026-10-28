import { apiRequest } from "@/services/api/client";

export type ReferralAccount = {
  referral_code: string;
  referral_link: string;
  id_number: string;
  holder_name: string | null;
  phone: string | null;
  customer_id: string | null;
  balance: string;
  earned_total: string;
  redeemed_total: string;
  referrals: number;
  created_at: string | null;
};

export type ReferralKitChannel = "EMAIL" | "SMS" | "WHATSAPP";

export const referralApi = {
  listAccounts(q?: string) {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiRequest<{ items: ReferralAccount[] }>(`/referrals/accounts${suffix}`);
  },
  forCustomer(customerId: string) {
    return apiRequest<{ referral_code: string | null; referral_link: string | null; balance: string }>(
      `/referrals/customers/${encodeURIComponent(customerId)}`,
    );
  },
  kitChannels(customerId: string) {
    return apiRequest<{ channels: ReferralKitChannel[] }>(
      `/referrals/customers/${encodeURIComponent(customerId)}/kit-channels`,
    );
  },
  resendKit(customerId: string, channel: ReferralKitChannel) {
    return apiRequest<{
      channel: ReferralKitChannel;
      queued: ReferralKitChannel[];
      available: ReferralKitChannel[];
      referral_code: string;
      referral_link: string;
    }>(`/referrals/customers/${encodeURIComponent(customerId)}/resend-kit`, {
      method: "POST",
      body: JSON.stringify({ channel }),
    });
  },
};
