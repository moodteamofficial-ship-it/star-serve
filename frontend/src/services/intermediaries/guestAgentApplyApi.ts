import { apiRequest } from "@/services/api/client";
import { insuranceApi } from "@/services/insurance/insuranceApi";

export type GuestAgentApplication = {
  name: string;
  email: string;
  phone: string;
  identification: string;
  agent_code?: string;
  kra_pin?: string;
  password?: string;
  website?: string;
};

export const guestAgentApplyApi = {
  async apply(tenantId: string, body: GuestAgentApplication) {
    await insuranceApi.startGuestSession(tenantId);
    return apiRequest<{ status: "PENDING" }>("/insurance/guest/agents/apply", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
