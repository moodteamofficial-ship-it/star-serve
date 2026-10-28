import { apiRequest } from "@/services/api/client";

export type Branch = {
  id: string;
  name: string;
  code: string | null;
  status: string;
  phone: string | null;
  email: string | null;
  city: string | null;
  address_line: string | null;
  users_count: number;
  created_at: string;
  updated_at: string;
};

export type BranchList = {
  items: Branch[];
  page: number;
  limit: number;
  total: number;
};

export const branchApi = {
  list(params: { page?: number; limit?: number; q?: string } = {}) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 25));
    if (params.q) qs.set("q", params.q);
    return apiRequest<BranchList>(`/branches?${qs.toString()}`);
  },
  create(body: {
    name: string;
    code?: string;
    phone?: string;
    email?: string;
    city?: string;
    address_line?: string;
  }) {
    return apiRequest<Branch>("/branches", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  update(
    id: string,
    body: {
      name?: string;
      code?: string;
      phone?: string;
      email?: string;
      city?: string;
      address_line?: string;
      status?: "ACTIVE" | "DISABLED";
    },
  ) {
    return apiRequest<Branch>(`/branches/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
};
