import { apiRequest } from "@/services/api/client";
import { insuranceApi } from "@/services/insurance/insuranceApi";

export type GuestClaimJourney = {
  steps: Array<{ id: string; label: string; state: "done" | "current" | "wait" | "skip" }>;
  now: string;
  waiting_on: "you" | "agency" | "insurer" | null;
  waiting_label: string;
  done: string[];
  pending: string[];
};

export type GuestClaimPublic = {
  id: string;
  claim_number: string;
  public_status: string;
  vehicle_registration: string | null;
  incident_date: string | null;
  submitted_at: string | null;
  notice: string | null;
  needs_information?: boolean;
  journey?: GuestClaimJourney;
  messages?: Array<{ from: "you" | "agency"; body: string; created_at: string }>;
};

async function withGuestSession<T>(tenantId: string, run: () => Promise<T>): Promise<T> {
  await insuranceApi.startGuestSession(tenantId);
  return run();
}

export const guestClaimApi = {
  file(tenantId: string, body: Record<string, unknown>) {
    return withGuestSession(tenantId, () =>
      apiRequest<GuestClaimPublic>("/insurance/guest/claims", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    );
  },
  lookup(tenantId: string, body: { claim_number: string; id_number: string; phone: string }) {
    return withGuestSession(tenantId, () =>
      apiRequest<GuestClaimPublic>("/insurance/guest/claims/lookup", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    );
  },
  followUp(tenantId: string, claimId: string, message: string) {
    return withGuestSession(tenantId, () =>
      apiRequest<GuestClaimPublic>(`/insurance/guest/claims/${claimId}/follow-up`, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
    );
  },
};
