import { apiRequest } from "@/services/api/client";

export type OperationalState = {
  enabled: boolean;
  reason: string | null;
  disabled_at: string | null;
  disabled_by: string | null;
  version: number;
};

export type ServicesState = {
  services: Record<string, boolean>;
  version: number;
};

export type NotificationChannelsState = {
  channels: Record<string, { enabled: boolean }>;
  version: number;
};

export type SystemConfigSnapshot = {
  operational: OperationalState;
  services: ServicesState;
  notification_channels: NotificationChannelsState;
};

export type CountryRow = {
  id: string;
  iso2: string;
  iso3: string | null;
  name: string;
  phone_code: string | null;
  currency_code: string | null;
  status: string;
};

export type CurrencyRow = {
  code: string;
  name: string;
  symbol: string | null;
  decimal_places: number;
  status: string;
};

export type RoleRow = {
  id: string;
  tenant_id: string | null;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  status: string;
  permissions: string[];
};

export type PermissionRow = {
  code: string;
  description?: string | null;
  category?: string | null;
};

export const systemConfigApi = {
  snapshot() {
    return apiRequest<SystemConfigSnapshot>("/system-config");
  },
  setOperational(body: { enabled: boolean; reason: string; expected_version: number }) {
    return apiRequest<OperationalState>("/system-config/operational", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  setServices(body: {
    services: Record<string, boolean>;
    reason: string;
    expected_version: number;
  }) {
    return apiRequest<ServicesState>("/system-config/services", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  setNotificationChannels(body: {
    channels: Record<string, { enabled: boolean }>;
    reason: string;
    expected_version: number;
  }) {
    return apiRequest<NotificationChannelsState>("/system-config/notification-channels", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
};

export const referenceApi = {
  countries() {
    return apiRequest<{ items: CountryRow[]; total: number }>("/reference/countries");
  },
  phoneCountries() {
    return apiRequest<{
      items: { iso: string; name: string; dial: string }[];
      default_iso: string | null;
      total: number;
    }>("/reference/phone-countries");
  },
  currencies() {
    return apiRequest<{ items: CurrencyRow[]; total: number }>("/reference/currencies");
  },
  createCountry(body: {
    iso2: string;
    iso3?: string;
    name: string;
    phone_code?: string;
    currency_code?: string;
    status?: string;
  }) {
    return apiRequest<CountryRow>("/reference/countries", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  updateCountry(
    id: string,
    body: {
      name?: string;
      phone_code?: string;
      currency_code?: string;
      iso3?: string;
      status?: string;
    },
  ) {
    return apiRequest<CountryRow>(`/reference/countries/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
};

export const rolesApi = {
  list() {
    return apiRequest<{ items: RoleRow[]; total: number }>("/roles");
  },
  permissions() {
    return apiRequest<{ items: PermissionRow[]; total: number }>("/roles/permissions");
  },
  update(id: string, body: { name?: string; description?: string; status?: string }) {
    return apiRequest<RoleRow>(`/roles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  setPermissions(id: string, body: { permission_codes: string[]; reason: string }) {
    return apiRequest<RoleRow>(`/roles/${id}/permissions`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
};
