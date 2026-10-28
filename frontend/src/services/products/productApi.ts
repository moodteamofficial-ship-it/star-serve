import { apiRequest } from "@/services/api/client";

export type Product = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  cover_options: string[];
  is_active?: boolean;
  scope: string;
  provider_code?: string | null;
  synced_at?: string | null;
};

export type VehicleMake = {
  id: string;
  code: string;
  name: string;
  is_active?: boolean;
  scope: string;
  sort_order: number;
  provider_code?: string | null;
};

export const productApi = {
  listProducts() {
    return apiRequest<Product[]>("/products");
  },
  listMakes() {
    return apiRequest<VehicleMake[]>("/vehicle-makes");
  },
};
