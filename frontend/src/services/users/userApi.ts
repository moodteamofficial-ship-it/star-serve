import { apiRequest } from "@/services/api/client";

export type StaffUser = {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  status: string;
  role_id: string | null;
  role_name?: string | null;
  role_code?: string | null;
  branch_id: string | null;
  branch_name?: string | null;
  branch_code?: string | null;
  avatar_url?: string | null;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type StaffUserList = {
  items: StaffUser[];
  page: number;
  limit: number;
  total: number;
};

export type StaffUserOption = {
  id: string;
  name: string;
  code?: string | null;
};

export type StaffUserOptions = {
  roles: StaffUserOption[];
  branches: StaffUserOption[];
};

export const userApi = {
  list(params: { page?: number; limit?: number; q?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    return apiRequest<StaffUserList>(`/users?${qs.toString()}`);
  },
  options() {
    return apiRequest<StaffUserOptions>("/users/options");
  },
  create(body: {
    full_name: string;
    email: string;
    password: string;
    phone?: string;
    role_id: string;
    branch_id?: string;
  }) {
    return apiRequest<StaffUser>("/users", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  update(
    id: string,
    body: {
      full_name?: string;
      email?: string;
      phone?: string | null;
      role_id?: string;
      branch_id?: string;
      password?: string;
    },
  ) {
    return apiRequest<StaffUser>(`/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  setStatus(id: string, status: "ACTIVE" | "DISABLED") {
    return apiRequest<StaffUser>(`/users/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },
};
