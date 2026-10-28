import { apiRequest } from "@/services/api/client";

export type Customer = {
  id: string;
  first_name: string;
  last_name: string;
  other_names: string | null;
  id_number: string;
  kra_pin: string | null;
  phone: string;
  email: string | null;
  avatar_url?: string | null;
  date_of_birth?: string | null;
  status: string;
  branch_id?: string | null;
  assigned_user_id?: string | null;
  external_client_ref?: string | null;
  referral_code?: string | null;
  referred_by_intermediary_id?: string | null;
  referred_by_agent_code?: string | null;
  referred_by_agent_name?: string | null;
  referred_by_referral_code?: string | null;
  referred_at?: string | null;
  policies_count?: number;
  proposals_count?: number;
  created_at: string;
  updated_at?: string;
};

export type CustomerLastVehicle = {
  registration: string;
  chassis_number: string | null;
  engine_number: string | null;
  vehicle_year: number | null;
  engine_rating: number | null;
  make_code: string | null;
  make_name: string | null;
  model_code: string | null;
  model_name: string | null;
};

export type CustomerList = {
  items: Customer[];
  page: number;
  limit: number;
  total: number;
};

export const customerApi = {
  list(params: { page?: number; limit?: number; q?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    return apiRequest<CustomerList>(`/customers?${qs.toString()}`);
  },
  lookupByIdNumber(id_number: string) {
    const qs = new URLSearchParams({ id_number: id_number.trim() });
    return apiRequest<{
      found: boolean;
      customer: Customer | null;
      last_vehicle?: CustomerLastVehicle | null;
    }>(
      `/customers/lookup?${qs.toString()}`,
    );
  },
  create(body: {
    first_name: string;
    last_name: string;
    id_number: string;
    phone: string;
    email?: string;
    kra_pin?: string;
    other_names?: string;
  }) {
    return apiRequest<Customer>("/customers", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
